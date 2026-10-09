"""Period-aligned financial calculations; absent inputs remain explicit gaps."""
import math
from datetime import date


def financial_analysis(company, cutoff):
    gaps, indexed = [], {}
    for row in company.get("metrics", []):
        try:
            start = row.get("period_start")
            end = row["period_end"]
            date.fromisoformat(end)
            date.fromisoformat(row["filing_date"])
            duration = (date.fromisoformat(end)-date.fromisoformat(start)).days if start else 0
            if duration < 0 or end > cutoff or row["filing_date"] > cutoff:
                continue
            value = row["value"]
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                continue
            key = (row["label"], row["unit"], start, end)
            old = indexed.get(key)
            if old is None or row["filing_date"] > old["filing_date"]:
                indexed[key] = row
            elif row["filing_date"] == old["filing_date"] and value != old["value"]:
                gaps.append("Conflicting facts for "+row["label"]+" ending "+end)
                indexed[key] = {**old, "value": None}
        except (KeyError, TypeError, ValueError):
            gaps.append("Malformed financial observation excluded")
    indexed = {k: v for k, v in indexed.items() if v["value"] is not None}
    derived = []

    def emit(label, value, unit, rows):
        first = rows[0]
        derived.append({"label": label, "value": value, "unit": unit,
                        "period_start": first.get("period_start"), "period_end": first["period_end"],
                        "filing_date": max(r["filing_date"] for r in rows),
                        "sources": list(dict.fromkeys(r["source"] for r in rows)),
                        "inputs": [{k: r.get(k) for k in ("label", "value", "unit", "period_start", "period_end", "filing_date")} for r in rows]})

    pairs = [("Operating margin", "Operating income", "Revenue", "%", "ratio"),
             ("Net margin", "Net income", "Revenue", "%", "ratio"),
             ("Operating cash flow margin", "Operating cash flow", "Revenue", "%", "ratio"),
             ("Cash conversion", "Operating cash flow", "Net income", "times", "ratio"),
             ("Free cash flow", "Operating cash flow", "Capital expenditure", "USD", "subtract"),
             ("Cash / assets", "Cash and equivalents", "Assets", "%", "ratio")]
    for label, numerator, denominator, unit, operation in pairs:
        found = False
        for (name, input_unit, start, end), left in indexed.items():
            if name != numerator or input_unit != "USD":
                continue
            right = indexed.get((denominator, input_unit, start, end))
            if right is None:
                continue
            if operation == "ratio" and right["value"] <= 0:
                continue
            if operation == "subtract" and right["value"] < 0:
                continue
            value = left["value"]-right["value"] if operation == "subtract" else left["value"]/right["value"]*(100 if unit == "%" else 1)
            emit(label, value, unit, [left, right]); found = True
        if not found:
            gaps.append(label+": matching USD periods and valid denominator/payment values unavailable")
    for name in ("Revenue", "Net income", "Diluted EPS"):
        rows = [r for r in indexed.values() if r["label"] == name and r.get("period_start")]
        found = False
        for current in rows:
            end = date.fromisoformat(current["period_end"])
            start = date.fromisoformat(current["period_start"])
            comparable = [r for r in rows if r["unit"] == current["unit"]
                          and 350 <= (end-date.fromisoformat(r["period_end"])).days <= 380
                          and 350 <= (start-date.fromisoformat(r["period_start"])).days <= 380
                          and abs((end-start).days-(date.fromisoformat(r["period_end"])-date.fromisoformat(r["period_start"])).days) <= 7
                          and r["value"] > 0]
            if comparable:
                prior = min(comparable, key=lambda r: abs((end-date.fromisoformat(r["period_end"])).days-365))
                emit(name+" YoY change", (current["value"]/prior["value"]-1)*100, "%", [current, prior]); found = True
        if not found:
            gaps.append(name+" YoY change: comparable prior-year period with positive base unavailable")
    return {"symbol": company["symbol"], "knowledge_cutoff": cutoff, "series": derived,
            "gaps": list(dict.fromkeys(gaps)),
            "method": "Ratios require identical start/end dates and USD units. Free cash flow is operating cash flow minus reported nonnegative capital expenditure for that same period. Growth compares similar-duration periods about one year apart, with a positive base. No overlapping quarterly/YTD/annual periods are summed. Noncurrent debt alone is not total debt. Ratios describe reported accounting data, not valuation or forecasts."}


def institutional_analysis(manager):
    snapshots = []
    for snapshot in manager.get("snapshots", []):
        equities = [h for h in snapshot.get("holdings", []) if not h.get("put_call") and h.get("amount_type") == "SH"]
        total = sum(h["value_usd"] for h in equities)
        rows = sorted(equities, key=lambda h: h["value_usd"], reverse=True)
        snapshots.append({"period_end": snapshot["period_end"], "filing_date": snapshot["filing_date"],
                          "source": snapshot["source"], "reported_equity_value_usd": total,
                          "equity_positions": len(rows), "excluded_positions": len(snapshot.get("holdings", []))-len(rows),
                          "top5_weight_pct": sum(h["value_usd"] for h in rows[:5])/total*100 if total > 0 else None,
                          "positions": [{**h, "weight_pct": h["value_usd"]/total*100 if total > 0 else None} for h in rows]})
    return {"name": manager.get("name"), "cik": manager["cik"], "snapshots": snapshots,
            "changes": manager.get("changes", []), "gaps": manager.get("gaps", []),
            "note": "Weights use all reported non-option SH positions in the supplied snapshot, not total managed assets. Changes are reported share-count differences, not confirmed trades; splits and other corporate actions may affect them."}


def institutional_overlap(managers):
    eligible = [m for m in managers if m.get("snapshots")]
    if len(eligible) < 2:
        return {"positions": [], "gaps": ["At least two managers with comparable snapshots are required"]}
    periods = set.intersection(*(set(s["period_end"] for s in m["snapshots"]) for m in eligible))
    if not periods:
        return {"positions": [], "gaps": ["Managers have no common reported quarter; overlap omitted"]}
    period, by_security = max(periods), {}
    for manager in eligible:
        snapshot = next(s for s in manager["snapshots"] if s["period_end"] == period)
        for holding in snapshot["positions"]:
            key = (holding["cusip"], holding["class"], holding["amount_type"])
            by_security.setdefault(key, []).append({"manager": manager["name"], "cik": manager["cik"],
                                                   "filing_date": snapshot["filing_date"], "source": snapshot["source"],
                                                   "weight_pct": holding["weight_pct"], "shares": holding["shares"],
                                                   "issuer": holding["issuer"]})
    return {"period_end": period, "manager_count": len(eligible),
            "positions": [{"cusip": k[0], "class": k[1], "holders": v} for k, v in sorted(by_security.items()) if len(v) > 1],
            "gaps": [], "note": "Exact CUSIP, class and SH matching within the same quarter. No guessed ticker mapping or inference about managers outside the selected coverage."}
