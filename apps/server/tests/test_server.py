import hashlib
import io
import json
import secrets
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select

from apps.server.api.app import create_app
from apps.server.config import Settings
from apps.server.errors import ServiceError
from apps.server.persistence.database import Database
from apps.server.persistence.models import Artifact, Event, Import, Job, Portfolio, Report, Schedule, Signal, Transaction, now
from apps.server.services.jobs import Jobs, enqueue
from apps.server.services.storage import Storage
from apps.server.workers.runtime import execute_one
from apps.server.workers.scheduler.service import tick
from apps.server.workers.scheduler.triggers import next_occurrence


class ServerCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.key = self.root/"key"
        self.key.write_bytes(secrets.token_bytes(32))
        self.settings = Settings(data_dir=self.root/"data", archive_key_file=self.key, archive_evict=True)
        self.database = Database(url="sqlite:///"+str(self.root/"test.sqlite"))
        self.database.migrate()
        self.client = TestClient(create_app(self.settings, self.database, token="unit-test-only-token-"+"a"*40))
        self.client.headers["Authorization"] = "Bearer unit-test-only-token-"+"a"*40
        self.storage = Storage(self.settings)

    def tearDown(self):
        self.client.close()
        self.database.engine.dispose()
        self.temp.cleanup()

    def post_job(self, kind, payload, key=None):
        with self.database.session() as db:
            return enqueue(db, "owner", kind, payload, key).id

    def job(self, identity):
        with self.database.session() as db:
            return db.get(Job, identity)

    def portfolio(self):
        r = self.client.post("/api/v1/portfolios", json={"name": "Research"})
        self.assertEqual(r.status_code, 201)
        return r.json()["id"]


class ApiTests(ServerCase):
    def test_reports_same_session_are_ordered_by_publication_and_paginated_consistently(self):
        published = datetime(2026,10,5,10,tzinfo=timezone.utc)
        identities=[]
        for name,quality,stamp in [('old','blocked_error',published-timedelta(hours=1)),('new','partial_coverage',published)]:
            path=self.storage.path(f'reports/{name}.json');path.parent.mkdir(parents=True,exist_ok=True)
            path.write_text(json.dumps({'status':quality}))
            with self.database.session() as db:
                artifact=self.storage.register(db,'owner',path,'reports');artifact.created_at=stamp
                row=Report(owner_id='owner',job_id=name,data_date='2026-10-02',mode='live',quality=quality,
                           artifact_id=artifact.id,markdown_id=artifact.id,summary={'candidate_count':0 if name=='old' else 2})
                db.add(row);db.flush();identities.append(row.id)
        reports=self.client.get('/api/v1/reports').json()
        self.assertEqual([report['id'] for report in reports],list(reversed(identities)))
        self.assertEqual(reports[0]['summary']['candidate_count'],2)
        for offset,identity in enumerate(reversed(identities)):
            self.assertEqual(self.client.get('/api/v1/reports',params={'limit':1,'offset':offset}).json()[0]['id'],identity)

    def test_auth_and_owner_boundary(self):
        self.assertEqual(self.client.get("/api/v1/health/live", headers={"Authorization": ""}).status_code, 200)
        self.assertEqual(self.client.get("/api/v1/jobs", headers={"Authorization": ""}).status_code, 401)
        with self.database.session() as db:
            row = Portfolio(owner_id="other", name="Private", currency="USD")
            db.add(row); db.flush(); identity = row.id
        self.assertEqual(self.client.get(f"/api/v1/portfolios/{identity}/positions").status_code, 404)
        self.assertEqual(self.client.get("/api/v1/openapi.json").status_code, 200)

    def test_daily_idempotency_conflict_and_range_semantics(self):
        body = {"mode": "historical_snapshot", "start_date": "2026-09-28", "end_date": "2026-10-02"}
        plan = self.client.post("/api/v1/scan-plans", json=body)
        self.assertEqual(plan.status_code, 200)
        self.assertEqual(len(plan.json()["sessions"]), 5)
        self.assertEqual(len(plan.json()["required_sessions"]), 264)
        r = self.client.post("/api/v1/scans", json=body, headers={"Idempotency-Key": "same"})
        self.assertEqual(r.status_code, 202)
        repeated = self.client.post("/api/v1/scans", json=body, headers={"Idempotency-Key": "same"})
        self.assertEqual(r.json()["job_id"], repeated.json()["job_id"])
        body["offline"] = True
        self.assertEqual(self.client.post("/api/v1/scans", json=body, headers={"Idempotency-Key": "same"}).status_code, 409)
        self.assertEqual(self.client.post("/api/v1/scans", json={"mode": "live", "start_date": "2026-09-28", "end_date": "2026-10-02"}).status_code, 422)

    def test_historical_research_and_future_dates_rejected(self):
        r = self.client.post("/api/v1/scans", json={"mode": "historical_snapshot", "research": "current"})
        self.assertEqual(r.status_code, 422)
        r = self.client.post("/api/v1/scan-plans", json={"mode": "historical_snapshot", "start_date": "2099-01-01", "end_date": "2099-01-02"})
        self.assertEqual(r.status_code, 422)
        r = self.client.get("/api/v1/market/coverage?start_date=wrong&end_date=wrong")
        self.assertEqual(r.status_code, 422)

    def test_cancel_resume_events_and_stream(self):
        identity = self.post_job("scan", {})
        self.assertEqual(self.client.post(f"/api/v1/jobs/{identity}/cancel").json()["status"], "cancelled")
        self.assertEqual(self.client.post(f"/api/v1/jobs/{identity}/resume").json()["status"], "queued")
        jobs = Jobs(self.database, self.settings); row = jobs.claim("scanner")
        jobs.finish(row.id, row.lease_token, "succeeded", {"ok": True})
        response = self.client.get(f"/api/v1/jobs/{identity}/events/stream")
        self.assertEqual(response.status_code, 200)
        self.assertIn("job_succeeded", response.text)

    def test_storage_policy_validated_and_persisted(self):
        self.assertEqual(self.client.patch("/api/v1/storage/policy", json={"limits": {"capacity_bytes": 100}}).status_code, 422)
        r = self.client.patch("/api/v1/storage/policy", json={"archive_after_days": 60, "limits": {"restore_ttl_days": 14}})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self.client.get("/api/v1/storage/status").json()["policy"]["restore_ttl_days"], 14)
        self.assertEqual(self.client.patch("/api/v1/storage/policy", json={"limits":{"upload_bytes":30_000_000}}).json()["error"]["code"], "upload_restart_required")

    def test_invalid_schedule_fields_return_typed_error(self):
        for trigger in [{"type":"local_cron","timezone":"Unknown/Nowhere","expression":"0 9 * * *"},
                        {"type":"once"}, {"type":"once","at":"invalid"}]:
            r = self.client.post("/api/v1/schedules",json={"name":"Invalid","trigger":trigger,"task":{"type":"daily_scan"}})
            self.assertEqual(r.status_code,422)

    def test_agent_disabled_and_portfolio_export_requires_permission(self):
        self.assertEqual(self.client.post("/api/v1/agent/tasks", json={"task_type": "daily_review", "prompt": "Review sources"}).status_code, 503)
        self.assertEqual(self.client.post("/api/v1/agent/tasks", json={"task_type": "portfolio_review", "prompt": "Review", "portfolio_id": "x"}).status_code, 422)


class QueueTests(ServerCase):
    def test_lease_expiry_and_fencing(self):
        identity = self.post_job("scan", {})
        jobs = Jobs(self.database, self.settings)
        first = jobs.claim("scanner")
        with self.database.session() as db:
            db.get(Job, identity).lease_until = now()-timedelta(seconds=1)
        second = jobs.claim("scanner")
        self.assertNotEqual(first.lease_token, second.lease_token)
        jobs.finish(identity, first.lease_token, "succeeded", {"wrong": True})
        self.assertEqual(self.job(identity).status, "running")
        jobs.finish(identity, second.lease_token, "succeeded", {"correct": True})
        self.assertEqual(self.job(identity).result, {"correct": True})

    def test_provider_error_is_not_automatically_retried(self):
        identity = self.post_job("scan", {})
        def fail(context): raise ServiceError("provider_403", "Provider entitlement denied")
        execute_one("scanner", fail, self.database, self.settings)
        self.assertEqual(self.job(identity).status, "failed")
        self.assertFalse(execute_one("scanner", fail, self.database, self.settings))


class SchedulerTests(ServerCase):
    def test_local_dst_gap_and_repeat(self):
        trigger = {"type": "local_cron", "expression": "30 2 * * *", "timezone": "America/New_York"}
        at, skipped = next_occurrence(trigger, datetime(2026, 3, 8, 5, tzinfo=timezone.utc), self.settings)
        self.assertEqual(at.date().isoformat(), "2026-03-09")
        self.assertEqual(skipped, ["2026-03-08T02:30:00"])
        trigger["expression"] = "30 1 * * *"
        at, _ = next_occurrence(trigger, datetime(2026, 11, 1, 4, tzinfo=timezone.utc), self.settings)
        self.assertEqual(at.hour, 5)
        next_, _ = next_occurrence(trigger, at, self.settings)
        self.assertEqual(next_.date().isoformat(), "2026-11-02")

    def test_early_close_and_weekly_holiday(self):
        at, _ = next_occurrence({"type": "market_close"}, datetime(2026, 11, 27, 14, tzinfo=timezone.utc), self.settings)
        self.assertEqual(at.isoformat(), "2026-11-27T18:30:00+00:00")
        at, _ = next_occurrence({"type": "market_close", "frequency": "weekly"}, datetime(2026, 4, 2, 12, tzinfo=timezone.utc), self.settings)
        self.assertEqual(at.date().isoformat(), "2026-04-02")

    def test_occurrence_persisted_once_and_restart(self):
        at = datetime(2026, 10, 2, 20, 30, tzinfo=timezone.utc)
        with self.database.session() as db:
            row = Schedule(owner_id="owner", name="Daily", trigger={"type": "market_close"}, task={"type": "daily_scan"}, enabled=True, next_at=at, missed_policy="run_once")
            db.add(row); db.flush(); identity = row.id
        self.assertEqual(tick(self.database, self.settings, at+timedelta(seconds=1)), 1)
        self.assertEqual(tick(self.database, self.settings, at+timedelta(seconds=2)), 0)
        with self.database.session() as db:
            self.assertEqual(len(list(db.scalars(select(Job)))), 1)
        response = self.client.get(f"/api/v1/schedules/{identity}/occurrences")
        self.assertEqual(len(response.json()), 1)

    def test_schedule_api_edits_and_disabled_state(self):
        r = self.client.post("/api/v1/schedules", json={"name": "Archive", "trigger": {"type": "local_cron", "expression": "0 2 1 * *"}, "task": {"type": "archive_completed_months"}, "enabled": False})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.client.patch('/api/v1/schedules/'+r.json()['id'], json={"enabled": True}).status_code, 200)
        self.assertEqual(self.client.post("/api/v1/schedules", json={"name": "Bad", "trigger": {"type": "shell"}, "task": {"type": "execute"}}).status_code, 422)


class PortfolioTests(ServerCase):
    def tx(self, identity, type_, **kwargs):
        return self.client.post(f"/api/v1/portfolios/{identity}/transactions", json={"type": type_, "at": "2026-09-28T17:00:00-04:00", "currency": "USD", **kwargs})

    def test_fifo_fees_split_and_negative_position(self):
        p = self.portfolio()
        self.assertEqual(self.tx(p, "buy", symbol="ABC", quantity="10", price="10", fees="2").status_code, 201)
        self.assertEqual(self.tx(p, "split", symbol="ABC", quantity="2").status_code, 201)
        self.assertEqual(self.tx(p, "sell", symbol="ABC", quantity="5", price="8", fees="1").status_code, 201)
        result = self.client.get(f"/api/v1/portfolios/{p}/positions").json()
        self.assertEqual(__import__('decimal').Decimal(result['realized_pnl']), __import__('decimal').Decimal('13.5'))
        self.assertEqual(__import__('decimal').Decimal(result['positions'][0]['quantity']), 15)
        self.assertEqual(self.tx(p, "sell", symbol="ABC", quantity="16", price="8").status_code, 422)
        with self.database.session() as db:
            self.assertEqual(len(list(db.scalars(select(Transaction)))), 3)

    def test_unknown_opening_basis_remains_unknown(self):
        p = self.portfolio()
        self.assertEqual(self.tx(p, "opening", symbol="ABC", quantity="10").status_code, 201)
        self.assertEqual(self.tx(p, "sell", symbol="ABC", quantity="2", price="10").status_code, 201)
        result = self.client.get(f"/api/v1/portfolios/{p}/positions").json()
        self.assertIsNone(result['realized_pnl'])
        self.assertIsNone(result['positions'][0]['cost_basis'])

    def test_duplicate_external_reference_and_auditable_correction(self):
        p = self.portfolio()
        r = self.tx(p, "buy", symbol="ABC", quantity="10", price="10", external_ref="broker-row")
        self.assertEqual(self.tx(p, "buy", symbol="ABC", quantity="10", price="10", external_ref="broker-row").status_code, 409)
        corrected = self.client.post(f"/api/v1/portfolios/{p}/transactions/{r.json()['id']}/corrections", json={"type": "buy", "at": "2026-09-28T17:00:00-04:00", "symbol": "ABC", "quantity": "8", "price": "10", "currency": "USD"})
        self.assertEqual(corrected.status_code, 201)
        history = self.client.get(f"/api/v1/portfolios/{p}/transactions").json()
        self.assertEqual(len(history), 2)
        self.assertEqual(sum(r['superseded'] for r in history), 1)


class ImportTests(ServerCase):
    def test_csv_review_confirm_idempotency_and_no_automatic_writes(self):
        from apps.server.workers.imports.handler import handle
        p = self.portfolio()
        csv = b"type,at,symbol,quantity,price,currency\nbuy,2026-09-28T17:00:00-04:00,ABC,2,10,USD\n"
        upload = self.client.post("/api/v1/uploads", files={"file": ("transaction.csv", csv, "text/csv")})
        self.assertEqual(upload.status_code, 201)
        body = {"upload_id": upload.json()["upload_id"], "portfolio_id": p}
        r = self.client.post("/api/v1/imports", json=body, headers={"Idempotency-Key": "import"})
        repeat = self.client.post("/api/v1/imports", json=body, headers={"Idempotency-Key": "import"})
        self.assertEqual(r.json()["import_id"], repeat.json()["import_id"])
        execute_one("imports", handle, self.database, self.settings)
        imported = self.client.get('/api/v1/imports/'+r.json()['import_id']).json()
        self.assertEqual(imported['status'], 'awaiting_review')
        self.assertEqual(self.client.get(f'/api/v1/portfolios/{p}/transactions').json(), [])
        reviewed = {"rows": [imported['proposal']['rows'][0]['transaction']]}
        first = self.client.post('/api/v1/imports/'+r.json()['import_id']+'/confirm', json=reviewed)
        self.assertEqual(first.status_code, 200)
        self.assertEqual(self.client.post('/api/v1/imports/'+r.json()['import_id']+'/confirm', json=reviewed).json(), first.json())
        self.assertEqual(len(self.client.get(f'/api/v1/portfolios/{p}/transactions').json()), 1)

    def test_upload_signature_limit_and_import_rejection(self):
        r = self.client.post('/api/v1/uploads', files={'file': ('bad.png', b'not an image', 'image/png')})
        self.assertEqual(r.status_code, 422)
        self.client.patch('/api/v1/storage/policy', json={'limits': {'upload_bytes': 10}})
        r = self.client.post('/api/v1/uploads', files={'file': ('big.csv', b'a'*11, 'text/csv')})
        self.assertEqual(r.status_code, 413)
        with self.database.session() as db:
            self.assertEqual(len(list(db.scalars(select(Artifact)))), 0)


class MemoryCloud:
    durable = True
    def __init__(self): self.objects = {}; self.fail_verify = False
    def put(self, key, source): self.objects[key] = Path(source).read_bytes()
    def verify(self, key, digest, size):
        if self.fail_verify or hashlib.sha256(self.objects[key]).hexdigest() != digest or len(self.objects[key]) != size:
            raise ServiceError('remote_checksum', 'Remote verification failed')
    def download(self, key, destination, max_bytes):
        assert len(self.objects[key]) <= max_bytes
        Path(destination).write_bytes(self.objects[key])


class ArchiveTests(ServerCase):
    def artifact(self):
        p = self.storage.path('uploads/owner/original.csv'); p.parent.mkdir(parents=True, mode=0o700)
        p.write_bytes(b'private-original-data\n'*1000)
        with self.database.session() as db:
            row = self.storage.register(db, 'owner', p, 'uploads')
            row.created_at = now()-timedelta(days=90)
            return row.id, p

    def test_encrypt_verify_evict_restore_and_repeat(self):
        from apps.server.workers.storage.handler import archive, restore
        store = MemoryCloud(); identity, original = self.artifact(); expected = original.read_bytes()
        job = self.post_job('archive', {})
        execute_one('storage', lambda c: archive(c, store), self.database, self.settings)
        self.assertEqual(self.job(job).status, 'succeeded', self.job(job).error)
        self.assertFalse(original.exists())
        self.assertNotIn(expected, next(iter(store.objects.values())))
        restore_id = self.post_job('restore', {'artifact_ids': [identity]})
        execute_one('storage', lambda c: restore(c, store), self.database, self.settings)
        self.assertEqual(self.job(restore_id).status, 'succeeded', self.job(restore_id).error)
        self.assertEqual(original.read_bytes(), expected)
        repeat = self.post_job('archive', {})
        execute_one('storage', lambda c: archive(c, store), self.database, self.settings)
        self.assertEqual(self.job(repeat).result['archive_ids'], [])
        self.assertTrue(original.exists(), 'Restored files are pinned by TTL')

    def test_failed_remote_verification_retains_original(self):
        from apps.server.workers.storage.handler import archive
        store = MemoryCloud(); store.fail_verify = True
        identity, original = self.artifact()
        job = self.post_job('archive', {})
        execute_one('storage', lambda c: archive(c, store), self.database, self.settings)
        self.assertEqual(self.job(job).status, 'failed')
        self.assertTrue(original.exists())
        with self.database.session() as db:
            self.assertIsNone(db.get(Artifact, identity).archive_id)

    def test_authenticated_encryption_rejects_tampering(self):
        from apps.server.adapters.encryption import Encryption
        e = Encryption(self.key); plain, encrypted, result = [self.root/n for n in ['plain','encrypted','result']]
        plain.write_bytes(b'confidential'*100)
        e.encrypt(plain, encrypted)
        b = bytearray(encrypted.read_bytes()); b[40] ^= 1; encrypted.write_bytes(b)
        with self.assertRaises(ServiceError): e.decrypt(encrypted, result)
        self.assertFalse(result.exists())

    def test_reservations_reject_overcommit_and_paths(self):
        from apps.server.config import Limits
        limits = Limits(capacity_bytes=2_000_000, target_bytes=1_000_000, archive_trigger_bytes=1_400_000,
                        admission_stop_bytes=1_800_000, upload_bytes=10000)
        self.storage = Storage(self.settings.model_copy(update={"limits": limits}))
        with self.database.session() as db:
            self.storage.reserve(db, 'one', 'owner', 1_000_000)
        with self.database.session() as db:
            with self.assertRaises(ServiceError): self.storage.reserve(db, 'two', 'owner', 1_000_000)
        for path in ['../outside','/etc/passwd']:
            with self.assertRaises(ServiceError): self.storage.path(path)


if __name__ == '__main__':
    unittest.main()
