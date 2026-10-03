"""Sourced provider research; gaps remain explicit, no invented catalyst/earnings date."""
from datetime import date, timedelta
from urllib.parse import quote, urlsplit
import re

from .calendar import utc_now
from .provider import BASE, ProviderError, fetched
from .storage import atomic_json, read_json
from .primary import sec_company_facts, sec_metrics


def source_url(value, fallback):
    if isinstance(value, str):
        parsed = urlsplit(value)
        if parsed.scheme in {"http", "https"} and parsed.netloc and not parsed.username and not parsed.password:
            return value
    return fallback


def filing_source(value, fallback, cik=None):
    """Public SEC accession index, derived from the provider's filing identifier.

    This is a reference to the primary filing, not a claim that the index was fetched.
    Do not forward the Massive credential to legacy api.polygon.io URLs.
    """
    safe = source_url(value, fallback)
    accession = re.search(r"(?<!\d)(\d{10}-\d{2}-\d{6})(?!\d)", value if isinstance(value, str) else safe)
    if not accession or cik is None or not re.fullmatch(r"\d{1,10}", str(cik)):
        return safe
    number = accession.group(1)
    # Accession prefixes may identify a filing AGENT, not the reporting issuer.
    return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{number.replace('-', '')}/{number}-index.html"


class Researcher:
    def __init__(self, client, as_of, recheck=False):
        self.client, self.as_of = client, as_of
        self.blocked, self.errors = {}, []
        self.recheck = recheck

    def request(self, category, symbol, path, params=None):
        cache = self.client.state / "raw" / "research" / self.as_of / (quote(symbol, safe="") + "_" + category + ".json.gz")
        if cache.exists():
            return read_json(cache)
        blocked = self.client.state / "raw" / "research" / self.as_of / ("_blocked_" + category + ".json")
        if blocked.exists() and not self.recheck:
            error = read_json(blocked)
            if error not in self.errors: self.errors.append(error)
            self.blocked[category] = error
        if category in self.blocked or "all" in self.blocked:
            return {"error": self.blocked.get(category, self.blocked.get("all"))}
        try:
            data = self.client.get(path, params)
            record = {"checked_at": fetched(), "source": BASE + path, "data": data}
            atomic_json(cache, record)
            return record
        except ProviderError as e:
            error = e.as_dict()
            print(str(e), flush=True)
            self.errors.append(error)
            # One diagnosis per inaccessible endpoint, never hammer paid endpoints.
            if e.status in {401, 403, 404, 410}:
                self.blocked[category] = error
                atomic_json(blocked, error)
            if e.status in {429, "connection_failed", "missing_credential"}:
                self.blocked["all"] = error
            return {"error": error}

    def details(self, symbol):
        record = self.request("details", symbol, "/v3/reference/tickers/" + quote(symbol, safe=""), {"date": self.as_of})
        return record, record.get("data", {}).get("results", {})

    def candidate(self, result):
        symbol = result["symbol"]
        facts, hypotheses, missing = [], [], []
        details_record, details = self.details(symbol)

        def fact(text, record, source=None):
            facts.append({"text": text, "source": source or record["source"], "checked_at": record["checked_at"],
                          "data_retrieved_from": record["source"],
                          "linked_primary_source_retrieved": source is None or source == record["source"]})

        if details_record.get("error"):
            missing.append("Company details inaccessible: " + str(details_record["error"]))
        else:
            if details.get("description"):
                fact("Business activity according to the provider: " + details["description"], details_record)
            if details.get("market_cap") is not None:
                fact(f"Provider market cap as of {self.as_of}: ${details['market_cap']:,.0f}", details_record)
            if details.get("homepage_url"):
                fact("Company website for official publications and primary-source review", details_record,
                     source_url(details["homepage_url"], details_record["source"]))
            if not details.get("description"):
                missing.append("No company activity description is available from this source")

        now = utc_now()
        news = self.request("news", symbol, "/v2/reference/news",
                            {"ticker": symbol, "published_utc.gte": (now-timedelta(days=60)).isoformat(),
                             "published_utc.lte": now.isoformat(), "limit": 5, "sort": "published_utc", "order": "desc"})
        if news.get("error"):
            missing.append("News source inaccessible: " + str(news["error"]))
        else:
            articles = news.get("data", {}).get("results", [])
            for article in articles:
                title, published = article.get("title"), article.get("published_utc")
                if title and published:
                    fact(f"Documented news headline ({published}): {title}; a headline is not independent verification of its contents", news,
                         source_url(article.get("article_url"), news["source"]))
            if not articles:
                missing.append("No news returned in the last 60 days; absence of a catalyst cannot be inferred")
            else:
                hypotheses.append("Investigate whether dated news relates to the breakout; proximity in time does not establish causality")

        params = {"tickers": symbol, "filing_date.lte": self.as_of, "period_end.lte": self.as_of,
                  "sort": "period_end.desc", "limit": 2}
        balance = self.request("balance_sheet", symbol, "/stocks/financials/v1/balance-sheets", params)
        cash = self.request("cash_flow", symbol, "/stocks/financials/v1/cash-flow-statements", params)
        calendars = self.request("earnings", symbol, "/benzinga/v1/earnings",
                                 {"ticker": symbol, "date.gte": now.date().isoformat(), "limit": 1, "sort": "date.asc"})
        modern_fields = {
            "balance_sheet": (balance, {"debt_current": "Current debt", "long_term_debt_and_capital_lease_obligations": "Long-term debt and capital leases", "cash_and_equivalents": "Cash and equivalents"}),
            "cash_flow": (cash, {"net_cash_from_operating_activities": "Operating cash flow", "net_cash_from_financing_activities": "Financing cash flow"}),
        }
        financial_observations = 0
        observed_topics = set()
        for category, (record, field_labels) in modern_fields.items():
            if record.get("error"):
                missing.append(category + " access blocked: " + str(record["error"]))
                continue
            rows = record.get("data", {}).get("results", [])
            if not rows:
                missing.append("No " + category + " records returned")
                continue
            current = rows[0]
            if symbol not in current.get("tickers", []) or (details.get("cik") and int(current.get("cik", -1)) != int(details["cik"])):
                missing.append("Financial issuer mismatch; data omitted")
                continue
            fact(f"{category} record: {current.get('timeframe')}, period end {current.get('period_end')}, filed {current.get('filing_date')}", record)
            for field, label in field_labels.items():
                if current.get(field) is not None:
                    fact(f"{label}, reported units, period through {current.get('period_end')}: {current[field]:,.0f}", record)
                    financial_observations += 1
                    if "debt" in field: observed_topics.add("debt")
                    if "operating" in field: observed_topics.add("operating_cash_flow")
        if calendars.get("error"):
            missing.append("Earnings calendar access blocked: " + str(calendars["error"]))
        else:
            for event in calendars.get("data", {}).get("results", []):
                if event.get("ticker") == symbol and event.get("date", "") >= now.date().isoformat():
                    fact(f"Provider earnings calendar: {event['date']}; date status {event.get('date_status')}; independently confirm with investor relations", calendars)
        # Free primary filings can fill financial gaps after public-network access is enabled.
        if balance.get("error") or cash.get("error"):
            primary = {"error": self.blocked["sec"]} if "sec" in self.blocked else sec_company_facts(self.client.state, details.get("cik"), self.as_of, self.recheck)
            if primary.get("error"):
                self.blocked["sec"] = primary["error"]
                missing.append("Primary SEC research blocked: " + str(primary["error"]))
                if primary["error"] not in self.errors: self.errors.append(primary["error"])
            else:
                for metric in sec_metrics(primary, self.as_of):
                    financial_observations += 1
                    if "Debt" in metric["concept"] or "Borrowings" in metric["concept"]: observed_topics.add("debt")
                    if "OperatingActivities" in metric["concept"]: observed_topics.add("operating_cash_flow")
                    source = filing_source(metric.get("accession"), primary["source"], details.get("cik"))
                    fact(f"{metric['label']}: {metric['value']:,.0f} {metric['unit']}; period {metric.get('period_start')} through {metric['period_end']}; filed {metric['filing_date']}", primary, source)
        # Never call the deprecated /vX endpoint. Previously retrieved data is an archive only.
        archived_path = self.client.state / "raw" / "research" / self.as_of / (quote(symbol, safe="") + "_financials.json.gz")
        if archived_path.exists() and not financial_observations:
            archive = read_json(archived_path)
            rows = archive.get("data", {}).get("results", [])
            if rows and symbol in rows[0].get("tickers", []):
                current = rows[0]
                source = filing_source(current.get("source_filing_url"), archive["source"], current.get("cik"))
                fact(f"Archived quarterly record from the deprecated endpoint: period through {current.get('end_date')}, filed {current.get('filing_date')}; this is not a fresh latest-filing check", archive, source)
                for section, fields in {"cash_flow_statement": {"net_cash_flow_from_operating_activities": "Archived operating cash flow", "net_cash_flow_from_financing_activities": "Archived financing cash flow"},
                                        "income_statement": {"basic_average_shares": "Archived basic average shares", "diluted_average_shares": "Archived diluted average shares"}}.items():
                    for field, label in fields.items():
                        value = current.get("financials", {}).get(section, {}).get(field, {})
                        if value.get("value") is not None:
                            fact(f"{label}, period through {current.get('end_date')}: {value['value']:,.0f} {value.get('unit', '')}", archive, source)
            missing.append("Archived data is not current financial verification; latest annual and quarterly filings still require primary-source review")
        if not financial_observations:
            missing.append("Current debt/cash-flow data unavailable; missing debt is not zero and liabilities cannot substitute for debt")
        if "debt" not in observed_topics:
            missing.append("Current financial debt amounts are not verified")
        if "operating_cash_flow" not in observed_topics:
            missing.append("Current operating cash flow is not verified; any archived amount is historical only")
        missing += ["Next earnings date is not verified in an official event calendar; check investor relations before making a decision",
                    "Review warrants, convertibles, shelf/ATM registrations and recent offerings; missing source fields do not establish absence of dilution risk",
                    "No causal catalyst for the breakout is established; research uses available sources, not causality inferred from price movement"]
        hypotheses.append("Relative strength and a volume breakout may justify further research; they are not a verified forecast of continued gains")
        return {"status": "incomplete_requires_primary_source_review", "facts": facts,
                "hypotheses": hypotheses, "missing": missing, "checked_at": fetched()}

    def liquidity_examples(self, results, metadata, limit=5):
        failures = [r for r in results if r.get("data_valid") and any(
            k in r["failed_filters"] for k in ("average_share_volume", "average_dollar_volume"))]
        # Near the liquidity cutoff, above the price floor: useful examples, not a market-cap sample.
        failures.sort(key=lambda r: (r["close"] >= 5 and r["avg_dollar_volume_50"] < 10_000_000,
                                      r["avg_dollar_volume_50"]), reverse=True)
        examples = []
        for result in failures[:limit]:
            record, details = self.details(result["symbol"])
            cap = details.get("market_cap")
            cap_class = None if cap is None else ("small (<$2B)" if cap < 2e9 else "mid ($2B–$10B)" if cap < 1e10 else "large (≥$10B)")
            examples.append({"symbol": result["symbol"], "name": metadata[result["symbol"]].get("name"),
                             "avg_volume_50": result["avg_volume_50"], "avg_dollar_volume_50": result["avg_dollar_volume_50"],
                             "liquidity_failures": [k for k in result["failed_filters"] if k in {"average_share_volume", "average_dollar_volume"}],
                             "market_cap": cap, "cap_class": cap_class,
                             "source": record.get("source"), "checked_at": record.get("checked_at"), "error": record.get("error")})
        return examples
