import io
import json
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import select

from apps.server.api.schemas import AgentRequest
from apps.server.errors import ServiceError
from apps.server.persistence.models import Artifact, Job, Report, Signal
from apps.server.workers.runtime import execute_one
from test_server import ServerCase


class FakeScanner:
    def __init__(self): self.calls = []; self.block = '2026-10-01'
    def run(self, state, rules, session, mode, research, offline=False, progress_callback=None):
        self.calls.append(session)
        directory = state/'runs'/f'{session}-{len(self.calls)}'; directory.mkdir(parents=True, mode=0o700)
        result = {'status': 'blocked_provider' if session == self.block else 'complete', 'coverage': {'evaluated': 1},
                  'candidates': [] if session == self.block else [{'symbol': 'ABC', 'close': 10, 'pivot': 9.9}],
                  'errors': [{'http_status':403, 'message':'Not entitled'}] if session == self.block else []}
        (directory/'report.json').write_text(json.dumps(result)); (directory/'report.md').write_text('# Scan\n')
        return directory, result


class ScannerWorkerTests(ServerCase):
    def test_resume_keeps_completed_dates_and_reconstructed_signals_separate(self):
        from apps.server.workers.scanner.handler import scan
        request = {'mode':'historical_snapshot','start_date':'2026-09-30','end_date':'2026-10-02','research':'none'}
        identity = self.post_job('scan', request)
        adapter = FakeScanner()
        execute_one('scanner', lambda c: scan(c,adapter), self.database, self.settings)
        self.assertEqual(self.job(identity).status,'failed')
        self.assertEqual(self.job(identity).progress['completed_sessions'],['2026-09-30'])
        self.client.post(f'/api/v1/jobs/{identity}/resume')
        adapter.block = None
        execute_one('scanner', lambda c: scan(c,adapter), self.database, self.settings)
        self.assertEqual(self.job(identity).status,'succeeded', self.job(identity).error)
        self.assertEqual(adapter.calls.count('2026-09-30'),1)
        with self.database.session() as db:
            self.assertEqual(len(list(db.scalars(select(Signal)))),3)
            self.assertEqual(set(db.scalars(select(Signal.mode))), {'historical_snapshot'})
            self.assertEqual(len(list(db.scalars(select(Report)))),3)

    def test_cold_warmup_waits_for_restore(self):
        from apps.server.workers.scanner.handler import scan
        from stock_scanner.calendar import sessions_ending
        day = sessions_ending('2026-10-02')[0]
        with self.database.session() as db:
            row = Artifact(owner_id='owner',dataset='grouped',path=f'market/raw/grouped/{day}.json.gz',sha256='0'*64,
                           size=10,status='cold',archive_id='coldarchive',metadata_={'session':day})
            db.add(row)
        identity = self.post_job('scan', {'mode':'historical_snapshot','start_date':'2026-10-02','end_date':'2026-10-02'})
        execute_one('scanner', lambda c: scan(c,FakeScanner()), self.database, self.settings)
        self.assertEqual(self.job(identity).status, 'waiting_for_archive')
        self.assertEqual(len(self.job(identity).progress['restore_artifact_ids']),1)

    def test_historical_research_uses_distinct_cache_and_date_cutoff(self):
        from stock_scanner.research import Researcher
        class Client:
            state = self.root
            calls = []
            def get(self, path, params=None):
                self.calls.append((path,params))
                return {'results':{} if path.startswith('/v3/reference/tickers/') else []}
        client = Client()
        with patch('stock_scanner.research.sec_company_facts', return_value={'error':{'http_status':403}}):
            researcher = Researcher(client,'2026-09-28',knowledge_cutoff='2026-09-28T20:30:00+00:00')
            result = researcher.candidate({'symbol':'ABC'})
        news = next(p for path,p in client.calls if path=='/v2/reference/news')
        self.assertEqual(news['published_utc.lte'],'2026-09-28T20:30:00+00:00')
        self.assertFalse(any(path=='/benzinga/v1/earnings' for path,p in client.calls))
        self.assertIn('historical-',researcher.cache_scope)


class FakeAnalyst:
    def analyze(self, workspace, request, checkpoint):
        self.inputs = json.loads((workspace/'inputs.json').read_text())
        assert (workspace/'AGENTS.md').is_file()
        return {'markdown':'# Source review\n','sources':self.inputs['source_ids'],'gaps':['Limited source coverage']}


class AgentWorkerTests(ServerCase):
    def report(self, mode='historical_snapshot'):
        path = self.storage.path('reports/source.json'); path.parent.mkdir(parents=True,mode=0o700)
        path.write_text(json.dumps({'data_date':'2026-10-02','status':'partial_coverage','candidates':[]}))
        with self.database.session() as db:
            artifact = self.storage.register(db,'owner',path,'reports')
            row = Report(owner_id='owner',job_id='sourcejob',data_date='2026-10-02',mode=mode,quality='partial_coverage',
                         artifact_id=artifact.id,markdown_id=artifact.id,summary={})
            db.add(row);db.flush();return row.id

    def test_only_authorized_sources_copied_and_workspace_removed(self):
        from apps.server.workers.codex.handler import handle
        report = self.report(); adapter = FakeAnalyst()
        request = AgentRequest(task_type='daily_review',prompt='Review the date.', report_ids=[report]).model_dump(mode='json')
        identity = self.post_job('agent',request)
        execute_one('codex',lambda c: handle(c,adapter),self.database,self.settings)
        self.assertEqual(self.job(identity).status,'succeeded', self.job(identity).error)
        self.assertEqual(adapter.inputs['source_ids'],[report])
        self.assertFalse(self.storage.path('job-workspaces/'+identity).exists())

    def test_portfolio_report_cannot_bypass_export_permission(self):
        from apps.server.workers.codex.handler import handle
        report = self.report(mode='portfolio')
        request = AgentRequest(task_type='daily_review',prompt='Review.',report_ids=[report]).model_dump(mode='json')
        identity = self.post_job('agent',request)
        execute_one('codex',lambda c: handle(c,FakeAnalyst()),self.database,self.settings)
        self.assertEqual(self.job(identity).error['code'],'portfolio_export_denied')


class ExtractionTests(ServerCase):
    def test_real_image_ocr_produces_review_only_text(self):
        from PIL import Image,ImageDraw,ImageFont
        from apps.server.adapters.extraction import LocalExtractor
        workspace = self.storage.path('job-workspaces/ocr');workspace.mkdir(parents=True,mode=0o700)
        image = Image.new('RGB',(1000,250),'white')
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',32)
        ImageDraw.Draw(image).text((20,30),'BUY ABC 10 SHARES AT 25 USD',font=font,fill='black')
        source = workspace/'source.png';image.save(source)
        result = LocalExtractor(self.settings).extract(source,'image/png',workspace)
        self.assertIn('ABC',result['pages'][0]['text'])
        self.assertTrue(result['requires_confirmation'])
        self.assertEqual(result['rows'][0]['recognized']['symbol'],'ABC')
        self.assertTrue(result['rows'][0]['errors'])
