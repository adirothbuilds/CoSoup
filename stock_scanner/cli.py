import argparse
import fcntl
import json
import os
from pathlib import Path

from .calendar import calendar, expected_session, next_run, sessions_ending, utc_now
from .delivery import DeliveryError, prepare
from .provider import Client, ProviderError, ensure_grouped, fetched, splits, universe
from .rules import Rules
from .signals import weekly
from .storage import atomic_json, read_json, state_directory
from .workflow import daily


def summary(directory, report):
    return {"output": str(directory), "status": report["status"], "data_date": report["data_date"],
            "candidates": len(report.get("candidates", [])), "coverage": {k: v for k, v in report.get("coverage", {}).items() if k != "daily_bars"},
            "errors": report.get("errors", [])}


def preflight(state, rules):
    client, last = Client(state), expected_session(settlement_minutes=rules.settlement_minutes)
    sessions = sessions_ending(last, rules.history_sessions)
    checks = {"data_date": last, "history_start": sessions[0], "checks": [], "errors": [], "status": "complete"}
    try:
        ensure_grouped(client, [sessions[0], last])
        checks["checks"].append({"grouped_daily": "verified_latest_and_oldest"})
        events = splits(client, sessions[0], last)
        checks["checks"].append({"splits": "accessible", "events": len(events["results"])})
        for ticker in ("SPY", "IWM"):
            path = f"/v2/aggs/ticker/{ticker}/range/1/day/{sessions[0]}/{last}"
            data = client.get(path, {"adjusted": "true", "sort": "asc", "limit": 5000})
            from datetime import datetime
            from zoneinfo import ZoneInfo
            dates = [datetime.fromtimestamp(r["t"]/1000, ZoneInfo("America/New_York")).date().isoformat() for r in data.get("results", [])]
            if dates != sessions or data.get("adjusted") is not True:
                raise ProviderError("history_mismatch", path, "Benchmark history does not match all expected sessions")
            atomic_json(state / "raw" / "benchmark-preflight" / (ticker + "_" + last + ".json.gz"),
                        {"retrieved_at": fetched(), "source": path, "data": data})
            checks["checks"].append({"ticker": ticker, "history_sessions": len(dates), "last_session": dates[-1]})
        listing = universe(client, last)
        checks["checks"].append({"universe_listings": len(listing["results"]), "as_of": listing["as_of"]})
    except ProviderError as e:
        checks["status"] = "blocked_provider"
        checks["errors"].append(e.as_dict())
        print(str(e), flush=True)
    atomic_json(state / "preflight.json", checks)
    return checks


def scheduled(state, rules, send=False, with_research=True):
    """Invoked by a DURABLE external scheduler, never by a transient local cron."""
    import pandas as pd
    now = pd.Timestamp(utc_now())
    session = expected_session(now, rules.settlement_minutes)
    today = now.tz_convert("America/New_York").date().isoformat()
    checkpoint = state / "schedule-checkpoint.json"
    saved = read_json(checkpoint) if checkpoint.exists() else {}
    if today != session:
        return {"status": "not_due", "next": next_run(now, rules.settlement_minutes)}
    daily_saved = saved.get("daily", {})
    if daily_saved.get("session") != session:
        directory, report = daily(state, rules, now, with_research=with_research)
        saved["daily"] = {"session": session, "directory": str(directory), "status": report["status"], "delivery": "not_sent"}
        atomic_json(checkpoint, saved)
    day = saved["daily"]
    if day["status"].startswith("blocked"):
        # Persistent failure is not retried every timer tick. Manual daily diagnoses/resumes.
        return {"status": "blocked_daily", "daily": day, "action": "Inspect report and resume manually after fixing the prerequisite"}
    def deliver_once(entry):
        if entry["delivery"] in {"attempting", "failed_no_auto_retry"}:
            raise DeliveryError("Previous scheduled delivery failed or is uncertain; inspect it before a manual retry")
        if entry["delivery"] == "not_sent":
            entry["delivery"] = "attempting"
            atomic_json(checkpoint, saved)
            try:
                delivery = prepare(Path(entry["directory"]) / "report.md", state, send=True)
                entry["delivery"] = "sent" if delivery["status"] in {"sent", "already_sent"} else delivery["status"]
            except DeliveryError:
                entry["delivery"] = "failed_no_auto_retry"
                raise
            finally:
                atomic_json(checkpoint, saved)
    if send:
        deliver_once(day)
    cal = calendar()
    next_session = cal.next_session(pd.Timestamp(session)).date()
    is_week_end = next_session.isocalendar()[:2] != pd.Timestamp(session).date().isocalendar()[:2]
    if is_week_end:
        if saved.get("weekly", {}).get("session") != session:
            directory, report = weekly(state, now)
            saved["weekly"] = {"session": session, "directory": str(directory), "status": report["status"], "delivery": "not_sent"}
            atomic_json(checkpoint, saved)
        week = saved["weekly"]
        if send and not week["status"].startswith("blocked"):
            deliver_once(week)
    return {"status": "processed", "daily": day, "weekly": saved.get("weekly") if is_week_end else None,
            "live_delivery_enabled": send}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Personal US equity research; private state, Massive data, no trades")
    parser.add_argument("--state-dir", help="Private directory OUTSIDE the checkout; default SCANNER_STATE_DIR or /workspace/stock-scanner-state")
    parser.add_argument("--config", help="Rules JSON; defaults to repository config.json")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight", help="Explicit read-only entitlement and benchmark checks; no upgrades")
    p = commands.add_parser("ingest", help="Cache 260 market-wide sessions; resume missing days only")
    p.add_argument("--as-of", help="Timezone-qualified observation time; defaults to actual UTC now")
    p = commands.add_parser("daily", help="Ingest missing days, screen all supported equities, report in English")
    p.add_argument("--as-of", help="Timezone-qualified observation time; historical dates are research snapshots, not backtests")
    p.add_argument("--offline", action="store_true", help="Use exact cached snapshots only; no network")
    p.add_argument("--no-research", action="store_true", help="Skip current company/news/financial sources, mark this gap")
    p.add_argument("--recheck-research", action="store_true", help="Explicitly recheck cached access failures after a meaningful settings change")
    p = commands.add_parser("weekly", help="Summarize cached daily reports and track prior signals; no network")
    p.add_argument("--as-of")
    commands.add_parser("schedule-plan", help="Next close-plus-buffer in UTC/New York; no process scheduling")
    p = commands.add_parser("scheduled", help="Idempotent close-aware entrypoint for a durable scheduler")
    p.add_argument("--send", action="store_true", help="Enable configured SMTP delivery; requires private variables and explicit enable flag")
    p.add_argument("--no-research", action="store_true")
    p = commands.add_parser("deliver", help="Prepare a private email draft; --send explicitly sends via configured TLS SMTP")
    p.add_argument("report", type=Path, help="Private generated report.md")
    p.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)
    try:
        rules, state = Rules.load(args.config), state_directory(args.state_dir)
        # Serialize workflows; the provider additionally shares its limiter across all processes.
        with (state / "workflow.lock").open("a+") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ValueError("Another scanner workflow is active; no duplicate run started") from None
            if args.command == "daily":
                directory, report = daily(state, rules, args.as_of, args.offline, not args.no_research, args.recheck_research)
                result = summary(directory, report)
            elif args.command == "weekly":
                directory, report = weekly(state, args.as_of)
                result = summary(directory, report)
            elif args.command == "preflight":
                result = preflight(state, rules)
            elif args.command == "ingest":
                session = expected_session(args.as_of, rules.settlement_minutes)
                sessions = sessions_ending(session, rules.history_sessions)
                client = Client(state)
                splits(client, sessions[0], session)
                ensure_grouped(client, sessions)
                result = {"status": "complete", "data_date": session, "cached_sessions": len(sessions)}
            elif args.command == "schedule-plan":
                result = {"status": "prepared", "next": next_run(settlement_minutes=rules.settlement_minutes),
                          "scheduler": "Durable host/managed scheduler with persistent private state required; no local cron installed",
                          "delivery": "not_connected", "mail_variables_present": {k: bool(os.environ.get(k)) for k in (
                              "SCANNER_REPORT_TO", "SMTP_FROM", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SCANNER_EMAIL_ENABLED")}}
            elif args.command == "scheduled":
                result = scheduled(state, rules, args.send, not args.no_research)
            else:
                result = prepare(args.report, state, args.send)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
        return 2 if result["status"].startswith("blocked") else 0
    except (ProviderError, DeliveryError, OSError, ValueError) as e:
        print(json.dumps({"status": "blocked", "error": str(e)}, ensure_ascii=False), flush=True)
        return 2
