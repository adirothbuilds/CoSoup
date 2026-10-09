"""Public SEC company facts. No Massive credential is used or forwarded."""
import fcntl
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

from .provider import fetched
from .storage import atomic_json, read_json


class SecRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        from urllib.parse import urlsplit
        url = urlsplit(newurl)
        if url.scheme != 'https' or url.netloc not in {'data.sec.gov', 'www.sec.gov'}:
            raise ValueError('Refusing an unexpected SEC redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def validate_sec_user_agent(value):
    """Validate a truthful contact header without including its value in errors."""
    if (not isinstance(value, str) or not 8 <= len(value) <= 512
            or any(ord(char) < 32 or ord(char) > 126 for char in value)
            or not re.search(r"\S+\s+[^\s<>@]+@[^\s<>@]+\.[A-Za-z]{2,}", value)
            or "noreply" in value.lower()):
        raise ValueError("Set SEC_USER_AGENT to an application name and a reachable contact email in private configuration")
    return value


def sec_user_agent():
    """The file takes precedence so ambient shell values cannot replace deployment identity."""
    path = os.environ.get("SEC_USER_AGENT_FILE")
    if path:
        try:
            with Path(path).open("rb") as stream:
                data = stream.read(513)
            value = data.decode("ascii")
        except (OSError, UnicodeError):
            raise ValueError("SEC contact configuration is unavailable; prepare the private deployment before syncing") from None
    else:
        value = os.environ.get("SEC_USER_AGENT", "")
    return validate_sec_user_agent(value)


def sec_company_facts(state, cik, as_of, recheck=False, opener=None):
    if not cik or not str(cik).isdigit():
        return {'error': {'provider': 'SEC', 'message': 'Issuer CIK unavailable'}}
    cik = int(cik)
    directory = state / 'raw' / 'research' / as_of
    cache = directory / f'SEC_{cik}.json.gz'
    blocked = directory / '_blocked_sec.json'
    if cache.exists():
        return read_json(cache)
    if blocked.exists() and not recheck:
        return {'error': read_json(blocked)}
    url = f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json'
    try:
        request = urllib.request.Request(url, headers={'User-Agent': sec_user_agent()})
        # Share the same conservative request budget; credentials are not shared.
        with (state / 'rate-limit.lock').open('a+') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            ledger = state / 'rate-limit.json'
            prior = read_json(ledger) if ledger.exists() else {}
            now = time.time()
            if prior.get('cooldown_until', 0) > now:
                return {'error': {'provider': 'SEC', 'message': 'Shared request cooldown active; no request sent'}}
            stamps = [t for t in prior.get('requests', []) if t > now-60]
            delay = max(0, stamps[-1]+13-now if stamps else 0, stamps[-5]+61-now if len(stamps)>=5 else 0)
            if delay: time.sleep(delay)
            now = time.time()
            atomic_json(ledger, {'requests': [t for t in stamps if t > now-60]+[now]})
            with (opener or urllib.request.build_opener(SecRedirects()).open)(request, timeout=40) as response:
                data = json.load(response)
        if int(data.get('cik', -1)) != cik:
            raise ValueError('SEC response issuer does not match requested CIK')
        record = {'source': url, 'checked_at': fetched(), 'data': data}
        atomic_json(cache, record)
        return record
    except (urllib.error.URLError, OSError, ValueError, TypeError) as e:
        error = {'provider': 'SEC', 'endpoint': url, 'http_status': getattr(e, 'code', 'connection_failed'),
                 'message': str(getattr(e, 'reason', e))[:500]}
        print('SEC research blocked:', error, flush=True)
        atomic_json(blocked, error)
        return {'error': error}


def sec_metrics(record, as_of):
    """Latest dated facts, preserving each fact's period/unit; no invented totals."""
    if record.get('error'): return []
    concepts = {
        ('us-gaap', 'LongTermDebtCurrent', 'USD'): 'Current portion of long-term debt',
        ('us-gaap', 'LongTermDebtNoncurrent', 'USD'): 'Noncurrent long-term debt',
        ('us-gaap', 'LongTermDebtAndFinanceLeaseObligationsNoncurrent', 'USD'): 'Noncurrent debt and finance leases',
        ('us-gaap', 'ShortTermBorrowings', 'USD'): 'Short-term borrowings',
        ('us-gaap', 'CashAndCashEquivalentsAtCarryingValue', 'USD'): 'Cash and cash equivalents',
        ('us-gaap', 'NetCashProvidedByUsedInOperatingActivities', 'USD'): 'Operating cash flow',
        ('us-gaap', 'NetCashProvidedByUsedInFinancingActivities', 'USD'): 'Financing cash flow',
        ('dei', 'EntityCommonStockSharesOutstanding', 'shares'): 'Common shares outstanding',
        ('us-gaap', 'WeightedAverageNumberOfDilutedSharesOutstanding', 'shares'): 'Weighted average diluted shares',
    }
    out = []
    for (namespace, concept, unit), label in concepts.items():
        entries = record['data'].get('facts', {}).get(namespace, {}).get(concept, {}).get('units', {}).get(unit, [])
        valid = [r for r in entries if r.get('form') in {'10-K','10-Q','20-F','40-F'} and
                 r.get('filed', '') <= as_of and r.get('end', '') <= as_of and r.get('end') and r.get('filed') and
                 isinstance(r.get('val'), (int,float)) and not isinstance(r.get('val'),bool) and math.isfinite(r['val'])]
        if not valid: continue
        row = max(valid,key=lambda r:(r['end'],r['filed'],r.get('start','')))
        out.append({'label':label,'value':row['val'],'unit':unit,'period_start':row.get('start'),
                    'period_end':row['end'],'filing_date':row['filed'],'accession':row.get('accn'), 'concept':concept})
    return out
