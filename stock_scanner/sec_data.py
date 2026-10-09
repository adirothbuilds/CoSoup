"""Bounded public SEC research. No market-provider credentials or automatic retries."""
import fcntl
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.request
from datetime import date
from html.parser import HTMLParser
from xml.etree import ElementTree as ET

from .primary import SecRedirects, sec_user_agent
from .provider import fetched
from .storage import atomic_json, read_json

MAX_RESPONSE = 32_000_000
FORMS = {"10-K", "10-Q", "20-F", "40-F", "6-K", "8-K", "4", "4/A",
         "SC 13D", "SC 13D/A", "SC 13G", "SC 13G/A", "SCHEDULE 13D", "SCHEDULE 13G", "SCHEDULE 13D/A", "SCHEDULE 13G/A"}
LIMITATIONS = [
    "13F holdings describe a quarter-end snapshot, generally filed up to 45 days later; they are not live trades or purchase prices.",
    "13F excludes short positions and many other assets. Reported holdings are not the manager's entire portfolio.",
    "Only the selected managers are covered. A missing holding is not evidence of no institutional ownership.",
    "Share-count changes are differences between snapshots, not verified purchases or sales; splits and corporate actions may affect them.",
    "Issuer submissions list recent filings only. Insider and beneficial-ownership filing discovery is not exhaustive.",
    "Financial facts retain their reported periods. Year-to-date cash flow is not presented as a standalone quarter.",
]


class SecClient:
    def __init__(self, state, as_of, opener=None, checkpoint=None):
        date.fromisoformat(as_of)
        self.state, self.as_of = state, as_of
        self.opener = opener or urllib.request.build_opener(SecRedirects()).open
        self.checkpoint = checkpoint or (lambda **kw: None)
        self.errors, self.cache_paths = [], set()
        self.stopped = False
        self.requests = 0

    def get(self, url, kind="json"):
        from urllib.parse import urlsplit
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.netloc not in {"www.sec.gov", "data.sec.gov"}
                or parsed.username or parsed.password or parsed.query or parsed.fragment):
            raise ValueError("Only public HTTPS SEC endpoints are permitted")
        cache = self.state / "raw/sec" / self.as_of / (hashlib.sha256(url.encode()).hexdigest()+".json.gz")
        if cache.exists():
            self.cache_paths.add(cache)
            return read_json(cache)
        if self.stopped:
            return None
        self.state.mkdir(parents=True, exist_ok=True)
        try:
            user_agent = sec_user_agent()
            # The existing persistent budget also covers SEC; no credential is shared.
            with (self.state/"rate-limit.lock").open("a+") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                ledger = self.state/"rate-limit.json"
                prior = read_json(ledger) if ledger.exists() else {}
                now = time.time()
                if prior.get("cooldown_until", 0) > now:
                    raise ValueError("Shared request cooldown active; no request sent")
                stamps = [t for t in prior.get("requests", []) if t > now-60]
                wait = max(0, stamps[-1]+13-now if stamps else 0,
                           stamps[-5]+61-now if len(stamps) >= 5 else 0)
                while wait > 0:
                    self.checkpoint(stage="waiting_for_public_source_budget", requests=self.requests)
                    pause = min(wait, 2)
                    time.sleep(pause)
                    wait -= pause
                self.checkpoint(stage="reading_public_source", requests=self.requests)
                now = time.time()
                atomic_json(ledger, {**prior, "requests": [t for t in stamps if t > now-60]+[now]})
                request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json, application/xml, text/html"})
                self.requests += 1
                with self.opener(request, timeout=40) as response:
                    body = response.read(MAX_RESPONSE+1)
                if len(body) > MAX_RESPONSE:
                    raise ValueError("SEC response exceeds the bounded source size")
            text = body.decode("utf-8-sig")
            record = {"source": url, "checked_at": fetched(), "data": json.loads(text) if kind == "json" else text}
            atomic_json(cache, record)
            self.cache_paths.add(cache)
            return record
        except (urllib.error.URLError, OSError, ValueError, UnicodeError) as e:
            # Never save raw exception strings/response bodies, which may contain intermediary secrets.
            self.errors.append({"provider": "SEC", "endpoint": url,
                                "http_status": getattr(e, "code", "connection_failed"),
                                "message": str(e) if isinstance(e, ValueError) else "Public SEC request failed; no automatic retry"})
            self.stopped = True
            return None


def filing_rows(data, cik, as_of, forms=FORMS):
    recent = data.get("filings", {}).get("recent", {})
    rows = []
    for i, form in enumerate(recent.get("form", [])):
        def cell(key):
            values = recent.get(key, [])
            return values[i] if i < len(values) else ""
        acc, filed, period, document = (cell(k) for k in ("accessionNumber", "filingDate", "reportDate", "primaryDocument"))
        if form not in forms or not re.fullmatch(r"\d{10}-\d{2}-\d{6}", acc) or not filed or filed > as_of:
            continue
        # EDGAR also provides human-readable XML through a single XSL directory.
        if not re.fullmatch(r"(?:xsl[A-Za-z0-9_]+/)?[A-Za-z0-9][A-Za-z0-9_.-]*", document):
            continue
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}"
        rows.append({"form": form, "accession": acc, "filing_date": filed, "period_end": period,
                     "source": f"{base}/{document}", "index_url": f"{base}/index.json"})
    return sorted(rows, key=lambda r: (r["filing_date"], r["accession"]), reverse=True)


METRICS = {
    "Revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "Net income": ["NetIncomeLoss", "ProfitLoss"],
    "Operating income": ["OperatingIncomeLoss"],
    "Cash and equivalents": ["CashAndCashEquivalentsAtCarryingValue"],
    "Assets": ["Assets"], "Liabilities": ["Liabilities"],
    "Noncurrent debt": ["LongTermDebtNoncurrent", "LongTermDebtAndFinanceLeaseObligationsNoncurrent"],
    "Current debt": ["LongTermDebtCurrent"],
    "Operating cash flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "Capital expenditure": ["PaymentsToAcquirePropertyPlantAndEquipment"],
    "Diluted EPS": ["EarningsPerShareDiluted"],
}


def financial_series(data, cik, as_of):
    metrics = []
    for label, concepts in METRICS.items():
        unit = "USD/shares" if label == "Diluted EPS" else "USD"
        # Prefer one supported concept per metric, never add overlapping alternatives.
        for concept in concepts:
            rows = data.get("facts", {}).get("us-gaap", {}).get(concept, {}).get("units", {}).get(unit, [])
            valid = [r for r in rows if r.get("form") in {"10-K", "10-Q", "20-F", "40-F"}
                     and r.get("filed") and r["filed"] <= as_of and r.get("end") and r["end"] <= as_of
                     and isinstance(r.get("val"), (int, float)) and not isinstance(r["val"], bool)
                     and math.isfinite(r["val"]) and re.fullmatch(r"\d{10}-\d{2}-\d{6}", r.get("accn", ""))]
            if not valid:
                continue
            unique = {}
            for r in sorted(valid, key=lambda r: (r["filed"], r["accn"]), reverse=True):
                unique.setdefault((r.get("start"), r["end"]), r)
            for r in sorted(unique.values(), key=lambda r: (r["end"], r.get("start", "")), reverse=True)[:8]:
                acc = r["accn"]
                metrics.append({"label": label, "concept": concept, "value": r["val"], "unit": unit,
                                "period_start": r.get("start"), "period_end": r["end"], "filing_date": r["filed"],
                                "form": r["form"], "source": f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/{acc}-index.html"})
            break
    return metrics


class FilingText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.hidden = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "ix:header"}:
            self.hidden += 1
        if tag in {"p", "div", "tr", "br"}:
            self.parts.append("\n")
    def handle_endtag(self, tag):
        if tag in {"script", "style", "ix:header"}:
            self.hidden = max(0, self.hidden-1)
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data+" ")


def company(client, symbol, cik):
    output = {"symbol": symbol, "cik": str(cik), "metrics": [], "filings": [], "documents": [], "gaps": []}
    submissions = client.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    if not submissions:
        output["gaps"].append("Company submissions unavailable; no complete filing discovery was performed")
        return output
    if int(submissions["data"].get("cik", -1)) != int(cik):
        raise ValueError("SEC submissions issuer mismatch")
    output["name"] = submissions["data"].get("name", symbol)
    filings = filing_rows(submissions["data"], cik, client.as_of)
    output["filings"] = filings[:40]
    facts = client.get(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json")
    if facts:
        if int(facts["data"].get("cik", -1)) != int(cik):
            raise ValueError("SEC financial issuer mismatch")
        output["metrics"] = financial_series(facts["data"], cik, client.as_of)
    if not output["metrics"]:
        output["gaps"].append("Standard financial facts unavailable; missing values are not zero")
    for forms in ({"10-K", "20-F", "40-F"}, {"10-Q"}):
        filing = next((f for f in filings if f["form"] in forms), None)
        if not filing:
            output["gaps"].append("No recent "+"/".join(sorted(forms))+" filing discovered")
            continue
        document = client.get(filing["source"], "text")
        if document:
            parser = FilingText()
            parser.feed(document["data"])
            text = re.sub(r"[ \t]+", " ", "".join(parser.parts))
            text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
            output["documents"].append({**filing, "text_excerpt": text[:40000], "truncated": len(text) > 40000,
                                        "checked_at": document["checked_at"], "full_document_cached": True})
        else:
            output["gaps"].append(filing["form"]+" document could not be retrieved; link remains available")
    output["gaps"].append("Custom financial tags and full accounting-note interpretation require review of the original filing")
    return output


def parse_holdings(text, period, filing_date=None):
    # Entity expansion / external references are never accepted.
    if "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
        raise ValueError("SEC XML declarations are unsupported")
    root = ET.fromstring(text)
    output = {}
    for row in root.iter():
        if row.tag.split("}")[-1] != "infoTable":
            continue
        fields = {node.tag.split("}")[-1]: (node.text or "").strip() for node in row.iter()}
        cusip = fields.get("cusip", "")
        if not re.fullmatch(r"[A-Z0-9*#@]{9}", cusip):
            raise ValueError("Invalid 13F security identifier")
        shares, value = float(fields.get("sshPrnamt", "nan")), float(fields.get("value", "nan"))
        if not math.isfinite(shares) or not math.isfinite(value) or shares < 0 or value < 0:
            raise ValueError("Invalid 13F numeric value")
        # Before 2023, values were reported in thousands; current forms use dollars.
        if (filing_date or period) < "2023-01-03":
            value *= 1000
        key = (cusip, fields.get("titleOfClass", ""), fields.get("putCall", ""), fields.get("sshPrnamtType", ""))
        if key not in output:
            output[key] = {"cusip": cusip, "issuer": fields.get("nameOfIssuer", ""), "class": key[1],
                           "put_call": key[2], "amount_type": key[3], "shares": 0, "value_usd": 0}
        output[key]["shares"] += shares
        output[key]["value_usd"] += value
    if not output:
        raise ValueError("13F information table contains no recognized holdings")
    return sorted(output.values(), key=lambda r: r["value_usd"], reverse=True)


def manager(client, cik):
    result = {"cik": str(cik), "name": "CIK "+str(cik), "snapshots": [], "changes": [], "gaps": []}
    submissions = client.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json")
    if not submissions:
        result["gaps"].append("Manager filings unavailable; holdings are unknown")
        return result
    if int(submissions["data"].get("cik", -1)) != int(cik):
        raise ValueError("SEC manager issuer mismatch")
    result["name"] = submissions["data"].get("name", result["name"])
    filings = filing_rows(submissions["data"], cik, client.as_of, {"13F-HR", "13F-HR/A"})
    periods = sorted({f["period_end"] for f in filings if f["period_end"] and f["period_end"] <= client.as_of}, reverse=True)[:2]
    for period in periods:
        latest = [f for f in filings if f["period_end"] == period]
        base = next((f for f in latest if f["form"] == "13F-HR"), None)
        if not base or any(f["form"] == "13F-HR/A" for f in latest):
            result["gaps"].append(period+": amended or missing base filing; holdings comparison omitted rather than merging ambiguous amendments")
            continue
        index = client.get(base["index_url"])
        if not index:
            result["gaps"].append(period+": filing directory unavailable")
            break
        candidates = [r["name"] for r in index["data"].get("directory", {}).get("item", [])
                      if re.fullmatch(r"[A-Za-z0-9_.-]+\.xml", r.get("name", "")) and r["name"] != base["source"].rsplit("/", 1)[-1]]
        if len(candidates) != 1:
            result["gaps"].append(period+": information table could not be identified unambiguously")
            continue
        source = base["index_url"].rsplit("/", 1)[0]+"/"+candidates[0]
        table = client.get(source, "text")
        if not table:
            result["gaps"].append(period+": information table unavailable")
            break
        holdings = parse_holdings(table["data"], period, base["filing_date"])
        result["snapshots"].append({"period_end": period, "filing_date": base["filing_date"],
                                    "source": source, "holdings": holdings, "checked_at": table["checked_at"]})
    if len(result["snapshots"]) == 2:
        current, prior = result["snapshots"]
        # Require adjacent quarter-ends, not an arbitrary older filing.
        month = ((date.fromisoformat(current["period_end"]).month-1)//3)*3
        from calendar import monthrange
        y = date.fromisoformat(current["period_end"]).year
        expected = f"{y-1}-12-31" if month == 0 else f"{y}-{month:02d}-{monthrange(y, month)[1]:02d}"
        if prior["period_end"] != expected:
            result["gaps"].append("Adjacent quarter unavailable; changes omitted")
            return result
        def key(r): return (r["cusip"], r["class"], r["put_call"], r["amount_type"])
        now_rows, old_rows = ({key(r): r for r in snap["holdings"]} for snap in (current, prior))
        for identity in sorted(set(now_rows)|set(old_rows)):
            now_row, old_row = now_rows.get(identity), old_rows.get(identity)
            delta = (now_row or {}).get("shares", 0)-(old_row or {}).get("shares", 0)
            status = "newly_reported" if old_row is None else "no_longer_reported" if now_row is None else "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
            result["changes"].append({**(now_row or old_row), "change": status, "share_delta": delta,
                                      "prior_shares": (old_row or {}).get("shares", 0)})
    elif len(result["snapshots"]) < 2:
        result["gaps"].append("Two comparable quarterly snapshots are unavailable; changes are unknown")
    return result
