import copy
import json
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import patch

from apps.server.errors import ServiceError
from apps.server.persistence.models import Artifact, Job, Policy, Report
from apps.server.services.paper_accounting import book, targets, valuation, apply_splits, rebalance
from apps.server.services.paper import create, record, pump, advance, overview
from apps.server.api.schemas import PaperCreateRequest
from apps.server.workers.codex.handler import handle
from apps.server.workers.runtime import execute_one
from stock_scanner.storage import atomic_json
from test_server import ServerCase

STAMP=datetime(2026,10,9,7,tzinfo=timezone.utc)


class AccountingTests(ServerCase):
    def test_fractional_cash_and_split_adjustment_are_atomic_and_idempotent(self):
        ledger=book('100')
        rebalance(ledger,{'ABC':'0.2'},{'ABC':'10'},'2026-10-12','decision')
        self.assertEqual(Decimal(ledger['cash']),80)
        self.assertEqual(Decimal(ledger['positions']['ABC']),2)
        rebalance(ledger,{'ABC':'0.2'},{'ABC':'10'},'2026-10-12','decision')
        self.assertEqual(len(ledger['fills']),1)
        events=[{'ticker':'ABC','execution_date':'2026-10-13','split_from':1,'split_to':2}]
        apply_splits(ledger,events,'2026-10-13');apply_splits(ledger,events,'2026-10-13')
        self.assertEqual(Decimal(ledger['positions']['ABC']),4)
        self.assertEqual(Decimal(valuation(ledger,{'ABC':'5'})['equity']),100)
        before=copy.deepcopy(ledger)
        with self.assertRaises(ServiceError):rebalance(ledger,{'XYZ':'0.2'},{'ABC':'5'},'2026-10-14','missing')
        self.assertEqual(ledger,before)
        self.assertIsNone(valuation(ledger,{})['equity'])

    def test_constraints_and_unknown_numbers_do_not_create_fills(self):
        policy={'max_positions':10,'max_position_weight':'0.2'}
        for rows in [[{'symbol':'UNKNOWN','weight':'0.1','reason':'test'}],
                     [{'symbol':'ABC','weight':'0.21','reason':'test'}],
                     [{'symbol':'ABC','weight':'NaN','reason':'test'}],
                     [{'symbol':'ABC','weight':'0.1','reason':'test'}]*2]:
            with self.assertRaises(ServiceError):targets(rows,policy,{'ABC'})
        rows=[{'symbol':str(i),'weight':'0.2','reason':'test'} for i in range(6)]
        with self.assertRaises(ServiceError):targets(rows,policy,{str(i) for i in range(6)})
        with self.assertRaises(ServiceError):apply_splits(book(100),[{'ticker':'ABC','execution_date':'2026-10-12','split_from':0,'split_to':2}],'2026-10-12')


class PaperTests(ServerCase):
    def setUp(self):
        super().setUp()
        self.settings.codex_enabled=True;self.settings.codex_sandbox_verified=True
        self.settings.timezone='Asia/Jerusalem'
        jobid=self.post_job('scan',{})
        path=self.storage.path('reports/test-paper.json');path.parent.mkdir(parents=True,exist_ok=True)
        data={'status':'partial_coverage','data_date':'2026-10-08','coverage':{'valid_histories':1},'candidates':[],
              'near_breakouts':[{'symbol':'ABC','data_valid':True,'close':10,'pivot':11}], 'errors':[]}
        path.write_text(json.dumps(data))
        with self.database.session() as db:
            db.get(Job,jobid).status='succeeded'
            artifact=self.storage.register(db,'owner',path,'reports',{'session':'2026-10-08'})
            row=Report(owner_id='owner',job_id=jobid,data_date='2026-10-08',mode='live',quality='partial_coverage',
                       artifact_id=artifact.id,markdown_id=artifact.id,summary={})
            db.add(row);db.flush();self.source=row.id

    def start(self):
        with patch('apps.server.services.paper.now',return_value=STAMP),patch('stock_scanner.calendar.utc_now',return_value=STAMP):
            with self.database.session() as db:
                state=create(db,'owner',self.settings,PaperCreateRequest(),'same-start')
        return state

    def test_native_decision_is_prospective_then_host_resolves_future_prices(self):
        state=self.start()
        class Analyst:
            def analyze(inner,workspace,request,checkpoint):
                packet=json.loads((workspace/'inputs.json').read_text())
                self.assertIsNone(packet['portfolio'])
                self.assertEqual(request['task_type'],'paper_portfolio')
                self.assertEqual(packet['approved_paper_symbols'],['ABC'])
                return {'markdown':'A hypothetical twenty percent allocation.','sources':[self.source],
                        'gaps':[],'decision':'rebalance','target_weights':[{'symbol':'ABC','weight':'0.2','reason':'Dated watchlist evidence'}]}
        with patch('apps.server.services.paper.now',return_value=STAMP),patch('stock_scanner.calendar.utc_now',return_value=STAMP):
            self.assertTrue(execute_one('codex',lambda c:handle(c,Analyst()),self.database,self.settings))
        with self.database.session() as db:
            current=copy.deepcopy(record(db,'owner',state['id']).values)
        self.assertEqual(current['start_date'],'2026-10-09')
        self.assertEqual(current['pending']['agent']['session'],'2026-10-12')
        self.assertEqual(current['books']['agent']['positions'],{})
        for day in ['2026-10-09','2026-10-12']:
            rows=[{'T':'ABC','o':10,'h':12,'l':9,'c':11}, {'T':'SPY','o':100,'h':115,'l':95,'c':110}]
            atomic_json(self.storage.path('market/raw/grouped/'+day+'.json.gz'),{'session':day,'adjusted':False,'data':{'adjusted':False,'results':rows}})
        atomic_json(self.storage.path('market/raw/splits/2026-10-09_2026-10-12.json.gz'),{'first':'2026-10-09','last':'2026-10-12','results':[]})
        advance(current,self.storage,'2026-10-12');advance(current,self.storage,'2026-10-12')
        self.assertEqual(len(current['snapshots']),2)
        last=current['snapshots'][-1]
        self.assertEqual(Decimal(last['books']['agent']['equity']),102000)
        self.assertEqual(Decimal(last['books']['spy']['equity']),110000)
        self.assertEqual(Decimal(last['books']['scanner']['equity']),100000)
        self.assertEqual(Decimal(last['books']['agent']['cost_sensitivity_equity']),101980)
        self.assertEqual(len(current['books']['agent']['fills']),1)
        self.assertEqual(len(overview(current)['charts']),3)

    def test_rejected_agent_result_is_preserved_without_mutating_holdings(self):
        state=self.start()
        class Analyst:
            def analyze(inner,*args):return {'markdown':'Unsupported proposal.','sources':[self.source],'gaps':[],
                'decision':'rebalance','target_weights':[{'symbol':'BAD','weight':'0.1','reason':'Invented stock'}]}
        with patch('apps.server.services.paper.now',return_value=STAMP),patch('stock_scanner.calendar.utc_now',return_value=STAMP):
            execute_one('codex',lambda c:handle(c,Analyst()),self.database,self.settings)
        with self.database.session() as db:
            current=record(db,'owner',state['id']).values
            self.assertEqual(current['decisions'][0]['status'],'rejected')
            self.assertNotIn('agent',current['pending'])
            self.assertIn('scanner',current['pending'])
            self.assertEqual(current['books']['agent']['cash'],'100000')
            with self.assertRaises(ServiceError):record(db,'another-owner',state['id'])

    def test_published_decision_reconciles_after_interruption_without_another_model_call(self):
        state=self.start()
        class Analyst:
            calls=0
            def analyze(inner,*args):
                inner.calls+=1
                return {'markdown':'A synthetic prospective allocation.','sources':[self.source],'gaps':[],
                        'decision':'rebalance','target_weights':[{'symbol':'ABC','weight':'0.2','reason':'Fixture'}]}
        analyst=Analyst()
        with patch('apps.server.services.paper.now',return_value=STAMP),patch('stock_scanner.calendar.utc_now',return_value=STAMP):
            with patch('apps.server.services.paper.finish_decision',side_effect=RuntimeError('Synthetic interruption after publication')):
                execute_one('codex',lambda c:handle(c,analyst),self.database,self.settings)
            with self.database.session() as db:
                job=db.scalar(__import__('sqlalchemy').select(Job).where(Job.kind=='paper_decision'))
                # Simulate lease recovery with the same durable job, not a new decision.
                job.status='queued';identity=job.id
            execute_one('codex',lambda c:handle(c,analyst),self.database,self.settings)
        self.assertEqual(self.job(identity).status,'succeeded',self.job(identity).error)
        self.assertEqual(analyst.calls,1)
        with self.database.session() as db:
            current=record(db,'owner',state['id']).values
            self.assertEqual(len(current['decisions']),1)
            self.assertEqual(current['pending']['agent']['session'],'2026-10-12')
            self.assertEqual(current['books']['agent']['fills'],[])
            self.assertEqual(len(list(db.scalars(__import__('sqlalchemy').select(Report).where(Report.mode=='paper_decision')))),1)

    def test_create_and_completion_dependency_are_idempotent(self):
        state=self.start();again=self.start()
        self.assertEqual(state['id'],again['id'])
        with patch('stock_scanner.calendar.utc_now',return_value=STAMP):
            with self.database.session() as db:
                pump(db,self.storage,self.settings,STAMP);pump(db,self.storage,self.settings,STAMP)
                jobs=list(db.scalars(__import__('sqlalchemy').select(Job).where(Job.kind=='paper_decision')))
                self.assertEqual(len(jobs),1)
                db.get(Job,jobs[0].id).status='failed'
            with self.database.session() as db:
                pump(db,self.storage,self.settings,STAMP)
                self.assertEqual(len(list(db.scalars(__import__('sqlalchemy').select(Job).where(Job.kind=='paper_decision')))),1)
        with self.database.session() as db:
            db.get(Policy,'paper:'+state['id']).values={**state,'status':'paused'}
        self.assertEqual(self.client.get('/api/v1/paper/experiments/'+state['id']).status_code,200)

    def test_paper_only_chat_can_use_approved_charts_without_exporting_personal_portfolio(self):
        state=self.start()
        # Complete the initial decision fixture before queuing the separate chat.
        with self.database.session() as db:
            for job in db.scalars(__import__('sqlalchemy').select(Job).where(Job.kind=='paper_decision')):
                job.status='failed'
        response=self.client.post('/api/v1/agent/chat',json={'conversation_id':'a'*32,
            'prompt':'Explain my paper experiment and show its starting balance.','report_ids':[]})
        self.assertEqual(response.status_code,202,response.text)
        identity=response.json()['job_id']
        class Analyst:
            def analyze(inner,workspace,request,checkpoint):
                packet=json.loads((workspace/'inputs.json').read_text())
                self.assertIsNone(packet['portfolio'])
                self.assertIn(state['id'],packet['source_ids'])
                chart=next(c for c in packet['chart_datasets'] if c['source_id']==state['id'])
                return {'markdown':'The experiment holds simulated cash.','sources':[state['id']], 'gaps':[],
                        'chart_requests':[{'dataset_id':chart['id'],'title':'Starting hypothetical balance'}],'portfolio_proposals':[]}
        with patch('apps.server.services.paper.now',return_value=STAMP),patch('stock_scanner.calendar.utc_now',return_value=STAMP):
            execute_one('codex',lambda c:handle(c,Analyst()),self.database,self.settings)
        self.assertEqual(self.job(identity).status,'succeeded',self.job(identity).error)
        published=self.client.get('/api/v1/reports/'+self.job(identity).result['report_id']+'/content').json()
        self.assertEqual(published['charts'][0]['points'][0]['value'],100000)

    def test_empty_chat_without_any_owner_sources_is_rejected(self):
        response=self.client.post('/api/v1/agent/chat',json={'conversation_id':'b'*32,'prompt':'Show a chart','report_ids':[]})
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.json()['error']['code'],'missing_chat_sources')
