"""Private persistent signal registry; observations are never trading returns."""
import hashlib
import json
import sqlite3
from dataclasses import asdict
from datetime import date, timedelta

import numpy as np

from .calendar import expected_session, utc_now
from .market import load_market, quality
from .reporting import weekly_markdown
from .storage import atomic_json, read_json


def database(state):
    connection = sqlite3.connect(state / "signals.sqlite3")
    connection.execute("CREATE TABLE IF NOT EXISTS signals (signal_date TEXT, symbol TEXT, rules_id TEXT, payload TEXT, PRIMARY KEY(signal_date,symbol,rules_id))")
    return connection


def record_signals(state, report):
    rules_id = hashlib.sha256(json.dumps(report["rules"], sort_keys=True).encode()).hexdigest()[:16]
    with database(state) as db:
        for candidate in report["candidates"]:
            db.execute("INSERT OR IGNORE INTO signals VALUES(?,?,?,?)",
                       (report["data_date"], candidate["symbol"], rules_id,
                        json.dumps(candidate | {"run_at_utc": report["run_at_utc"]})))


def previous_signals(state, since=None):
    with database(state) as db:
        query = "SELECT signal_date,symbol,rules_id,payload FROM signals"
        rows = db.execute(query + (" WHERE signal_date >= ?" if since else "") + " ORDER BY signal_date,symbol", (since,) if since else ())
        return [{"signal_date": d, "symbol": s, "rules_id": r, "original": json.loads(p)} for d, s, r, p in rows]


def observations(signals, matrix, symbols, sessions, events, data_errors):
    index = {s: i for i, s in enumerate(symbols)}
    output = []
    for signal in signals:
        symbol, day = signal["symbol"], signal["signal_date"]
        row = {"symbol": symbol, "signal_date": day, "rules_id": signal["rules_id"],
               "observation_date": sessions[-1], "monitor_status": "unavailable",
               "price_change": None, "close_drawdown": None, "closes_below_pivot": None}
        if symbol not in index or day not in sessions or data_errors.get(symbol):
            row["error"] = data_errors.get(symbol, "signal_outside_cache_or_symbol_missing")
            output.append(row)
            continue
        signal_index = sessions.index(day)
        bars = matrix[index[symbol], signal_index:]
        reason = quality(bars, sessions[signal_index:], len(bars))
        if reason:
            row["error"] = reason
            output.append(row)
            continue
        original = signal["original"]
        factor = 1.0
        for split_day, ratio in events[symbol]:
            if day < split_day <= sessions[-1]:
                factor *= ratio
        baseline, pivot = original["close"] / factor, original["pivot"] / factor
        closes = bars[:, 3]
        # Track in a single current share basis; no synthetic entries/exits.
        if not np.isclose(closes[0], baseline, rtol=1e-6, atol=1e-8):
            row["error"] = "signal_price_revised_or_corporate_action_mismatch"
        elif len(closes) == 1:
            row["monitor_status"] = "awaiting_followup"
            row["closes_below_pivot"] = 0
        else:
            running_high = np.maximum.accumulate(closes)
            below = closes[1:] < pivot
            row.update(monitor_status="failed_below_pivot" if closes[-1] < pivot else "recovered_after_failure" if below.any() else "above_pivot",
                       price_change=float(closes[-1]/baseline-1),
                       close_drawdown=float((closes/running_high-1).min()),
                       closes_below_pivot=int(below.sum()), original_pivot_on_current_basis=pivot,
                       sessions_observed=len(closes)-1)
        output.append(row)
    return output


def weekly(state, now=None):
    latest = expected_session(now)
    monday = (date.fromisoformat(latest) - timedelta(days=date.fromisoformat(latest).weekday())).isoformat()
    reports = []
    for path in sorted((state / "runs" / "daily").glob("*/report.json")):
        report = read_json(path)
        if report.get("data_date") <= latest:
            reports.append((path, report))
    by_date = {}
    for path, report in reports:
        by_date[report["data_date"]] = report
    daily = [r for d, r in sorted(by_date.items()) if monday <= d <= latest]
    summary = {"run_at_utc": utc_now().isoformat(), "data_date": latest,
               "week_start": monday, "status": "complete", "signals": [], "errors": [],
               "daily_run_count": len(daily), "daily_runs": [
                   {"data_date": r["data_date"], "status": r["status"], "candidate_count": len(r["candidates"]),
                    "data_errors": r.get("coverage", {}).get("data_errors", 0)} for r in daily],
               "observation_note": "Split-adjusted price changes only. No trades, dividends, fees or simulated portfolio."}
    if latest not in by_date or by_date[latest]["status"].startswith("blocked"):
        summary["status"] = "blocked_missing_current_daily"
        summary["errors"].append("No valid daily screen for the latest completed session; current observations are unverified")
    else:
        report = by_date[latest]
        sessions = report["sessions"]
        signal_rows = previous_signals(state, (date.fromisoformat(latest)-timedelta(days=90)).isoformat())
        # Old/out-of-window observations remain unavailable, not silently dropped.
        tickers = sorted({s["symbol"] for s in signal_rows})
        split_path = state / "raw" / "splits" / (sessions[0] + "_" + latest + ".json.gz")
        try:
            if tickers:
                matrix, errors, _, events = load_market(state, sessions, tickers, read_json(split_path))
                summary["signals"] = observations(signal_rows, matrix, tickers, sessions, events, errors)
            if any(s["monitor_status"] == "unavailable" for s in summary["signals"]):
                summary["status"] = "partial_observations"
        except (OSError, ValueError, KeyError) as e:
            summary["status"] = "blocked_cache"
            summary["errors"].append(str(e))
        if report["status"] == "partial_coverage" or any(r["status"].startswith("blocked") for r in daily):
            summary["errors"].append("Some daily screens were blocked or had partial coverage")
            if summary["status"] == "complete":
                summary["status"] = "partial_coverage"
    # A one-day deployment cannot masquerade as a full week of observations.
    from .calendar import calendar
    expected_days = [d.date().isoformat() for d in calendar().sessions_in_range(monday, latest)]
    missing = sorted(set(expected_days) - set(by_date))
    summary["missing_daily_sessions"] = missing
    if missing:
        summary["errors"].append("Missing daily reports this week: " + ", ".join(missing))
        if summary["status"] == "complete":
            summary["status"] = "partial_week"
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    directory = state / "runs" / "weekly" / stamp
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    atomic_json(directory / "report.json", summary)
    (directory / "report.md").write_text(weekly_markdown(summary), encoding="utf-8")
    return directory, summary
