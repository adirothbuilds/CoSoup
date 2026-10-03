import json
import shutil
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select
from stock_scanner.calendar import calendar, expected_session

from ...adapters.codex import CodexCLI
from ...errors import ServiceError
from ...persistence.models import Artifact, Report
from ...services.jobs import owned
from ...services.portfolios import ledger
from ...services.reports import publish, published


def handle(context, analyst=None):
    existing = published(context, "agent")
    if existing:
        return existing
    request, storage, owner = context.job.payload, context.storage, context.job.owner_id
    if request.get("profile_id", "research-analyst") != "research-analyst":
        raise ServiceError("invalid_profile", "Unknown trusted analyst profile")
    if request.get("portfolio_id") and not request.get("allow_portfolio_data"):
        raise ServiceError("portfolio_export_denied", "Portfolio export was not explicitly authorized", 403)
    if request.get("allow_current_web_research"):
        raise ServiceError("web_research_disabled", "This analyst profile is limited to approved local inputs")
    latest = expected_session(settlement_minutes=context.settings.settlement_minutes)
    end = request.get("end_date") or latest
    if end > latest:
        raise ServiceError("invalid_date", "Agent task cannot claim future market data", 422)
    if request["task_type"] == "weekly_review" and not request.get("end_date"):
        import pandas as pd
        following = calendar().next_session(pd.Timestamp(end))
        if following.date().isocalendar()[:2] == date.fromisoformat(end).isocalendar()[:2]:
            monday = date.fromisoformat(end)-timedelta(days=date.fromisoformat(end).weekday())
            end = calendar().date_to_session((monday-timedelta(days=1)).isoformat(), direction="previous").date().isoformat()
    start = request.get("start_date") or ((date.fromisoformat(end)-timedelta(days=date.fromisoformat(end).weekday())).isoformat() if request["task_type"] == "weekly_review" else end)
    workspace = storage.path(f"job-workspaces/{context.job.id}-{context.job.lease_token}")
    workspace.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        with context.database.session() as db:
            storage.reserve(db, context.job.id, owner, context.settings.limits.agent_reservation_bytes)
            if request.get("report_ids"):
                reports = [owned(db, Report, identity, owner) for identity in request["report_ids"]]
            else:
                reports = list(db.scalars(select(Report).where(Report.owner_id == owner, Report.data_date >= start, Report.data_date <= end,
                                          Report.mode.in_(["live", "historical_snapshot"])).limit(30)))
            if not reports and request["task_type"] != "portfolio_review":
                raise ServiceError("missing_reports", "No authorized reports exist for the requested period; scan or restore first")
            inputs = {"source_ids": [], "start_date": start, "end_date": end, "reports": [], "portfolio": None}
            for row in reports:
                private_portfolio = row.mode == "portfolio" or row.summary.get("provenance", {}).get("portfolio_export_authorized")
                if private_portfolio and not request.get("allow_portfolio_data"):
                    raise ServiceError("portfolio_export_denied", "Portfolio-derived report export was not authorized", 403)
                artifact = owned(db, Artifact, row.artifact_id, owner)
                p = storage.read(artifact, context.settings.limits.task_output_bytes)
                data = json.loads(p.read_text())
                inputs["reports"].append({"id": row.id, "mode": row.mode, "data_date": row.data_date, "data": data})
                inputs["source_ids"].append(row.id)
            if request.get("portfolio_id"):
                inputs["portfolio"] = ledger(db, owner, request["portfolio_id"])
                inputs["source_ids"].append(request["portfolio_id"])
        body = json.dumps(inputs)
        if len(body.encode()) > context.settings.limits.agent_reservation_bytes//2:
            raise ServiceError("agent_input_limit", "Approved inputs exceed the configured agent workspace budget")
        (workspace/"inputs.json").write_text(body)
        trusted = Path(__file__).resolve().parents[2]/"profiles/research-analyst.md"
        (workspace/"AGENTS.md").write_text(trusted.read_text())
        result = (analyst or CodexCLI(context.settings)).analyze(workspace, request, context.checkpoint)
        allowed = set(inputs["source_ids"])
        if set(result["sources"])-allowed:
            raise ServiceError("agent_unapproved_source", "Agent result cites sources outside its authorized inputs")
        result.update(status="complete" if not result["gaps"] else "partial_coverage", data_date=end,
                      provenance={"job_id": context.job.id, "source_ids": inputs["source_ids"], "profile_id": "research-analyst",
                                  "portfolio_export_authorized": bool(request.get("allow_portfolio_data"))})
        return publish(context, end, "agent", result, result["markdown"])
    finally:
        shutil.rmtree(workspace, ignore_errors=True)
