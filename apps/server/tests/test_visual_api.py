import io
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select

from apps.server.api.app import create_app
from apps.server.api.schemas import AgentRequest
from apps.server.config import Settings
from apps.server.persistence.database import Database
from apps.server.persistence.models import Artifact, Policy, Report
from apps.server.services.market import cached_matrix, restore_ids
from apps.server.services.storage import Storage
from stock_scanner.calendar import calendar, sessions_ending
from stock_scanner.storage import atomic_json


class VisualApiTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.settings=Settings(data_dir=self.root/'data',browser_origin='https://scanner.test')
        self.database=Database(url='sqlite:///'+str(self.root/'database.sqlite'))
        self.database.migrate()
        self.token='test-owner-token-'+('a'*40)
        self.app=create_app(self.settings,self.database,token=self.token)
        self.client=TestClient(self.app,base_url='https://scanner.test')
        self.auth={'Authorization':'Bearer '+self.token}
        self.storage=Storage(self.settings)
        self.days=sessions_ending('2026-10-02')

    def tearDown(self):
        cached_matrix.cache_clear()
        self.client.close();self.database.engine.dispose();self.temp.cleanup()

    def market(self,split=False):
        for i,d in enumerate(self.days):
            price=100+i/10
            if split and i<259:price*=2
            atomic_json(self.storage.path(f'market/raw/grouped/{d}.json.gz'),{
                'session':d,'adjusted':False,'retrieved_at':'2026-10-03T00:00:00Z','data':{'adjusted':False,'results':[
                {'T':'AVT','o':price-.5,'h':price+1,'l':price-1,'c':price,'v':1000/(2 if split and i<259 else 1),
                 't':int(calendar().session_close(pd.Timestamp(d)).timestamp()*1000)}]}})
        atomic_json(self.storage.path(f'market/raw/splits/{self.days[0]}_{self.days[-1]}.json.gz'),{
            'first':self.days[0],'last':self.days[-1],'retrieved_at':'2026-10-03T00:00:00Z',
            'results':[{'ticker':'AVT','execution_date':self.days[-1],'split_from':1,'split_to':2}] if split else []})

    def report(self, extra=False):
        candidates=[{'symbol':'AVT','stock_return':.63}]+([{'symbol':'ABC'}] if extra else [])
        path=self.storage.path('reports/test.json');atomic_json(path,{'status':'complete','data_date':'2026-10-02','candidates':candidates})
        md=self.storage.path('reports/test.md');md.write_text('Research')
        with self.database.session() as db:
            a=self.storage.register(db,'owner',path,'reports');m=self.storage.register(db,'owner',md,'reports')
            r=Report(owner_id='owner',job_id='test',data_date='2026-10-02',mode='historical_snapshot',quality='complete',artifact_id=a.id,markdown_id=m.id,
                     summary={'candidate_count':len(candidates)})
            db.add(r);db.flush();return r.id

    def test_session_cookie_csrf_revocation_and_no_store(self):
        response=self.client.post('/api/v1/auth/session',headers={**self.auth,'Origin':'https://scanner.test'})
        self.assertEqual(response.status_code,200)
        self.assertIn('HttpOnly',response.headers['set-cookie']);self.assertIn('Secure',response.headers['set-cookie']);self.assertIn('SameSite=strict',response.headers['set-cookie'])
        self.assertEqual(self.client.get('/api/v1/me').status_code,200)
        self.assertEqual(self.client.get('/api/v1/me').headers['cache-control'],'no-store')
        self.assertEqual(self.client.post('/api/v1/portfolios',json={'name':'Test'}).status_code,403)
        headers={'Origin':'https://scanner.test','X-Scanner-CSRF':response.json()['csrf_token']}
        self.assertEqual(self.client.post('/api/v1/portfolios',json={'name':'Test'},headers=headers).status_code,201)
        self.assertEqual(self.client.post('/api/v1/portfolios',json={'name':'Bad'},headers={**headers,'Origin':'https://evil.test'}).status_code,403)
        self.assertEqual(self.client.delete('/api/v1/auth/session',headers=headers).status_code,200)
        self.assertEqual(self.client.get('/api/v1/me').status_code,401)

    def test_session_expiry_and_token_rotation(self):
        self.client.post('/api/v1/auth/session',headers={**self.auth,'Origin':'https://scanner.test'})
        with self.database.session() as db:
            row=db.scalar(select(Policy).where(Policy.id.like('session:%')))
            self.assertNotIn(self.token,json.dumps(row.values))
            row.values={**row.values,'expires_at':(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat()}
        self.assertEqual(self.client.get('/api/v1/me').status_code,401)
        self.client.post('/api/v1/auth/session',headers={**self.auth,'Origin':'https://scanner.test'})
        rotated=TestClient(create_app(self.settings,self.database,token='other-token-'+('b'*40)),base_url='https://scanner.test')
        rotated.cookies.update(self.client.cookies)
        self.assertEqual(rotated.get('/api/v1/me').status_code,401);rotated.close()

    def test_wrong_origin_and_insecure_nonlocal_config_rejected(self):
        self.assertEqual(self.client.post('/api/v1/auth/session',headers={**self.auth,'Origin':'https://evil.test'}).status_code,403)
        with self.assertRaises(ValueError):Settings(data_dir=self.root/'data',browser_origin='http://192.168.1.2',browser_secure_cookie=False)

    def test_split_consistency_indicators_and_daily_change_not_screening_return(self):
        self.market(split=True);identity=self.report()
        r=self.client.get('/api/v1/market/tickers/AVT/bars?end_date=2026-10-02',headers=self.auth)
        self.assertEqual(r.status_code,200);data=r.json()
        self.assertEqual(len(data['bars']),260);self.assertEqual(data['bars'][0]['close'],100)
        self.assertEqual(data['bars'][0]['volume'],1000);self.assertEqual(len(data['indicators']['sma200']),61)
        move=self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':'1D'})
        self.assertEqual(move.status_code,200)
        self.assertAlmostEqual(move.json()['items'][0]['change_percent'],(125.9/125.8-1)*100)
        self.assertNotEqual(move.json()['items'][0]['change_percent'],63)

    def test_gaps_are_not_zero_and_future_sessions_rejected(self):
        self.market();identity=self.report();self.storage.path(f'market/raw/grouped/{self.days[-2]}.json.gz').unlink()
        data=self.client.get('/api/v1/market/tickers/AVT/bars?end_date=2026-10-02',headers=self.auth).json()
        self.assertEqual(len(data['bars']),259);self.assertEqual(data['quality'],'partial_coverage')
        move=self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':'1D'}).json()
        self.assertIsNone(move['items'][0]['change_percent']);self.assertEqual(move['items'][0]['quality'],'insufficient_history')
        self.assertEqual(self.client.get('/api/v1/market/tickers/AVT/bars?end_date=2099-01-01',headers=self.auth).status_code,422)

    def test_historical_cutoff_does_not_apply_later_split(self):
        self.market(split=True)
        end=self.days[-2];first=sessions_ending(end)[0]
        # The first required warmup bar is absent, but available prices remain usable.
        atomic_json(self.storage.path(f'market/raw/splits/{first}_2026-10-02.json.gz'),{
            'first':first,'last':'2026-10-02','results':[{'ticker':'AVT','execution_date':'2026-10-02','split_from':1,'split_to':2}]})
        data=self.client.get(f'/api/v1/market/tickers/AVT/bars?end_date={end}',headers=self.auth).json()
        self.assertEqual(data['bars'][-1]['close'],251.6)
        self.assertEqual(data['adjustment_cutoff'],end)

    def test_context_version_owner_scope_and_explicit_vision_permission(self):
        identity=self.report()
        packet=self.client.post('/api/v1/agent/context',headers=self.auth,json={'task_type':'daily_review','prompt':'Compare candidates','report_ids':[identity],'end_date':'2026-10-02'}).json()
        self.assertEqual(packet['schema_version'],1);self.assertIn(identity,packet['source_ids']);self.assertIn('relative_strength',packet['semantics'])
        image=io.BytesIO();Image.new('RGB',(4,4)).save(image,format='PNG')
        upload=self.client.post('/api/v1/uploads',headers=self.auth,files={'file':('test.png',image.getvalue(),'image/png')}).json()['upload_id']
        body={'task_type':'document_review','prompt':'Read this image','upload_ids':[upload]}
        self.assertEqual(self.client.post('/api/v1/agent/context',headers=self.auth,json=body).status_code,422)
        packet=self.client.post('/api/v1/agent/context',headers=self.auth,json={**body,'allow_uploaded_documents':True}).json()
        self.assertIn(upload,packet['source_ids']);self.assertEqual(packet['images'][0]['id'],upload)
        self.assertNotIn('path',packet['images'][0])

    def test_journal_decimal_transport_is_exact(self):
        p=self.client.post('/api/v1/portfolios',headers=self.auth,json={'name':'Precise'}).json()['id']
        self.client.post(f'/api/v1/portfolios/{p}/transactions',headers=self.auth,json={'type':'opening','at':'2026-10-02T14:00:00Z','symbol':'AVT','quantity':'0.1234567891','price':'55.1234567891','fees':'0','currency':'USD'})
        rows=self.client.get(f'/api/v1/portfolios/{p}/transactions',headers=self.auth).json()
        self.assertEqual(rows[0]['quantity'],'0.1234567891');self.assertEqual(rows[0]['price'],'55.1234567891')

    def test_default_weekly_context_uses_completed_week_and_explicit_dates_allow_partial_week(self):
        body={'task_type':'weekly_review','prompt':'Review the latest completed week'}
        with patch('apps.server.services.market.expected_session',return_value='2026-09-30'):
            packet=self.client.post('/api/v1/agent/context',headers=self.auth,json=body).json()
            self.assertEqual((packet['start_date'],packet['end_date']),('2026-09-21','2026-09-25'))
            packet=self.client.post('/api/v1/agent/context',headers=self.auth,json={**body,'end_date':'2026-09-30'}).json()
            self.assertEqual((packet['start_date'],packet['end_date']),('2026-09-28','2026-09-30'))

    def test_cold_restore_ids_include_catalogued_split_references_and_exclude_other_owners(self):
        with self.database.session() as db:
            split=Artifact(owner_id='owner',dataset='reference',path='market/raw/splits/window.json.gz',sha256='0'*64,size=10,status='cold')
            other=Artifact(owner_id='other',dataset='reference',path='market/raw/splits/other.json.gz',sha256='0'*64,size=10,status='cold')
            ticker=Artifact(owner_id='owner',dataset='reference',path='market/raw/tickers/window.json.gz',sha256='0'*64,size=10,status='cold')
            db.add_all([split,other,ticker]);db.flush()
            self.assertEqual(restore_ids(db,'owner',self.days),[split.id])

    def test_short_movement_does_not_replace_full_chart_history(self):
        from stock_scanner.market import load_market
        self.market();identity=self.report(extra=True)
        with patch('apps.server.services.market.load_market',wraps=load_market) as loader:
            self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':'1D'})
            response=self.client.get('/api/v1/market/tickers/AVT/bars?end_date=2026-10-02',headers=self.auth)
            self.assertEqual(response.status_code,200);self.assertEqual(len(response.json()['bars']),260)
            self.assertEqual([len(call.args[1]) for call in loader.call_args_list],[2,260])
            monthly=self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':'1M'})
            self.assertEqual(monthly.status_code,200)
            rows={row['symbol']:row for row in monthly.json()['items']}
            self.assertAlmostEqual(rows['AVT']['change_percent'],(125.9/123.8-1)*100)
            self.assertIsNone(rows['ABC']['change_percent'])

    def test_movement_reads_only_its_period_and_keeps_split_adjustment(self):
        from stock_scanner.market import load_market
        self.market(split=True);identity=self.report()
        with patch('apps.server.services.market.load_market',wraps=load_market) as loader:
            for period,count in [('1D',2),('1W',6),('1M',22)]:
                response=self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':period})
                self.assertEqual(response.status_code,200)
                self.assertAlmostEqual(response.json()['items'][0]['change_percent'],(125.9/(125.9-(count-1)/10)-1)*100)
            self.assertEqual([len(call.args[1]) for call in loader.call_args_list],[2,6,22])

    def test_full_chart_cache_reuses_columns_for_short_movement(self):
        from stock_scanner.market import load_market
        self.market(split=True);identity=self.report()
        with patch('apps.server.services.market.load_market',wraps=load_market) as loader:
            self.assertEqual(self.client.get('/api/v1/market/tickers/AVT/bars?end_date=2026-10-02',headers=self.auth).status_code,200)
            response=self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':'1M'})
            self.assertEqual(response.status_code,200)
            self.assertEqual(loader.call_count,1)
            self.assertAlmostEqual(response.json()['items'][0]['change_percent'],(125.9/123.8-1)*100)

    def test_old_invalid_bar_does_not_block_recent_movement(self):
        self.market();identity=self.report()
        path=self.storage.path(f'market/raw/grouped/{self.days[0]}.json.gz')
        from stock_scanner.storage import read_json
        document=read_json(path);document['data']['results'][0]['c']=-1
        atomic_json(path,document)
        chart=self.client.get('/api/v1/market/tickers/AVT/bars?end_date=2026-10-02',headers=self.auth)
        self.assertEqual(chart.status_code,200);self.assertEqual(chart.json()['quality'],'partial_coverage')
        response=self.client.post('/api/v1/market/movement-snapshots',headers=self.auth,json={'scope':'candidates','report_id':identity,'period':'1D'})
        self.assertEqual(response.status_code,200)
        self.assertAlmostEqual(response.json()['items'][0]['change_percent'],(125.9/125.8-1)*100)
