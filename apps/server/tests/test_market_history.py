from datetime import datetime, timezone
from unittest.mock import patch
from types import SimpleNamespace

from stock_scanner.storage import atomic_json
from stock_scanner.provider import ProviderError
from apps.server.services.market_history import plan_history, acquire
from apps.server.workers.runtime import execute_one
from test_server import ServerCase


class HistoryTests(ServerCase):
    def test_two_calendar_years_and_persistent_older_cache(self):
        with patch('apps.server.services.market_history.datetime') as clock:
            clock.now.return_value = datetime(2026,10,9,7,tzinfo=timezone.utc)
            plan = plan_history(self.storage,self.settings)
        self.assertEqual(plan['first_session'],'2024-10-09')
        self.assertEqual(plan['last_session'],'2026-10-08')
        self.assertGreater(plan['required_sessions'],490)
        self.assertLess(plan['required_sessions'],520)
        path=self.storage.path('market/raw/grouped/2023-10-09.json.gz')
        atomic_json(path,{'original':True})
        with patch('apps.server.services.market_history.datetime') as clock:
            clock.now.return_value=datetime(2026,10,9,7,tzinfo=timezone.utc)
            data=self.client.get('/api/v1/market/history').json()
        self.assertEqual(data['oldest_retained_session'],'2023-10-09')
        self.assertTrue(path.exists())

    def test_missing_only_and_exact_failure_checkpoint(self):
        target={'sessions':['2026-10-07','2026-10-08']}
        identity=self.post_job('market_backfill',{'history_plan':target})
        calls=[]
        def grouped(client,sessions,progress):
            calls.extend(sessions)
            if sessions==['2026-10-07']:raise ProviderError(403,'/grouped/2026-10-07','Not entitled')
            atomic_json(client.state/'raw/grouped/2026-10-08.json.gz',{'session':'2026-10-08'})
        with patch('apps.server.services.market_history.Client',return_value=SimpleNamespace(state=self.storage.path('market'))),patch('apps.server.services.market_history.ensure_grouped',side_effect=grouped):
            execute_one('scanner',acquire,self.database,self.settings)
        job=self.job(identity)
        self.assertEqual(job.status,'failed')
        self.assertEqual(calls,['2026-10-08','2026-10-07'])
        self.assertEqual(job.progress['cached_sessions'],1)
        self.assertEqual(job.progress['source_errors'][0]['http_status'],403)
        self.assertFalse(execute_one('scanner',acquire,self.database,self.settings))

    def test_backfill_replay_is_stable_while_the_cache_grows(self):
        with patch('apps.server.services.market_history.datetime') as clock:
            clock.now.return_value=datetime(2026,10,9,7,tzinfo=timezone.utc)
            first=self.client.post('/api/v1/market/history/backfills',headers={'Idempotency-Key':'same-history'})
            self.assertEqual(first.status_code,202,first.text)
            atomic_json(self.storage.path('market/raw/grouped/2026-10-08.json.gz'),{'session':'2026-10-08'})
            again=self.client.post('/api/v1/market/history/backfills',headers={'Idempotency-Key':'same-history'})
            self.assertEqual(again.status_code,202,again.text)
            self.assertEqual(first.json()['job_id'],again.json()['job_id'])
