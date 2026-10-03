from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from sqlalchemy import select

from apps.server.persistence.models import Archive, Report
from apps.server.services.recovery import recover
from apps.server.errors import ServiceError, Cancelled
from apps.server.workers.runtime import execute_one
from stock_scanner.storage import atomic_json
from test_server import ServerCase, MemoryCloud


class RecoveryTests(ServerCase):
    def test_cancelled_database_dump_kills_child_and_removes_partial_file(self):
        from apps.server.workers.storage.handler import backup
        password = self.root/"password";password.write_text("fixture-only")
        settings = self.settings.model_copy(update={"database_password_file":password})
        class Child:
            stopped = False
            returncode = None
            def poll(self):return 0 if self.stopped else None
            def terminate(self):self.stopped=True
            def wait(self,timeout=None):return 0
        child = Child()
        def cancel(**progress):raise Cancelled()
        context = SimpleNamespace(settings=settings, storage=self.storage,database=self.database,
                                  job=SimpleNamespace(id="cancelled-dump",owner_id="owner",attempts=1),checkpoint=cancel)
        with patch("apps.server.workers.storage.handler.subprocess.Popen",return_value=child):
            with self.assertRaises(Cancelled):backup(context)
        self.assertTrue(child.stopped)
        self.assertFalse(list(self.storage.path("backups").glob("*.dump")))

    def test_recovery_without_database_and_failed_hash_publishes_nothing(self):
        from apps.server.workers.storage.handler import archive
        path = self.storage.path("reports/old.json")
        path.parent.mkdir(parents=True, mode=0o700)
        path.write_text('{"status":"partial_coverage"}')
        original = path.read_bytes()
        with self.database.session() as db:
            artifact = self.storage.register(db, "owner", path, "reports")
            from datetime import timedelta
            from apps.server.persistence.models import now
            artifact.created_at = now()-timedelta(days=90)
        cloud = MemoryCloud()
        self.post_job("archive", {})
        execute_one("storage", lambda c: archive(c, cloud), self.database, self.settings)
        with self.database.session() as db:
            record = db.scalar(select(Archive))
        source = self.root/"download.aesgcm"
        cloud.download(record.object_key, source, record.size)
        result = recover(source, self.key, self.root/"recovered", expected_hash=record.sha256)
        self.assertEqual(result["members"], 1)
        self.assertEqual((self.root/"recovered"/record.manifest["members"][0]["id"]).read_bytes(), original)
        with self.assertRaises(ServiceError):
            recover(source, self.key, self.root/"failed", expected_hash="0"*64)
        self.assertFalse((self.root/"failed").exists())


class PortfolioPriceTests(ServerCase):
    def test_worker_crash_after_publication_resumes_existing_immutable_report(self):
        from apps.server.services.portfolios import analyze
        portfolio = self.portfolio()
        atomic_json(self.storage.path("market/raw/grouped/2026-10-02.json.gz"), {"session":"2026-10-02","adjusted":False,"data":{"adjusted":False,"results":[self.bar()]}})
        identity = self.post_job("portfolio_analysis",{"portfolio_id":portfolio,"data_date":"2026-10-02"})
        def crash(context):
            analyze(context)
            raise RuntimeError("Simulated worker loss before terminal job update")
        execute_one("scanner",crash,self.database,self.settings)
        with self.database.session() as db:
            first = db.scalar(select(Report).where(Report.job_id==identity)).id
        self.client.post(f"/api/v1/jobs/{identity}/resume")
        execute_one("scanner",analyze,self.database,self.settings)
        self.assertEqual(self.job(identity).result["report_id"],first)
        with self.database.session() as db:
            self.assertEqual(len(list(db.scalars(select(Report).where(Report.job_id==identity)))),1)

    def analysis(self, bar, splits=None):
        portfolio = self.portfolio()
        self.client.post(f"/api/v1/portfolios/{portfolio}/transactions", json={"type":"buy","at":"2026-09-28T14:00:00Z","symbol":"ABC","quantity":"10","price":"12"})
        # This actual after-close purchase must be absent from the valuation.
        self.client.post(f"/api/v1/portfolios/{portfolio}/transactions", json={"type":"buy","at":"2026-10-02T22:00:00Z","symbol":"ABC","quantity":"5","price":"13"})
        atomic_json(self.storage.path("market/raw/grouped/2026-10-02.json.gz"), {"session":"2026-10-02","adjusted":False,"data":{"adjusted":False,"results":[bar]}})
        if splits:
            atomic_json(self.storage.path("market/raw/splits/test.json.gz"), {"results":splits})
        identity = self.post_job("portfolio_analysis", {"portfolio_id":portfolio,"data_date":"2026-10-02"})
        from apps.server.services.portfolios import analyze
        execute_one("scanner", analyze, self.database, self.settings)
        self.assertEqual(self.job(identity).status, "succeeded", self.job(identity).error)
        with self.database.session() as db:
            report = db.scalar(select(Report).where(Report.job_id == identity))
        return self.client.get(f"/api/v1/reports/{report.id}/content?format=json").json()

    def bar(self):
        return {"T":"ABC","o":12,"h":14,"l":11,"c":13,"v":1000,"t":int(datetime(2026,10,2,4,tzinfo=timezone.utc).timestamp()*1000)}

    def test_close_cutoff_and_actual_fifo(self):
        result = self.analysis(self.bar())
        self.assertEqual(result["positions"][0]["quantity"], "10.0000000000")
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["positions"][0]["market_value"], "130.0000000000")

    def test_impossible_bar_never_produces_valuation(self):
        bar = self.bar(); bar["h"] = 5
        result = self.analysis(bar)
        self.assertEqual(result["status"], "partial_coverage")
        self.assertIsNone(result["positions"][0]["market_value"])

    def test_unrecorded_split_never_produces_misleading_pnl(self):
        result = self.analysis(self.bar(), [{"ticker":"ABC","execution_date":"2026-10-01","split_from":1,"split_to":2}])
        self.assertEqual(result["corporate_action_gaps"][0]["code"], "split_requires_reconciliation")
        self.assertIsNone(result["positions"][0]["unrealized_pnl"])
