"""Bounded, cached, split-consistent visual data. Never calls a provider."""
import re
import hashlib
import threading
from collections import OrderedDict
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from sqlalchemy import select

from stock_scanner.calendar import calendar, expected_session, sessions_ending
from stock_scanner.market import load_market, quality, split_events
from stock_scanner.storage import read_json

from ..errors import ServiceError
from ..persistence.models import Artifact, Report
from .jobs import owned
from .portfolios import ledger

_columns = OrderedDict()
_column_lock = threading.Lock()


def ending(settings, value=None):
    end = value or expected_session(settlement_minutes=settings.settlement_minutes)
    try:
        if end > expected_session(settlement_minutes=settings.settlement_minutes) or not calendar().is_session(end):
            raise ValueError()
        sessions_ending(end)
    except (ValueError, KeyError, TypeError):
        raise ServiceError("invalid_market_date", "Choose a completed trading session within the supported calendar", 422) from None
    return end


def fingerprints(root, sessions):
    files = [root / "raw/grouped" / (d+".json.gz") for d in sessions]
    files += sorted((root / "raw/splits").glob("*.json.gz"))
    return tuple((str(p), p.stat().st_mtime_ns, p.stat().st_size) for p in files if p.is_file())


@lru_cache(maxsize=8)
def cached_matrix(root_name, sessions, symbols, stamps):
    root = Path(root_name)
    references = []
    for name, _, _ in stamps:
        if "/splits/" not in name:
            continue
        snapshot = read_json(name)
        if snapshot.get("first", "9999") <= sessions[0] and snapshot.get("last", "") >= sessions[-1]:
            references.append(snapshot)
    if not references:
        raise ServiceError("split_reference_unavailable", "A split reference covering the chart warmup is missing; ingest or restore it", 409)
    reference = min(references, key=lambda s: (s["last"] != sessions[-1], s["last"]))
    reference = {**reference, "results": [r for r in reference["results"] if r.get("execution_date", "9999") <= sessions[-1]]}
    available = [d for d in sessions if (root / "raw/grouped" / (d+".json.gz")).is_file()]
    matrix = np.full((len(symbols), len(sessions), 5), np.nan)
    errors, daily = {}, []
    if available:
        # Validate raw bars first. Adjustment cutoff is the requested session,
        # even when the final grouped file itself is missing.
        loaded, errors, daily, _ = load_market(root, available, symbols, {"results":[]})
        positions = {d:i for i,d in enumerate(sessions)}
        for i,d in enumerate(available):
            matrix[:, positions[d], :] = loaded[:, i, :]
    events, split_errors = split_events(reference)
    errors.update({s:e for s,e in split_errors.items() if s in symbols})
    for i,symbol in enumerate(symbols):
        factors = np.ones(len(sessions))
        for execution, ratio in events[symbol]:
            factors *= np.array([ratio if day < execution else 1 for day in sessions])
        if not np.isfinite(factors).all() or (factors<=0).any():
            errors[symbol] = "invalid_split_factor"
        else:
            with np.errstate(over="ignore",invalid="ignore"):
                matrix[i,:,:4] /= factors[:,None]
                matrix[i,:,4] *= factors
    return matrix, errors, daily, reference.get("retrieved_at"), reference["last"]


def matrix_for(storage, end, symbols, count=260):
    sessions = tuple(sessions_ending(end, count))
    try:
        root = str(storage.path("market"))
        stamps = fingerprints(storage.path("market"), sessions)
        stamp = hashlib.sha256(repr(stamps).encode()).digest()
        keys = [(root,sessions,stamp,symbol) for symbol in symbols]
        full_keys = None
        if count < 260:
            full_sessions = tuple(sessions_ending(end))
            full_stamps = fingerprints(storage.path("market"), full_sessions)
            full_stamp = hashlib.sha256(repr(full_stamps).encode()).digest()
            full_keys = [(root,full_sessions,full_stamp,symbol) for symbol in symbols]
        with _column_lock:
            reused = [_columns.get(k) for k in keys]
            reused_keys = keys
            if not all(r is not None for r in reused) and full_keys:
                reused = [_columns.get(k) for k in full_keys]
                reused_keys = full_keys
                # An error from an older bar may not apply to this shorter range.
                if any(r is not None and r[1] for r in reused):
                    reused = [None] * len(symbols)
            if all(r is not None for r in reused):
                for k in reused_keys:
                    _columns.move_to_end(k)
                return sessions, np.stack([r[0][-count:] for r in reused]), {s:r[1] for s,r in zip(symbols,reused) if r[1]}, *reused[0][2:]
        matrix, errors, daily, retrieved, reference_end = cached_matrix(root, sessions, tuple(symbols), stamps)
        with _column_lock:
            for i,key in enumerate(keys):
                _columns[key] = (matrix[i].copy(),errors.get(symbols[i]),daily,retrieved,reference_end)
                _columns.move_to_end(key)
            while len(_columns)>256:
                _columns.popitem(last=False)
    except ServiceError:
        raise
    except (OSError, ValueError, KeyError, TypeError, EOFError):
        raise ServiceError("invalid_market_cache", "Cached market inputs are malformed or have an inconsistent basis", 409) from None
    return sessions, matrix, errors, daily, retrieved, reference_end


def restore_ids(db, owner, sessions):
    return [a.id for a in db.scalars(select(Artifact).where(Artifact.owner_id == owner,
                  Artifact.dataset.in_(["grouped", "splits", "reference"]), Artifact.status == "cold").order_by(Artifact.id))
            if (a.dataset == "splits" or a.path.startswith("market/raw/splits/"))
            or (a.dataset == "grouped" and a.metadata_.get("session") in sessions)][:100]


def bars(db, storage, settings, owner, symbol, start, end):
    if not re.fullmatch(r"[A-Z0-9][A-Z0-9.\-]{0,29}", symbol):
        raise ServiceError("invalid_symbol", "Invalid stock symbol", 422)
    end = ending(settings, end)
    with storage.reader():
        sessions, matrix, errors, daily, retrieved, reference_end = matrix_for(storage, end, [symbol])
    if start and (start > end or start < sessions[0]):
        raise ServiceError("chart_range_limit", "Chart range must fit the 260-session cached window", 422)
    values = matrix[0]
    output, missing, sma50, sma200, pivots = [], [], [], [], []
    for i, day in enumerate(sessions):
        if start and day < start:
            continue
        issue = errors.get(symbol) or quality(values[i:i+1], [day], 1)
        if issue:
            missing.append({"session": day, "reason": issue})
            continue
        o,h,l,c,v = (float(x) for x in values[i])
        output.append({"session": day, "open": o, "high": h, "low": l, "close": c, "volume": v})
        for count, series in [(50,sma50),(200,sma200)]:
            window = values[max(0,i-count+1):i+1]
            if len(window) == count and quality(window, sessions[max(0,i-count+1):i+1], count) is None:
                series.append({"session": day, "value": float(window[:,3].mean())})
        prior = values[max(0,i-55):i]
        if len(prior) == 55 and quality(prior, sessions[i-55:i], 55) is None:
            pivots.append({"session": day, "value": float(prior[:,1].max())})
    return {"symbol": symbol, "data_date": end, "basis": "split_adjusted", "adjustment_cutoff": end,
            "source": "Massive grouped daily cache", "split_reference_end": reference_end,
            "split_reference_retrieved_at": retrieved, "bars": output, "missing_sessions": missing,
            "indicators": {"sma50": sma50, "sma200": sma200, "breakout55": pivots},
            "quality": "partial_coverage" if missing else "complete", "restore_artifact_ids": restore_ids(db,owner,sessions),
            "note": "Completed sessions; split-adjusted price movement excludes dividends. Historical references may be retrieved later."}


def movement(db, storage, settings, owner, request):
    end = request.data_date.isoformat() if request.data_date else None
    names, metrics = {}, {}
    if request.scope == "portfolio":
        if not request.portfolio_id:
            raise ServiceError("missing_scope", "Select a portfolio", 422)
        end = ending(settings, end)
        positions = ledger(db, owner, request.portfolio_id, calendar().session_close(pd.Timestamp(end)).to_pydatetime())["positions"]
        symbols = sorted(p["symbol"] for p in positions)
    else:
        if not request.report_id:
            raise ServiceError("missing_scope", "Select a daily report", 422)
        report = owned(db, Report, request.report_id, owner)
        end = ending(settings, end or report.data_date)
        if report.data_date != end or report.mode not in {"live", "historical_snapshot"}:
            raise ServiceError("scope_date_mismatch", "Movement must use the selected daily report's session", 422)
        # Daily report metadata deliberately contains counts, not candidate rows.
        artifact = owned(db, Artifact, report.artifact_id, owner)
        with storage.reader():
            document = read_json(storage.read(artifact, settings.limits.task_output_bytes))
        candidates = document.get("candidates" if request.scope == "candidates" else "near_breakouts", [])
        metrics = {r["symbol"]:r for r in candidates}
        names = {s:r.get("name") for s,r in metrics.items()}
        symbols = sorted(metrics)
    total = len(symbols)
    symbols = symbols[:100]
    intervals = {"1D":1,"1W":5,"1M":21}[request.period]
    sessions = sessions_ending(end, intervals+1)
    if not symbols:
        return {"data_date": end,"start_date":sessions[0],"period":request.period,"basis":"split_adjusted",
                "items":[],"total_symbols":total,"displayed_symbols":0,"quality":"complete","restore_artifact_ids":[]}
    with storage.reader():
        warmup, matrix, errors, _, _, _ = matrix_for(storage, end, symbols, intervals+1)
    output = []
    for symbol, values in zip(symbols, matrix):
        recent = values[-intervals-1:]
        issue = errors.get(symbol) or quality(recent, sessions, len(sessions))
        output.append({"symbol":symbol,"name":names.get(symbol),"change_percent":None if issue else float((recent[-1,3]/recent[0,3]-1)*100),
                       "close":None if issue else float(recent[-1,3]),"quality":issue or "complete","metrics":metrics.get(symbol)})
    return {"data_date":end,"start_date":sessions[0],"period":request.period,"basis":"split_adjusted",
            "items":output,"total_symbols":total,"displayed_symbols":len(output),"quality":"partial_coverage" if any(r["quality"]!="complete" for r in output) else "complete",
            "restore_artifact_ids":restore_ids(db,owner,warmup)}
