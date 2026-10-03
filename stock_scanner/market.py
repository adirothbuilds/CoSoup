"""Compact market-wide OHLCV matrix, using a single raw daily fetch per session."""
from collections import Counter, defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import re

import numpy as np

from .storage import read_json

ELIGIBLE_TYPES = {"CS", "OS", "ADRC", "NYRS"}
BENCHMARKS = ("SPY", "IWM")
LISTED_EXCHANGES = {"XNAS", "XNYS", "XASE", "ARCX", "BATS", "IEXG"}
EXCLUDED_NAMES = re.compile(r"\bfunds?\b|\bET[FN]\b|\bclosed[- ]end\b|\bwarrants?\b|\bpreferred\b|\bpreference\b|\bunits?\b|\brights\b|\bnotes\b|\bdebentures?\b|\b(?:L\.?P\.?|limited partnership)\s*$", re.I)


def classify_universe(snapshot):
    selected, excluded, seen = [], Counter(), set()
    for row in snapshot["results"]:
        if not isinstance(row, dict):
            raise ValueError("Malformed listing row")
        ticker = row.get("ticker")
        if not isinstance(ticker, str) or not ticker or ticker in seen:
            raise ValueError("Malformed or duplicate ticker in listing snapshot")
        seen.add(ticker)
        if row.get("type") not in ELIGIBLE_TYPES:
            excluded["security_type:" + str(row.get("type", "unknown"))] += 1
        elif EXCLUDED_NAMES.search(str(row.get("name") or "")):
            excluded["ineligible_security_name_despite_common_type"] += 1
        elif row.get("primary_exchange") not in LISTED_EXCHANGES:
            excluded["outside_supported_us_exchanges"] += 1
        elif row.get("active") is not True or row.get("market") != "stocks" or row.get("locale") != "us":
            excluded["not_active_us_equity"] += 1
        elif not isinstance(row.get("currency_name", "usd"), str) or row.get("currency_name", "usd").lower() != "usd":
            excluded["non_usd"] += 1
        else:
            selected.append(row)
    if not selected:
        raise ValueError("No supported common shares / common ADRs in listing snapshot")
    return selected, dict(excluded)


def split_events(snapshot):
    events, errors, seen = defaultdict(list), {}, set()
    for item in snapshot["results"]:
        ticker, date = item.get("ticker"), item.get("execution_date")
        try:
            before, after = float(item["split_from"]), float(item["split_to"])
            datetime.strptime(date, "%Y-%m-%d")
            if not ticker or not np.isfinite([before, after]).all() or before <= 0 or after <= 0:
                raise ValueError()
            identity = (ticker, date, before, after)
            if identity in seen:
                continue
            if any(e[0] == date for e in events[ticker]):
                errors[ticker] = "ambiguous_split_events"
            seen.add(identity)
            events[ticker].append((date, after / before))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            if ticker:
                errors[ticker] = "invalid_split_event"
            else:
                raise ValueError("Malformed split event without ticker")
    return events, errors


def load_market(state, sessions, tickers, split_snapshot):
    indices = {ticker: i for i, ticker in enumerate(tickers)}
    matrix = np.full((len(tickers), len(sessions), 5), np.nan)
    errors, daily = {}, []
    for day_index, session in enumerate(sessions):
        path = state / "raw" / "grouped" / (session + ".json.gz")
        if not path.exists():
            raise ValueError("Missing daily cache: " + session)
        snapshot = read_json(path)
        if snapshot.get("session") != session or snapshot.get("adjusted") is not False or snapshot["data"].get("adjusted") is not False:
            raise ValueError("Incorrect raw cache basis: " + session)
        rows = snapshot["data"].get("results")
        if not rows:
            raise ValueError("Empty daily cache: " + session)
        seen = set()
        for row in rows:
            ticker = row.get("T")
            index = indices.get(ticker)
            if index is None:
                continue
            if ticker in seen:
                errors[ticker] = "duplicate_daily_bar"
                continue
            seen.add(ticker)
            try:
                if datetime.fromtimestamp(row["t"] / 1000, ZoneInfo("America/New_York")).date().isoformat() != session:
                    errors[ticker] = "bar_date_mismatch"
                    continue
                values = [row[k] for k in ("o", "h", "l", "c", "v")]
                if any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in values):
                    raise ValueError()
                matrix[index, day_index] = values
            except (KeyError, TypeError, ValueError, OverflowError, OSError):
                errors[ticker] = "malformed_daily_bar"
        daily.append({"session": session, "market_bars": len(rows), "selected_bars": len(seen),
                      "retrieved_at": snapshot.get("retrieved_at")})
    events, split_errors = split_events(split_snapshot)
    errors.update({t: v for t, v in split_errors.items() if t in indices})
    for ticker, index in indices.items():
        factors = np.ones(len(sessions))
        for date, ratio in events[ticker]:
            if date <= sessions[-1]:
                factors *= np.array([ratio if session < date else 1 for session in sessions])
        with np.errstate(over="ignore", invalid="ignore"):
            matrix[index, :, :4] /= factors[:, None]
            matrix[index, :, 4] *= factors
        if not np.isfinite(factors).all() or (factors <= 0).any():
            errors[ticker] = "invalid_split_factor"
    return matrix, errors, daily, events


def quality(bars, sessions, min_history):
    present = ~np.isnan(bars).all(axis=1)
    if not present.any():
        return "missing_data"
    if not present[-1]:
        return "stale_data"
    if present.sum() < min_history:
        return "insufficient_history"
    if not present[-min_history:].all():
        return "missing_sessions"
    # All observed rows must be plausible; NaN within a present bar is a data failure.
    values = bars[present]
    if not np.isfinite(values).all():
        return "invalid_prices_or_volume"
    o, h, l, c, v = values.T
    if (values[:, :4] <= 0).any() or (values[:, :4] > 1e8).any() or (v < 0).any() or (v > 1e15).any():
        return "invalid_prices_or_volume"
    tolerance = 1e-8 * np.maximum(1, h)
    if (h + tolerance < np.maximum.reduce([o, l, c])).any() or (l - tolerance > np.minimum.reduce([o, h, c])).any():
        return "invalid_ohlc"
    return None


def assess(ticker, bars, benchmark, sessions, rules, data_error=None):
    present = np.where(~np.isnan(bars).all(axis=1))[0]
    result = {"symbol": ticker, "eligible": False, "near_breakout": False,
              "data_date": sessions[-1], "observed_bars": len(present),
              "first_bar_date": sessions[present[0]] if len(present) else None,
              "last_bar_date": sessions[present[-1]] if len(present) else None}
    reason = data_error or quality(bars, sessions, rules.min_history)
    if reason:
        return result | {"data_valid": False, "reason": reason, "failed_filters": []}
    if quality(benchmark, sessions, len(sessions)):
        return result | {"data_valid": False, "reason": "invalid_benchmark", "failed_filters": []}
    close = float(bars[-1, 3])
    prior = bars[:-1]
    average_volume = float(prior[-rules.liquidity_days:, 4].mean())
    dollar_volume = float((prior[-rules.liquidity_days:, 3] * prior[-rules.liquidity_days:, 4]).mean())
    pivot = float(prior[-rules.breakout_days:, 1].max())
    sma50, sma200 = float(bars[-50:, 3].mean()), float(bars[-200:, 3].mean())
    volume_ratio = float(bars[-1, 4] / average_volume) if average_volume > 0 else 0
    stock_return = float(close / bars[-rules.rs_days-1, 3] - 1)
    spy_return = float(benchmark[-1, 3] / benchmark[-rules.rs_days-1, 3] - 1)
    extension, sma_extension = close / pivot - 1, close / sma50 - 1
    checks = {"minimum_price": close >= rules.min_price,
              "average_share_volume": average_volume >= rules.min_avg_volume,
              "average_dollar_volume": dollar_volume >= rules.min_avg_dollar_volume,
              "breakout": close > pivot,
              "volume_confirmation": volume_ratio >= rules.min_volume_ratio,
              "relative_strength": stock_return > spy_return and stock_return > 0,
              "trend": close > sma50 > sma200,
              "pivot_extension": extension <= rules.max_pivot_extension,
              "sma50_extension": sma_extension <= rules.max_sma50_extension}
    eligible = all(checks.values())
    # Watchlist may lack breakout and volume confirmation, but must pass other rules.
    near = (-rules.near_pivot_distance <= extension <= 0 and
            all(v for k, v in checks.items() if k not in {"breakout", "volume_confirmation"}))
    result.update(data_valid=True, reason="pass" if eligible else "filter_reject",
                  eligible=eligible, near_breakout=bool(near), close=close, pivot=pivot,
                  volume_ratio=volume_ratio, avg_volume_50=average_volume,
                  avg_dollar_volume_50=dollar_volume, sma50=sma50, sma200=sma200,
                  stock_return=stock_return, spy_return=spy_return, rs_excess=stock_return-spy_return,
                  pivot_extension=extension, sma50_extension=sma_extension,
                  checks=checks, failed_filters=[k for k, v in checks.items() if not v],
                  first_bar_date=sessions[present[0]], last_bar_date=sessions[present[-1]])
    return result
