from collections import Counter
from dataclasses import asdict
import numpy as np
import sqlite3

from .calendar import expected_session, sessions_ending, utc_now
from .market import BENCHMARKS, assess, classify_universe, load_market, quality
from .provider import Client, ProviderError, ensure_grouped, splits, universe
from .reporting import write_daily
from .research import Researcher
from .signals import record_signals
from .storage import read_json


def daily(state, rules, now=None, offline=False, with_research=True, recheck_research=False,
          register_signals=True, knowledge_cutoff=None, progress_callback=None):
    session = expected_session(now, rules.settlement_minutes)
    sessions = sessions_ending(session, rules.history_sessions)
    stamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    output = state / "runs" / "daily" / stamp
    report = {"schema_version": 1, "run_at_utc": utc_now().isoformat(), "data_date": session,
              "requested_as_of": str(now) if now else None, "status": "initializing", "rules": asdict(rules),
              "sessions": sessions, "source": "Massive", "price_volume_basis": "raw unadjusted grouped bars; split prices divided and share volumes multiplied by identical factors to data_date; no dividend adjustment",
              "coverage": {"first_session": sessions[0], "required_sessions": len(sessions)},
              "benchmarks": {}, "errors": [], "candidates": [], "near_breakouts": [],
              "research": {}, "liquidity_examples": [], "warnings": [
                  "Data and signals are personal research tools, not recommendations or calibrated return probabilities.",
                  "Coverage includes active shares on XNAS/XNYS/XASE/ARCX/BATS/IEXG only; OTC is excluded.",
                  "Provider classifications can be wrong; there is no sector/market-cap restriction, but every stock does not have a verified sector mapping.",
                  "Split-adjusted data excludes dividends. Relative strength is excess price change over the same window.",
                  "The listing snapshot is for the data date, not a delisted-company database; it cannot establish backtest performance."]}
    results = []
    if knowledge_cutoff:
        report["knowledge_cutoff"] = knowledge_cutoff
        report["warnings"].append("Historical snapshot: news/filings use the dated cutoff and a separate cache. Provider-dated descriptions and subsequently revised source records are not a certified information-as-known archive.")
    try:
        evidence = state / "live-consistency.json"
        if evidence.exists():
            report["validation_evidence"] = read_json(evidence)
            comparisons = report["validation_evidence"].get("comparisons", {})
            if any(c.get("max_volume_relative_difference", 0) > 1e-6 for c in comparisons.values()):
                report["warnings"].append("Independent ticker-history and grouped-daily volumes differ in the documented validation window. Screening uses grouped-daily volume consistently for stocks and benchmarks; endpoint equivalence is not claimed.")
            if any(not c.get("ohlc_match", True) for c in comparisons.values()):
                raise ValueError("Independent validation found unexplained price inconsistency; diagnose before screening")
        if offline:
            listing = read_json(state / "raw" / "universe" / (session + ".json.gz"))
            split_snapshot = read_json(state / "raw" / "splits" / (sessions[0] + "_" + session + ".json.gz"))
            client = None
        else:
            client = Client(state)
            listing = universe(client, session)
            split_snapshot = splits(client, sessions[0], session)
            ensure_grouped(client, sessions, progress=progress_callback or print)
        if listing.get("as_of") != session or split_snapshot.get("first") != sessions[0] or split_snapshot.get("last") != session:
            raise ValueError("Listing/split cache does not match the requested session window")
        metadata_rows, excluded = classify_universe(listing)
        metadata = {r["ticker"]: r for r in metadata_rows}
        tickers = sorted(set(metadata) | set(BENCHMARKS))
        matrix, data_errors, daily_coverage, events = load_market(state, sessions, tickers, split_snapshot)
        indices = {t: i for i, t in enumerate(tickers)}
        report["coverage"].update(provider_listings=len(listing["results"]), selected_equities=len(metadata),
                                  type_counts=dict(Counter(r.get("type") for r in metadata_rows)),
                                  excluded_listings=excluded, universe_as_of=listing["as_of"],
                                  universe_retrieved_at=listing["retrieved_at"], daily_bars=daily_coverage,
                                  cached_sessions=len(daily_coverage), split_events=len(split_snapshot["results"]))
        for symbol in BENCHMARKS:
            bars = matrix[indices[symbol]]
            issue = data_errors.get(symbol) or quality(bars, sessions, len(sessions))
            report["benchmarks"][symbol] = {"valid": issue is None, "reason": issue,
                                            "data_date": session, "bars": int((~np.isnan(bars).all(axis=1)).sum()),
                                            "last_close": float(bars[-1, 3]) if issue is None else None}
        if any(not b["valid"] for b in report["benchmarks"].values()):
            report["status"] = "blocked_benchmarks"
            report["errors"].append("SPY/IWM must both have complete valid split-consistent histories")
        else:
            benchmark = matrix[indices["SPY"]]
            for ticker in sorted(metadata):
                result = assess(ticker, matrix[indices[ticker]], benchmark, sessions, rules, data_errors.get(ticker))
                result["name"], result["security_type"] = metadata[ticker].get("name"), metadata[ticker].get("type")
                results.append(result)
            counts = Counter(r["reason"] for r in results)
            data_failure_count = sum(not r["data_valid"] and r["reason"] != "insufficient_history" for r in results)
            valid_count = sum(r["data_valid"] for r in results)
            report["coverage"].update(evaluated=len(results), valid_histories=valid_count,
                                      insufficient_history=counts.get("insufficient_history", 0), data_errors=data_failure_count,
                                      valid_fraction=valid_count / len(results))
            report["reason_counts"] = dict(counts)
            report["filter_counts"] = dict(Counter(k for r in results for k in r.get("failed_filters", [])))
            if data_failure_count / len(results) > rules.max_data_error_fraction or not valid_count:
                report["status"] = "blocked_quality"
                report["errors"].append("Data failure fraction exceeded configured limit or no valid histories remain")
            else:
                report["status"] = "partial_coverage" if data_failure_count else "complete"
                rank = lambda r: (r["rs_excess"], r["volume_ratio"], r["symbol"])
                report["candidates"] = sorted((r for r in results if r["eligible"]), key=rank, reverse=True)
                report["near_breakouts"] = sorted((r for r in results if r["near_breakout"]), key=rank, reverse=True)
                if with_research and client is not None:
                    researcher = Researcher(client, session, recheck_research, knowledge_cutoff=knowledge_cutoff)
                    for result in report["candidates"][:rules.research_limit]:
                        report["research"][result["symbol"]] = researcher.candidate(result)
                    report["liquidity_examples"] = researcher.liquidity_examples(results, metadata)
                    report["errors"].extend(researcher.errors)
                else:
                    report["warnings"].append("Current-source research was not run; technical screening is not company research")
                    for r in sorted((r for r in results if r.get("data_valid") and any(k in r["failed_filters"] for k in ("average_share_volume", "average_dollar_volume"))), key=lambda r: r["avg_dollar_volume_50"], reverse=True)[:5]:
                        report["liquidity_examples"].append({"symbol": r["symbol"], "name": r["name"],
                            "avg_volume_50": r["avg_volume_50"], "avg_dollar_volume_50": r["avg_dollar_volume_50"],
                            "liquidity_failures": [k for k in r["failed_filters"] if k in {"average_share_volume", "average_dollar_volume"}]})
                if register_signals:
                    record_signals(state, report)
    except ProviderError as e:
        report["status"] = "blocked_provider"
        report["errors"].append(e.as_dict())
        print(str(e), flush=True)
    except (OSError, EOFError, ValueError, KeyError, TypeError, OverflowError, sqlite3.Error) as e:
        report["status"] = "blocked_error"
        report["errors"].append({"type": type(e).__name__, "message": str(e)})
    finally:
        if report["status"].startswith("blocked"):
            report["candidates"], report["near_breakouts"] = [], []
        if not report["coverage"].get("cached_sessions"):
            report["coverage"]["cached_sessions"] = sum((state / "raw" / "grouped" / (s + ".json.gz")).exists() for s in sessions)
        write_daily(output, report, results)
    return output, report
