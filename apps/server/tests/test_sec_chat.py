import json
from unittest.mock import patch

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.server.api.app import create_app
from apps.server.persistence.models import Report
from apps.server.workers.codex.handler import handle as agent_handle
from apps.server.workers.runtime import execute_one
from apps.server.workers.scanner.handler import handle
from test_server import ServerCase


class SecChatTests(ServerCase):
    def seed_report(self, mode='live', owner='owner', provenance=None):
        path=self.storage.path(f'reports/{owner}-{mode}.json');path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps({'status':'partial_coverage','data_date':'2026-10-02','candidates':[{'symbol':'ABC'}]}))
        with self.database.session() as db:
            a=self.storage.register(db,owner,path,'reports')
            r=Report(owner_id=owner,job_id=owner+mode,data_date='2026-10-02',mode=mode,quality='partial_coverage',
                     artifact_id=a.id,markdown_id=a.id,summary={'provenance':provenance or {}})
            db.add(r);db.flush();return r.id

    def enable_chat(self):
        self.client.close()
        self.settings=self.settings.model_copy(update={'codex_enabled':True,'codex_sandbox_verified':True})
        self.client=TestClient(create_app(self.settings,self.database,token='unit-test-only-token-'+'a'*40))
        self.client.headers['Authorization']='Bearer unit-test-only-token-'+'a'*40

    def test_sync_is_owner_scoped_bounded_and_idempotent(self):
        own=self.seed_report();other=self.seed_report(owner='other')
        payload={'report_id':own,'manager_ciks':[]}
        response=self.client.post('/api/v1/research/sec-sync',json=payload,headers={'Idempotency-Key':'sec-intent'})
        self.assertEqual(response.status_code,202)
        repeat=self.client.post('/api/v1/research/sec-sync',json=payload,headers={'Idempotency-Key':'sec-intent'})
        self.assertEqual(response.json()['job_id'],repeat.json()['job_id'])
        self.assertEqual(self.job(response.json()['job_id']).payload['symbols'],['ABC'])
        self.assertEqual(self.client.post('/api/v1/research/sec-sync',json={'report_id':other}).status_code,404)
        self.assertEqual(self.client.post('/api/v1/research/sec-sync',json={'symbols':['../../private']}).status_code,422)
        self.assertEqual(self.client.post('/api/v1/research/sec-sync',json={'symbols':['ABC']*11}).status_code,422)

    def test_blocked_source_publishes_diagnostics_and_does_not_claim_success(self):
        r=self.client.post('/api/v1/research/sec-sync',json={'symbols':['ABC'],'manager_ciks':[]})
        identity=r.json()['job_id']
        class Blocked:
            def __init__(self,*a,**kw):self.errors=[{'provider':'SEC','http_status':403,'endpoint':'https://www.sec.gov/files/company_tickers.json','message':'Public access blocked'}];self.cache_paths=set();self.stopped=True;self.requests=1
            def get(self,*a):return None
        with patch('apps.server.services.sec_research.SecClient',Blocked):
            self.assertTrue(execute_one('scanner',handle,self.database,self.settings))
        job=self.job(identity);self.assertEqual(job.status,'failed');self.assertEqual(job.error['code'],'sec_source_blocked')
        saved=self.client.get('/api/v1/reports',params={'job_id':identity}).json()
        self.assertEqual(saved[0]['quality'],'blocked_provider')
        self.assertNotIn('companies',saved[0]['summary'])
        report=self.client.get(f"/api/v1/reports/{saved[0]['id']}/content").json()
        self.assertEqual(report['errors'][0]['http_status'],403)
        self.assertFalse(report['provenance']['market_prices_refreshed']);self.assertFalse(report['provenance']['model_request_made'])

    def test_chat_turns_persist_followups_and_replay_does_not_export_new_sources(self):
        self.enable_chat();source=self.seed_report();cid='a'*32
        payload={'conversation_id':cid,'prompt':'Explain the evidence','report_ids':[source]}
        headers={'Idempotency-Key':'first-message'}
        response=self.client.post('/api/v1/agent/chat',json=payload,headers=headers)
        self.assertEqual(response.status_code,202,response.text)
        identity=response.json()['job_id']
        replay=self.client.post('/api/v1/agent/chat',json=payload,headers=headers)
        self.assertEqual(replay.json()['job_id'],identity)
        self.assertEqual(self.client.post('/api/v1/agent/chat',json={**payload,'prompt':'Changed'},headers=headers).status_code,409)
        self.assertEqual(self.client.post('/api/v1/agent/chat',json=payload).status_code,409)
        seen=[]
        class Analyst:
            def analyze(self,workspace,request,checkpoint):
                inputs=json.loads((workspace/'inputs.json').read_text());seen.append(inputs)
                return {'markdown':'# Evidence\n\nAn explicitly sourced synthetic answer.','sources':inputs['source_ids'],'gaps':['Synthetic source coverage is limited']}
        execute_one('codex',lambda c:agent_handle(c,Analyst()),self.database,self.settings)
        self.assertEqual(self.job(identity).status,'succeeded',self.job(identity).error)
        self.assertIsNone(seen[0]['portfolio']);self.assertEqual(seen[0]['images'],[])
        saved=self.job(identity).result['report_id']
        next_turn=self.client.post('/api/v1/agent/chat',json={**payload,'prompt':'What remains uncertain?'})
        self.assertEqual(next_turn.status_code,202,next_turn.text)
        self.assertIn(saved,self.job(next_turn.json()['job_id']).payload['report_ids'])
        history=self.client.get(f'/api/v1/agent/conversations/{cid}').json()
        self.assertEqual(len(history['messages']),2)
        self.assertEqual(history['messages'][0]['answer']['markdown'],'# Evidence\n\nAn explicitly sourced synthetic answer.')
        self.assertEqual(self.client.get('/api/v1/agent/conversations').json()[0]['id'],cid)

    def test_chat_rejects_other_owners_and_private_derived_reports(self):
        self.enable_chat()
        reports=[(self.seed_report(owner='other'),404),(self.seed_report(mode='portfolio'),403),
                 (self.seed_report(mode='agent',provenance={'document_export_authorized':True}),403)]
        for source,status in reports:
            response=self.client.post('/api/v1/agent/chat',json={'conversation_id':'b'*32,'prompt':'Review','report_ids':[source]})
            self.assertEqual(response.status_code,status,response.text)
        with self.database.session() as db:
            self.assertFalse(list(db.scalars(select(Report).where(Report.mode=='sec_research'))))

    def test_chat_cannot_bypass_conversation_scope_through_generic_task_queue(self):
        self.enable_chat();source=self.seed_report()
        response=self.client.post('/api/v1/agent/tasks',json={
            'task_type':'research_chat','prompt':'Review','report_ids':[source]})
        self.assertEqual(response.status_code,422)
        self.assertEqual(response.json()['error']['code'],'chat_endpoint_required')
        self.assertEqual(self.client.get('/api/v1/agent/conversations').json(),[])

    def test_chart_tools_reject_fabricated_datasets_and_keep_periods_comparable(self):
        from apps.server.services.research_tools import catalog,render
        from apps.server.errors import ServiceError
        packet={'reports':[{'id':'source','mode':'sec_research','data':{'companies':[{'symbol':'ABC','metrics':[
            {'label':'Revenue','unit':'USD','period_start':'2026-04-01','period_end':'2026-06-30','value':12},
            {'label':'Revenue','unit':'USD','period_start':'2026-01-01','period_end':'2026-03-31','value':10},
            {'label':'Revenue','unit':'USD','period_start':'2025-01-01','period_end':'2025-12-31','value':40}]}]}}], 'portfolio':None}
        data=catalog(packet);self.assertEqual([p['value'] for p in data[0]['points']],[10,12])
        chart=render([{'dataset_id':data[0]['id'],'title':'Reported revenue'}],data)
        self.assertEqual(chart[0]['source_id'],'source')
        with self.assertRaises(ServiceError):render([{'dataset_id':'unapproved','title':'Fake'}],data)
        with self.assertRaises(ServiceError):render([{'dataset_id':data[0]['id'],'title':'Fake','points':[999]}],data)

    def test_native_session_command_resumes_only_explicit_session_and_hides_history(self):
        from apps.server.adapters.codex import CodexCLI
        profile=self.root/'profile';profile.mkdir();(profile/'auth.json').write_text('{}')
        workspace=self.root/'workspace';workspace.mkdir();session=self.root/'session';session.mkdir()
        settings=self.settings.model_copy(update={'codex_enabled':True,'codex_sandbox_verified':True,'codex_profile_dir':profile})
        with patch('shutil.which',return_value='/usr/bin/bwrap'):
            command=CodexCLI(settings).command(workspace,session,'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.assertNotIn('--ephemeral',command);self.assertNotIn('--last',command)
        self.assertEqual(command[command.index('resume')+1],'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee')
        self.assertIn('"/home/agent/.codex/sessions"="deny"',next(v for v in command if v.startswith('permissions.steve.filesystem=')))
        self.assertIn('"/home/agent/.codex/auth.json"="deny"',next(v for v in command if v.startswith('permissions.steve.filesystem=')))
        self.assertIn('features.multi_agent=true',command)
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox',command)

    def test_documents_in_chat_are_proposals_until_owner_confirms_and_permissions_persist(self):
        from io import BytesIO
        from PIL import Image
        from apps.server.workers.imports.handler import handle as import_handle
        self.enable_chat()
        portfolio=self.client.post('/api/v1/portfolios',json={'name':'Synthetic portfolio'}).json()['id']
        b=BytesIO();Image.new('RGB',(20,20),'white').save(b,format='PNG')
        upload=self.client.post('/api/v1/uploads',files={'file':('test.png',b.getvalue(),'image/png')}).json()['upload_id']
        imported=self.client.post('/api/v1/imports',json={'portfolio_id':portfolio,'upload_id':upload}).json()['import_id']
        class Extractor:
            def extract(self,*a):return {'pages':[{'text':'ABC 10 shares; cost and timestamp unknown'}],'rows':[],'warnings':[],'requires_confirmation':True}
        execute_one('imports',lambda c:import_handle(c,Extractor()),self.database,self.settings)
        payload={'conversation_id':'c'*32,'prompt':'Fill my portfolio from this screenshot','upload_ids':[upload],'import_ids':[imported]}
        self.assertEqual(self.client.post('/api/v1/agent/chat',json=payload).status_code,422)
        payload['allow_uploaded_documents']=True
        response=self.client.post('/api/v1/agent/chat',json=payload);self.assertEqual(response.status_code,202,response.text)
        row={'type':'opening','symbol':'ABC','quantity':'10','price':None,'amount':None,'at':None,'fees':None,'currency':None,'source_text':'ABC 10 shares'}
        class Analyst:
            def analyze(self,workspace,request,checkpoint):
                inputs=json.loads((workspace/'inputs.json').read_text())
                self_outer.assertEqual(len(inputs['images']),1);self_outer.assertEqual(len(inputs['imports']),1)
                self_outer.assertIsNone(inputs['portfolio']);self_outer.assertEqual(inputs['reports'],[])
                self_outer.assertTrue((workspace/'.agents/skills/portfolio-documents/SKILL.md').exists())
                return {'markdown':'Review the proposed opening position. The basis is unknown.','sources':inputs['source_ids'],'gaps':['Timestamp and currency need confirmation'],
                        'chart_requests':[],'portfolio_proposals':[{'import_id':imported,'rows':[row],'warnings':['Check the original statement']} ]}
        self_outer=self
        execute_one('codex',lambda c:agent_handle(c,Analyst()),self.database,self.settings)
        job=self.job(response.json()['job_id']);self.assertEqual(job.status,'succeeded',job.error)
        summary=self.client.get('/api/v1/reports',params={'job_id':job.id}).json()[0]['summary']
        self.assertNotIn('portfolio_proposals',summary);self.assertNotIn('markdown',summary)
        self.assertEqual(self.client.get(f'/api/v1/portfolios/{portfolio}/positions').json()['positions'],[])
        answer=self.client.get('/api/v1/agent/conversations/'+'c'*32).json()['messages'][0]['answer']
        self.assertIsNone(answer['portfolio_proposals'][0]['rows'][0]['price'])
        self.assertEqual(self.client.post('/api/v1/agent/chat',json={'conversation_id':'c'*32,'prompt':'Explain','report_ids':[job.result['report_id']]}).status_code,403)
        reviewed={k:v for k,v in row.items() if k!='source_text'};reviewed.update(at='2026-10-02T12:00:00+00:00',currency='USD',fees='0')
        confirmed=self.client.post(f'/api/v1/imports/{imported}/confirm',json={'rows':[reviewed]});self.assertEqual(confirmed.status_code,200,confirmed.text)
        position=self.client.get(f'/api/v1/portfolios/{portfolio}/positions').json()['positions'][0]
        from decimal import Decimal
        self.assertEqual(Decimal(position['quantity']),Decimal('10'));self.assertFalse(position['basis_known'])
        followup=self.client.post('/api/v1/agent/chat',json={'conversation_id':'c'*32,'prompt':'Explain the missing basis','report_ids':[job.result['report_id']],'allow_uploaded_documents':True})
        self.assertEqual(followup.status_code,202,followup.text)
        followup_job=self.job(followup.json()['job_id'])
        self.assertEqual(followup_job.payload['upload_ids'],[upload]);self.assertEqual(followup_job.payload['import_ids'],[imported])
        self.client.post(f"/api/v1/agent/tasks/{followup_job.id}/cancel")
        self.assertEqual(self.client.patch('/api/v1/agent/conversations/'+'c'*32,json={'title':'Portfolio document','archived':True}).status_code,200)
        self.assertTrue(self.client.get('/api/v1/agent/conversations').json()[0]['archived'])
        self.assertEqual(self.client.post('/api/v1/agent/chat',json=payload).status_code,409)
        self.assertEqual(self.client.patch('/api/v1/agent/conversations/'+'c'*32,json={'archived':False}).status_code,200)
        self.assertEqual(self.client.patch('/api/v1/agent/conversations/'+'d'*32,json={'title':'Other'}).status_code,404)
