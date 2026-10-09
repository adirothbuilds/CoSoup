"""Owner-scoped prospective experiments using existing durable records.

Policy records hold versioned private ledgers; immutable reports hold decisions.
This avoids replacing personal portfolios or requiring new database identities.
"""
import copy
import hashlib
import json
import shutil
from datetime import date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from stock_scanner.calendar import calendar, expected_session
from stock_scanner.storage import read_json

from ..errors import ServiceError
from ..persistence.models import Artifact, Job, Policy, Report, now, uid
from .jobs import enqueue, owned, utc
from .paper_accounting import book, number, targets, valuation, apply_splits, rebalance

KINDS = {'paper_mark','paper_decision'}


def experiments(db, owner):
    return list(db.scalars(select(Policy).where(Policy.owner_id==owner, Policy.id.like('paper:%'))))


def record(db, owner, identity, lock=False):
    if not isinstance(identity,str) or len(identity)!=32 or any(c not in '0123456789abcdef' for c in identity):
        raise ServiceError('not_found','Paper experiment not found',404)
    row=owned(db,Policy,'paper:'+identity,owner,lock)
    if row.values.get('kind')!='paper_experiment':
        raise ServiceError('not_found','Paper experiment not found',404)
    return row


def latest_report(db, owner, session):
    return db.scalar(select(Report).join(Artifact,Report.artifact_id==Artifact.id).join(Job,Report.job_id==Job.id).where(
        Report.owner_id==owner, Report.mode=='live', Report.data_date==session,
        ~Report.quality.like('blocked%'), Job.status=='succeeded').order_by(Artifact.created_at.desc()).limit(1))


def queue_once(db, owner, kind, state, session, report_id=None):
    key=f"paper:{state['id']}:{kind}:{session}"
    old=db.scalar(select(Job).where(Job.owner_id==owner,Job.idempotency_key==key))
    if old:
        return old
    return enqueue(db,owner,kind,{'experiment_id':state['id'],'session':session,'report_id':report_id},key)


def create(db, owner, settings, request, key=None):
    if not settings.codex_enabled or not settings.codex_sandbox_verified:
        raise ServiceError('agent_not_ready','Paper manager requires the verified account-authenticated analyst',409)
    identity=hashlib.sha256((owner+':'+key).encode()).hexdigest()[:32] if key else uid()
    existing=db.get(Policy,'paper:'+identity)
    policy={'initial_cash':str(request.initial_cash),'max_positions':request.max_positions,
            'max_position_weight':str(request.max_position_weight),'currency':'USD',
            'fees_bps':'0','sensitivity_cost_bps':'10','dividends':'excluded',
            'execution':'Daily-bar open on a trading date strictly after the completed decision New York date',
            'benchmark':'SPY buy and hold; same raw price-only basis',
            'scanner_baseline':'Daily original candidates, equal weights capped at the same position maximum; cash otherwise'}
    if existing:
        if existing.owner_id!=owner or existing.values['policy']!=policy or existing.values['name']!=request.name:
            raise ServiceError('idempotency_conflict','Experiment key was used with a different policy',409)
        return existing.values
    if len(experiments(db,owner))>=10:
        raise ServiceError('paper_experiment_limit','At most ten paper experiments are supported',422)
    stamp=now();market_date=stamp.astimezone(ZoneInfo('America/New_York')).date().isoformat()
    first=calendar().date_to_session((date.fromisoformat(market_date)+timedelta(days=1)).isoformat(),direction='next').date().isoformat()
    state={'schema_version':1,'kind':'paper_experiment','id':identity,'name':request.name,
           'created_at':stamp.isoformat(),'start_date':stamp.astimezone(ZoneInfo(settings.timezone)).date().isoformat(),
           'start_market_date':market_date,'status':'active','policy':policy,
           'model':settings.codex_model,'profile':'paper-manager-v1',
           'books':{label:book(request.initial_cash) for label in ['agent','spy','scanner']},
           'pending':{'spy':{'weights':{'SPY':'1'},'session':first,'decision_id':identity+':benchmark','status':'pending'}},
           'decisions':[],'snapshots':[],'gaps':[],
           'starting_equity':str(request.initial_cash), 'first_execution_session':first}
    db.add(Policy(id='paper:'+identity,owner_id=owner,values=state));db.flush()
    session=expected_session(settlement_minutes=settings.settlement_minutes,data_ready_time=settings.market_data_ready_time)
    source=latest_report(db,owner,session)
    if source:
        queue_once(db,owner,'paper_decision',state,session,source.id)
    return state


def pump(db, storage, settings, at=None):
    session=expected_session(at,settings.settlement_minutes,settings.market_data_ready_time)
    rows=list(db.scalars(select(Policy).where(Policy.id.like('paper:%'))))
    count=0
    for row in rows:
        state=row.values
        if state.get('kind')!='paper_experiment' or state.get('status') not in {'active','paused'}:
            continue
        if session>=state['start_market_date'] and storage.path('market/raw/grouped/'+session+'.json.gz').is_file():
            queue_once(db,row.owner_id,'paper_mark',state,session)
        source=latest_report(db,row.owner_id,session)
        if source and state['status']=='active':
            queue_once(db,row.owner_id,'paper_decision',state,session,source.id);count+=1
    return count


def prices_for(storage, session):
    path=storage.path('market/raw/grouped/'+session+'.json.gz')
    if not path.is_file():
        return {},{},'missing_daily_cache'
    try:
        payload=read_json(path)
        if payload.get('session')!=session or payload.get('adjusted') is not False or payload['data'].get('adjusted') is not False:
            raise ValueError()
        opens,closes,seen={},{},set()
        for item in payload['data']['results']:
            symbol=item.get('T')
            if symbol in seen:
                opens.pop(symbol,None);closes.pop(symbol,None);continue
            seen.add(symbol)
            try:
                o,h,l,c=(number(item[k]) for k in ['o','h','l','c'])
                if min(o,h,l,c)<=0 or l>min(o,c) or h<max(o,c) or l>h:
                    continue
                opens[symbol]=str(o);closes[symbol]=str(c)
            except (KeyError,ServiceError):
                continue
        return opens,closes,None
    except (OSError,ValueError,KeyError,TypeError,EOFError):
        return {},{},'invalid_daily_cache'


def split_reference(storage, first, end):
    options=[]
    for path in storage.path('market/raw/splits').glob('*.json.gz'):
        if path.name[:10]<=first and path.name[11:21]>=end:
            options.append(path)
    if not options:
        return None
    try:
        payload=read_json(sorted(options,key=lambda p:p.name[11:21])[0])
        if payload['first']>first or payload['last']<end:
            return None
        events=[];seen={}
        for event in payload['results']:
            day=event['execution_date'];date.fromisoformat(day)
            if not first<=day<=end:
                continue
            a,b=number(event['split_from']),number(event['split_to'])
            if a<=0 or b<=0:
                return None
            key=(event['ticker'],day)
            ratio=b/a
            if key in seen:
                if seen[key]!=ratio:return None
                continue
            seen[key]=ratio;events.append(event)
        return events
    except (OSError,ValueError,KeyError,TypeError,EOFError,ServiceError):
        return None


def advance(state, storage, end):
    first=state['snapshots'][-1]['session'] if state['snapshots'] else state['start_market_date']
    if end<first:
        return
    days=[s.date().isoformat() for s in calendar().sessions_in_range(first,end)]
    days=[d for d in days if not state['snapshots'] or d>state['snapshots'][-1]['session']]
    if not days:
        return
    events=split_reference(storage,days[0],end)
    for session in days:
        opens,closes,error=prices_for(storage,session);gaps=[]
        if error:gaps.append(error)
        if events is None:gaps.append('split_reference_unavailable')
        measures={}
        for label,ledger in state['books'].items():
            if events is not None:apply_splits(ledger,events,session)
            pending=state['pending'].get(label)
            if pending and pending['session']==session and pending['status']=='pending':
                try:
                    if events is None and ledger['positions']:
                        raise ServiceError('paper_split_reference_missing','Cannot execute with an unknown split basis')
                    rebalance(ledger,pending['weights'],opens,session,pending['decision_id'])
                    pending['status']='filled';pending['resolved_at']=now().isoformat()
                except ServiceError as failure:
                    pending['status']='blocked';pending['error']=failure.code;gaps.append(label+':'+failure.code)
                if label=='agent':
                    for decision in state['decisions']:
                        if decision['job_id']==pending['decision_id']:
                            decision['execution_status']=pending['status']
            if pending and pending['status']=='blocked':
                gaps.append(label+':blocked_execution')
            marked=valuation(ledger,closes)
            if events is None and ledger['positions']:
                marked['equity']=None;marked['quality']='partial_coverage'
            if marked['missing_symbols']:gaps.append(label+':missing_prices')
            measures[label]=marked
        initial=number(state['starting_equity'])
        point={'session':session,'marked_at':now().isoformat(),'books':measures,'gaps':sorted(set(gaps)),
               'quality':'partial_coverage' if gaps or any(m['equity'] is None for m in measures.values()) else 'complete'}
        for label,m in measures.items():
            m['change_pct']=float((number(m['equity'])/initial-1)*100) if m['equity'] is not None else None
            known=[number(p['books'][label]['equity']) for p in state['snapshots'] if p['books'][label]['equity'] is not None]
            high=max([initial,*known,number(m['equity'])] if m['equity'] is not None else [initial,*known])
            m['drawdown_pct']=float((number(m['equity'])/high-1)*100) if m['equity'] is not None else None
            m['cost_sensitivity_equity']=str(number(m['equity'])-number(state['books'][label]['turnover_notional'])*number(state['policy']['sensitivity_cost_bps'])/10000) if m['equity'] is not None else None
        state['snapshots'].append(point)
    state['gaps']=state['snapshots'][-1]['gaps']


def overview(state):
    value=copy.deepcopy(state)
    value['snapshots']=value['snapshots'][-1000:]
    for ledger in value['books'].values():
        ledger['fills']=ledger['fills'][-200:]
        ledger.pop('applied_splits',None)
    value['decisions']=value['decisions'][-100:]
    value['note']='Hypothetical prospective portfolio. Raw daily-bar prices; dividends, primary fees and cash interest are excluded. No execution, tax or real-money return certification. Missing valuations remain gaps.'
    initial=number(state['starting_equity']);points={label:[{'label':state['start_date']+' · start','value':float(initial)}] for label in state['books']}
    for point in value['snapshots']:
        for label,m in point['books'].items():
            if m['equity'] is not None:points[label].append({'label':point['session'],'value':float(number(m['equity']))})
    value['charts']=[{'id':state['id']+':equity:'+label,'source_id':state['id'],'title':title,
                      'kind':'line','unit':'USD','points':points[label],
                      'note':value['note']+' Missing dates are omitted; '+state['policy']['execution']+'.'}
                     for label,title in [('agent','Codex hypothetical equity'),('spy','SPY hypothetical benchmark'),('scanner','Deterministic scanner baseline')]]
    return value


def public_view(db, owner, state):
    value=overview(state)
    job=db.scalar(select(Job).where(Job.owner_id==owner,Job.kind=='paper_decision',
                                   Job.payload['experiment_id'].as_string()==state['id']).order_by(Job.created_at.desc()).limit(1))
    value['manager_job']={'id':job.id,'status':job.status,'error':job.error,'progress':job.progress} if job else None
    return value


def mark(context):
    with context.database.session() as db:
        row=record(db,context.job.owner_id,context.job.payload['experiment_id'],True)
        state=copy.deepcopy(row.values)
        advance(state,context.storage,context.job.payload['session']);row.values=copy.deepcopy(state)
    return {'experiment_id':state['id'],'session':context.job.payload['session'],'quality':state['snapshots'][-1]['quality'] if state['snapshots'] else 'awaiting_first_session'}


def finish_decision(context, published_result, result):
    """Reconcile a published immutable decision after a lease/process interruption."""
    job = context.job
    provenance = result['provenance']
    with context.database.session() as db:
        row = record(db, job.owner_id, job.payload['experiment_id'], True)
        state = copy.deepcopy(row.values)
        if not any(d['job_id'] == job.id for d in state['decisions']):
            decision = {'job_id': job.id, 'report_id': published_result['report_id'],
                        'research_session': job.payload['session'], 'completed_at': provenance['completed_at_utc'],
                        'decision': result['decision'], 'status': result['status'],
                        'target_weights': result['target_weights'], 'execution_session': provenance['execution_session'],
                        'validation_error': provenance['validation_error']}
            state['decisions'].append(decision)
            if not provenance['validation_error'] and result['decision'] == 'rebalance':
                old = state['pending'].get('agent')
                if old and old['status'] == 'pending':
                    decision['superseded_pending_decision'] = old['decision_id']
                pending = {'weights': {r['symbol']: r['weight'] for r in result['target_weights']},
                           'session': provenance['execution_session'], 'decision_id': job.id, 'status': 'pending'}
                if state['snapshots'] and state['snapshots'][-1]['session'] >= pending['session']:
                    pending.update(status='blocked', error='paper_decision_recovered_after_execution_session')
                state['pending']['agent'] = pending
            row.values = copy.deepcopy(state)
    return {**published_result, 'experiment_id': state['id'], 'decision_status': result['status'],
            'execution_session': provenance['execution_session']}


def decide(context, analyst=None):
    from ..adapters.analyst import backend
    from .agent_context import context_packet
    from .research_analysis import prepare
    from .reports import publish, published
    existing = published(context, 'paper_decision')
    if existing:
        with context.database.session() as db:
            saved = owned(db, Report, existing['report_id'], context.job.owner_id).summary
        return finish_decision(context, existing, saved)
    job,storage=context.job,context.storage
    with context.database.session() as db:
        row=record(db,job.owner_id,job.payload['experiment_id'],True)
        state=copy.deepcopy(row.values)
        advance(state,storage,job.payload['session']);row.values=copy.deepcopy(state)
        if state['status']!='active':
            return {'experiment_id':state['id'],'status':'paused'}
        report=owned(db,Report,job.payload['report_id'],job.owner_id)
        latest=expected_session(settlement_minutes=context.settings.settlement_minutes,data_ready_time=context.settings.market_data_ready_time)
        if report.mode!='live' or report.quality.startswith('blocked') or report.data_date!=latest or report.data_date!=job.payload['session']:
            raise ServiceError('paper_stale_research','No prospective decision can use stale or blocked market research')
        stamp=now();end=stamp.date().isoformat()
        sources=[report.id]
        sec=db.scalar(select(Report).join(Artifact,Report.artifact_id==Artifact.id).join(Job,Report.job_id==Job.id).where(
            Report.owner_id==job.owner_id,Report.mode=='sec_research',Report.data_date<=end,
            ~Report.quality.like('blocked%'),Job.status=='succeeded').order_by(Report.data_date.desc(),Artifact.created_at.desc()).limit(1))
        if sec:sources.append(sec.id)
        request={'task_type':'research_chat','prompt':'Inspect the supplied paper experiment and dated research. Propose a constrained prospective paper decision using offline research tools. Cash and hold are allowed. Explain uncertainty in English.',
                 'report_ids':sources,'end_date':end,'start_date':end,'allow_portfolio_data':False,'include_paper_experiments':False}
        packet=context_packet(db,storage,context.settings,job.owner_id,request)
        # Prepare the fixed comparison even if account auth/model execution fails.
        raw=next(r['data'] for r in packet['reports'] if r['id']==report.id)
        candidates=raw.get('candidates',[])[:state['policy']['max_positions']]
        equal=min(number(1)/len(candidates),number(state['policy']['max_position_weight'])) if candidates else number(0)
        baseline_date=stamp.astimezone(ZoneInfo('America/New_York')).date()+timedelta(days=1)
        baseline_session=calendar().date_to_session(baseline_date.isoformat(),direction='next').date().isoformat()
        state['pending']['scanner']={'weights':{c['symbol']:str(equal) for c in candidates},'session':baseline_session,
                                     'decision_id':job.id+':scanner','status':'pending'}
        row.values=copy.deepcopy(state)
        hashes={r:owned(db,Artifact,owned(db,Report,r,job.owner_id).artifact_id,job.owner_id).sha256 for r in sources}
        storage.reserve(db,job.id,job.owner_id,context.settings.limits.agent_reservation_bytes)
    packet['paper_experiments']=[overview(state)]
    prepare(packet,storage,context.settings)
    approved=set(state['books']['agent']['positions'])
    for r in packet['reports']:
        if r['mode']=='live':
            approved.update(c['symbol'] for group in ['candidates','near_breakouts','screening_review'] for c in r['data'].get(group,[]) if c.get('data_valid'))
    packet['paper_experiment']=overview(state)
    packet['paper_experiment']['books']={label:{k:v for k,v in ledger.items() if k!='fills'} for label,ledger in packet['paper_experiment']['books'].items()}
    packet['approved_paper_symbols']=sorted(approved);packet['source_ids'].append(state['id'])
    packet['decision_cutoff_at_utc']=stamp.isoformat();packet['source_artifact_hashes']=hashes
    if len(json.dumps(packet).encode())>context.settings.limits.agent_reservation_bytes//2:
        raise ServiceError('agent_input_limit','Paper research packet exceeds the bounded workspace budget')
    workspace=storage.path(f'job-workspaces/{job.id}-{job.lease_token}');workspace.mkdir(parents=True,exist_ok=True,mode=0o700)
    try:
        (workspace/'inputs.json').write_text(json.dumps(packet))
        profile_path=Path(__file__).resolve().parents[1]/'profiles/paper-manager.md'
        manifest_path=Path(__file__).resolve().parents[1]/'profiles/research-tools.json'
        profile_hash=hashlib.sha256(profile_path.read_bytes()).hexdigest()
        manifest_hash=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
        shutil.copyfile(profile_path,workspace/'AGENTS.md')
        for name in ['research_tools.py']:
            shutil.copyfile(Path(__file__).with_name(name),workspace/name)
        shutil.copyfile(manifest_path,workspace/'research-tools.json')
        shutil.copytree(Path(__file__).resolve().parents[1]/'profiles/skills',workspace/'.agents/skills')
        owner_ref=hashlib.sha256(job.owner_id.encode()).hexdigest()[:32]
        request.update(task_type='paper_portfolio',_native_session_home=str(storage.path(f'agent-sessions/{owner_ref}/paper-{state["id"]}')))
        result=(analyst or backend(context.settings)).analyze(workspace,request,context.checkpoint)
        completed=now();validation_error=None;weights={}
        try:
            if set(result.get('sources',[]))-set(packet['source_ids']):
                raise ServiceError('paper_unapproved_source','Paper decision cites an unauthorized source')
            if result.get('decision') not in {'hold','rebalance'}:
                raise ServiceError('invalid_paper_decision','Decision must be hold or rebalance')
            weights=targets(result.get('target_weights'),state['policy'],approved)
            if result['decision']=='hold' and weights:
                raise ServiceError('invalid_paper_decision','Hold must not propose replacement weights')
        except ServiceError as error:
            validation_error=error.code
        ny_date=completed.astimezone(ZoneInfo('America/New_York')).date()
        execution=calendar().date_to_session((ny_date+timedelta(days=1)).isoformat(),direction='next').date().isoformat()
        result.update(status='rejected' if validation_error else 'partial_coverage' if result['gaps'] else 'complete',
                      experiment_id=state['id'],data_date=completed.date().isoformat(),
                      provenance={'job_id':job.id,'decision_cutoff_at_utc':stamp.isoformat(),'completed_at_utc':completed.isoformat(),
                                  'source_artifact_hashes':hashes,'source_ids':packet['source_ids'],'profile_id':'paper-manager-v1',
                                  'profile_sha256':profile_hash,'tools_manifest_sha256':manifest_hash,
                                  'model':context.settings.codex_model,'session':result.pop('_session',None),'execution_session':execution,
                                  'validation_error':validation_error,'price_convention':state['policy']['execution']})
        published_result=publish(context,result['data_date'],'paper_decision',result,result['markdown'])
        return finish_decision(context, published_result, result)
    finally:
        shutil.rmtree(workspace,ignore_errors=True)
