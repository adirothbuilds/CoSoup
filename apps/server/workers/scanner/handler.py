import hashlib
import json
from dataclasses import asdict

from sqlalchemy import select

from stock_scanner.rules import Rules

from ...adapters.scanner import ExistingScanner
from ...errors import ServiceError
from ...persistence.models import Artifact, Report, Signal
from ...services.jobs import owned
from ...services.scans import plan


def scan(context, adapter=None):
    job, storage = context.job, context.storage
    with context.database.session() as db:
        planning = plan(db, storage, context.settings, job.owner_id, job.payload)
        storage.reserve(db, job.id, job.owner_id, context.settings.limits.scan_reservation_bytes)
    if planning["cold_sessions"]:
        context.jobs.checkpoint(job.id, job.lease_token, {"restore_artifact_ids": [x["artifact_id"] for x in planning["cold_sessions"]]})
        raise ServiceError("restore_required", "Warmup data is cold; restore the listed artifacts and resume")
    rules = Rules(**planning["rules"])
    adapter = adapter or ExistingScanner()
    completed = list(job.progress.get("completed_sessions", []))
    report_ids = list(job.progress.get("report_ids", []))
    for session in planning["sessions"]:
        if session in completed:
            continue
        context.checkpoint(completed_sessions=completed, report_ids=report_ids, current_session=session)
        with context.database.session() as db:
            existing = db.scalar(select(Report).where(Report.job_id == job.id, Report.data_date == session, Report.mode == planning["mode"]))
            if existing and not existing.quality.startswith("blocked"):
                completed.append(session)
                report_ids.append(existing.id)
                continue
        def progress(message, **kwargs):
            context.checkpoint(completed_sessions=completed, report_ids=report_ids, current_session=session,
                               acquisition=message)
        output, result = adapter.run(storage.path("market"), rules, session, planning["mode"],
                                     job.payload.get("research", "none") != "none", job.payload.get("offline", False), progress_callback=progress)
        import pandas as pd
        from stock_scanner.calendar import calendar
        cutoff = (calendar().session_close(pd.Timestamp(session))+pd.Timedelta(minutes=rules.settlement_minutes)).isoformat()
        result["provenance"] = {"mode": planning["mode"], "job_id": job.id, "knowledge_cutoff": cutoff,
                                "rules_hash": hashlib.sha256(json.dumps(asdict(rules), sort_keys=True).encode()).hexdigest(),
                                "signal_origin": "observed_live" if planning["mode"] == "live" else "reconstructed"}
        from stock_scanner.storage import atomic_json
        atomic_json(output/"report.json", result)
        with (output/"report.md").open("a") as f:
            f.write(f"\nRun mode: {planning['mode']}. Job ID: {job.id}. Historical signals are reconstructed, not observed live.\n")
        with context.database.session() as db:
            artifact = storage.register(db, job.owner_id, output/"report.json", "reports", {"session": session})
            markdown = storage.register(db, job.owner_id, output/"report.md", "reports", {"session": session})
            detailed = output/"all_results.json.gz"
            details_id = storage.register(db, job.owner_id, detailed, "reports", {"session": session}).id if detailed.exists() else None
            for p in (storage.path("market/raw")).rglob("*"):
                if p.is_file() and p.suffix in {".json", ".gz"} and not p.name.startswith("_blocked"):
                    dataset = "grouped" if p.parent.name == "grouped" else "reference"
                    storage.register(db, job.owner_id, p, dataset, {"session": p.name[:10] if dataset == "grouped" else session})
            if existing:
                report_ids = [identity for identity in report_ids if identity != existing.id]
                db.delete(owned(db, Report, existing.id, job.owner_id))
                db.flush()
            row = Report(owner_id=job.owner_id, job_id=job.id, data_date=session, mode=planning["mode"],
                         quality=result["status"], artifact_id=artifact.id, markdown_id=markdown.id,
                         summary={"coverage": result["coverage"], "candidate_count": len(result["candidates"]),
                                  "errors": result["errors"], "provenance": result["provenance"], "details_artifact_id": details_id})
            db.add(row)
            db.flush()
            report_ids.append(row.id)
            for candidate in result["candidates"]:
                h = result["provenance"]["rules_hash"]
                old = db.scalar(select(Signal).where(Signal.owner_id == job.owner_id, Signal.data_date == session,
                                Signal.symbol == candidate["symbol"], Signal.rules_hash == h, Signal.mode == planning["mode"]))
                if old is None:
                    db.add(Signal(owner_id=job.owner_id, data_date=session, symbol=candidate["symbol"], rules_hash=h,
                                  mode=planning["mode"], report_id=row.id, payload=candidate))
        if result["status"].startswith("blocked"):
            context.checkpoint(completed_sessions=completed, report_ids=report_ids, current_session=session)
            raise ServiceError("scan_blocked", "Source/quality blocked the scan; exact errors are preserved in the report")
        completed.append(session)
        context.checkpoint(completed_sessions=completed, report_ids=report_ids)
    return {"report_ids": report_ids, "sessions": completed, "mode": planning["mode"]}


def handle(context):
    if context.job.kind == "scan":
        return scan(context)
    if context.job.kind == "weekly":
        from ...services.reports import weekly
        return weekly(context)
    if context.job.kind == "portfolio_analysis":
        from ...services.portfolios import analyze
        return analyze(context)
    raise ServiceError("invalid_task", "Scanner worker does not support this task")
