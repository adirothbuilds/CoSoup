"""Descriptive calculations on verified, split-consistent daily bars.

These measurements do not change eligibility or estimate return probabilities.
Percentage fields use percentage points (e.g. 5 means 5%).
"""
import numpy as np


def technical(bars, benchmark, pivot, volume_threshold=1.5):
    close = bars[:, 3]
    previous = close[:-1]
    true_range = np.maximum.reduce((bars[1:, 1]-bars[1:, 2],
                                    np.abs(bars[1:, 1]-previous),
                                    np.abs(bars[1:, 2]-previous)))
    atr = float(true_range[-14:].mean())
    returns = np.diff(np.log(close[-21:]))
    prior_range = true_range[:-1]
    baseline = float(prior_range[-50:-10].mean())
    confirmation = []
    for i in range(len(bars)-5, len(bars)):
        average = float(bars[i-50:i, 4].mean())
        confirmation.append(average > 0 and bars[i, 4]/average >= volume_threshold)
    relative = {}
    for window in (21, 63, 126):
        if len(close) <= window or not np.isfinite(bars[-window-1:]).all():
            continue
        stock = float(close[-1]/close[-window-1]-1)
        market = float(benchmark[-1, 3]/benchmark[-window-1, 3]-1)
        relative[str(window)] = {"stock_change_pct": stock*100,
                                 "spy_change_pct": market*100,
                                 "excess_pct": (stock-market)*100}
    recent = close[-64:]
    return {"atr14": atr, "atr14_pct": atr/float(close[-1])*100,
            "pivot_distance_atr": float((close[-1]-pivot)/atr) if atr > 0 else None,
            "realized_volatility20_pct": float(returns.std(ddof=1)*np.sqrt(252)*100),
            "prior_range_contraction_ratio": float(prior_range[-10:].mean()/baseline) if baseline > 0 else None,
            "volume_confirmed_days5": sum(bool(v) for v in confirmation),
            "max_close_drawdown63_pct": float((recent/np.maximum.accumulate(recent)-1).min()*100),
            "relative_strength_windows": relative,
            "method": "ATR: mean of last 14 true ranges. Volatility: sample standard deviation of 20 daily log changes, annualized by sqrt(252). Range contraction: prior 10 versus preceding 40 true ranges, excluding the current session. Volume confirmation: each of five sessions versus its own prior 50-session mean. Price changes exclude dividends."}


def breadth(results, data_date):
    valid = [r for r in results if r.get("data_valid")]
    count = len(valid)
    measures = {"above_sma50": sum(r["close"] > r["sma50"] for r in valid),
                "above_sma200": sum(r["close"] > r["sma200"] for r in valid),
                "positive_excess_vs_spy": sum(r["rs_excess"] > 0 for r in valid),
                "above_breakout_pivot": sum(r["close"] > r["pivot"] for r in valid)}
    return {"data_date": data_date, "evaluated": len(results), "valid_histories": count,
            "excluded_histories": len(results)-count,
            "measures": {k: {"count": v, "pct": v/count*100 if count else None} for k, v in measures.items()},
            "note": "Equal-weight observations among verified histories in this report's dated listing universe only. Missing histories are excluded and disclosed; this is not whole-market breadth or a historical strategy backtest."}
