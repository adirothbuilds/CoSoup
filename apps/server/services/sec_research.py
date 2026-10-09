"""Owner-scoped SEC sync jobs; reading a report never makes a source request."""
import json
from datetime import datetime, timezone

from sqlalchemy import select

from stock_scanner.sec_data import LIMITATIONS, SecClient, company, manager
from stock_scanner.storage import read_json

from ..errors import ServiceError
from ..persistence.models import Artifact, Report
from .jobs import owned
from .reports import publish, published


def sync_symbols(db, storage, settings, owner, payload):
    symbols = payload.get("symbols", [])
    if payload.get("report_id"):
        report = owned(db, Report, payload["report_id"], owner)
        if report.mode not in {"live", "historical_snapshot"} or report.quality.startswith("blocked"):
            raise ServiceError("invalid_research_source", "Select a usable daily report", 422)
        if not symbols:
            artifact = owned(db, Artifact, report.artifact_id, owner)
            with storage.reader():
                content = json.loads(storage.read(artifact, settings.limits.task_output_bytes).read_text())
            symbols = [c["symbol"] for c in content.get("candidates", [])][:10]
    if not symbols:
        raise ServiceError("missing_symbols", "Choose up to ten symbols or a daily report containing candidates", 422)
    return list(dict.fromkeys(symbols))


def sync(context):
    existing = published(context, "sec_research")
    if existing:
        if existing["quality"].startswith("blocked"):
            raise ServiceError("sec_source_blocked", "Saved SEC sync was blocked; inspect diagnostics before creating a new sync")
        return existing
    job, storage = context.job, context.storage
    with context.database.session() as db:
        symbols = sync_symbols(db, storage, context.settings, job.owner_id, job.payload)
        storage.reserve(db, job.id, job.owner_id, context.settings.limits.scan_reservation_bytes)
    as_of = datetime.now(timezone.utc).date().isoformat()
    client = SecClient(storage.path("market"), as_of, checkpoint=context.checkpoint)
    result = {"status": "partial_coverage", "as_of": as_of, "data_date": as_of,
              "companies": [], "managers": [], "errors": [], "limitations": LIMITATIONS,
              "provenance": {"job_id": job.id, "source_report_id": job.payload.get("report_id"),
                             "knowledge_cutoff": datetime.now(timezone.utc).isoformat(),
                             "market_prices_refreshed": False, "model_request_made": False}}
    tickers = client.get("https://www.sec.gov/files/company_tickers.json")
    mapping = {r["ticker"].upper(): r["cik_str"] for r in tickers["data"].values()} if tickers else {}
    for symbol in symbols:
        context.checkpoint(stage="company_filings", symbol=symbol, requests=client.requests)
        if symbol not in mapping:
            result["companies"].append({"symbol": symbol, "metrics": [], "filings": [], "documents": [],
                                        "gaps": ["SEC issuer mapping unavailable; no financial facts inferred"]})
            continue
        result["companies"].append(company(client, symbol, mapping[symbol]))
    for cik in dict.fromkeys(job.payload.get("manager_ciks", [])):
        context.checkpoint(stage="institutional_holdings", manager_cik=cik, requests=client.requests)
        result["managers"].append(manager(client, cik))
    result["errors"] = client.errors
    result["checked_at"] = datetime.now(timezone.utc).isoformat()
    result["coverage"] = {"requested_companies": len(symbols),
                           "companies_with_financials": sum(bool(c["metrics"]) for c in result["companies"]),
                           "filing_documents": sum(len(c["documents"]) for c in result["companies"]),
                           "requested_managers": len(result["managers"]),
                           "managers_with_holdings": sum(bool(m["snapshots"]) for m in result["managers"]),
                           "source_requests": client.requests}
    if client.stopped and not (result["coverage"]["companies_with_financials"] or result["coverage"]["managers_with_holdings"]):
        result["status"] = "blocked_provider"
    body = json.dumps(result).encode()
    if len(body) > context.settings.limits.task_output_bytes:
        raise ServiceError("sec_output_limit", "SEC research exceeds the configured report budget")
    markdown = f"# SEC research — {as_of}\n\nQuality: {result['status']}. This sync did not refresh market prices.\n\n"
    for c in result["companies"]:
        markdown += f"## {c['symbol']} — {c.get('name', 'Issuer unavailable')}\n\n"
        for metric in c["metrics"]:
            markdown += f"- {metric['label']}: {metric['value']:,.2f} {metric['unit']}; {metric.get('period_start') or 'instant'} → {metric['period_end']}; filed {metric['filing_date']}. [Filing]({metric['source']})\n"
        for f in c["filings"]:
            markdown += f"- [{f['form']} — filed {f['filing_date']}]({f['source']})\n"
        for gap in c["gaps"]:
            markdown += f"- Coverage gap: {gap}\n"
    for m in result["managers"]:
        markdown += f"\n## {m['name']}\n\n"
        for snap in m["snapshots"]:
            markdown += f"### Holdings as of {snap['period_end']}, filed {snap['filing_date']}\n\n[Original information table]({snap['source']})\n\n"
            for h in snap["holdings"]:
                markdown += f"- {h['issuer']} ({h['class']}, {h['put_call'] or 'equity'}): {h['shares']:,.0f} {h['amount_type']}; reported value ${h['value_usd']:,.0f}.\n"
        for gap in m["gaps"]:
            markdown += f"- Coverage gap: {gap}\n"
    markdown += "\n## Limitations\n\n"+"\n".join("- "+g for g in LIMITATIONS)
    for error in client.errors:
        markdown += f"\n- Source error: {error['http_status']}; {error['endpoint']}. {error['message']}\n"
    with context.database.session() as db:
        for path in client.cache_paths:
            storage.register(db, job.owner_id, path, "reference", {"provider": "SEC", "session": as_of})
    saved = publish(context, as_of, "sec_research", result, markdown)
    context.checkpoint(stage="saved", report_ids=[saved["report_id"]], coverage=result["coverage"], errors=client.errors)
    if client.errors:
        raise ServiceError("sec_source_blocked", "Public SEC access failed. Exact endpoint/status are saved in the report; no automatic retry")
    return saved
