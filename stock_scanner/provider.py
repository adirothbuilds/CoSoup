"""Massive HTTPS only; shared persistent rate limit; no automatic retries."""
import fcntl
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from .storage import atomic_json, read_json

BASE = "https://api.massive.com"


class ScopedRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https" or parsed.netloc != "api.massive.com":
            raise ProviderError("unsafe_redirect", urllib.parse.urlsplit(req.full_url).path,
                                "Refusing to forward credentials outside the authorized HTTPS host")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class ProviderError(RuntimeError):
    def __init__(self, status, endpoint, message):
        self.status, self.endpoint, self.message = status, endpoint, message
        super().__init__(f"Massive HTTP {status} {endpoint}: {message}")

    def as_dict(self):
        return {"provider": "Massive", "http_status": self.status,
                "endpoint": self.endpoint, "message": self.message}


def clean_message(message, key):
    text = str(message).replace(key, "[REDACTED]") if key else str(message)
    return re.sub(r"(?i)(apikey|api_key|authorization)([\s:=]+)[^\s&,\"}]+", r"\1\2[REDACTED]", text)[:1000]


def scrub_payload(value, key):
    """Avoid persisting a credential even if a provider response reflects it."""
    if isinstance(value, dict):
        return {k: scrub_payload(v, key) for k, v in value.items()
                if k.lower() not in {"apikey", "api_key", "authorization", "access_token"}}
    if isinstance(value, list):
        return [scrub_payload(v, key) for v in value]
    if isinstance(value, str) and key:
        return value.replace(key, "[REDACTED]")
    return value


class Client:
    def __init__(self, state, key=None, opener=None, clock=time.time, sleep=time.sleep):
        self.state = state
        self.key = key if key is not None else os.environ.get("MASSIVE_API_KEY")
        self.opener = opener or urllib.request.build_opener(ScopedRedirects()).open
        self.clock, self.sleep = clock, sleep
        if not self.key:
            raise ProviderError("missing_credential", "/", "MASSIVE_API_KEY is absent; configure its Network secret for api.massive.com")

    def get(self, path, params=None):
        url = urllib.parse.urljoin(BASE, path)
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "api.massive.com":
            raise ProviderError("unsafe_url", "/", "Refusing credentials outside https://api.massive.com")
        if params:
            url += ("&" if parsed.query else "?") + urllib.parse.urlencode(params)
        # Credential stays in the supported HTTPS Authorization route, never in URLs/cache.
        req = urllib.request.Request(url, headers={"Authorization": "Bearer " + self.key,
                                                   "User-Agent": "PersonalStockResearch/1.0"})
        lock = self.state / "rate-limit.lock"
        ledger = self.state / "rate-limit.json"
        with lock.open("a+") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            saved = read_json(ledger) if ledger.exists() else {}
            now = self.clock()
            if saved.get("cooldown_until", 0) > now:
                raise ProviderError(429, parsed.path, "Persistent provider cooldown active; no request sent")
            stamps = [t for t in saved.get("requests", []) if t > now - 60]
            delay = max(0, (stamps[-1] + 13 - now) if stamps else 0,
                        (stamps[-5] + 61 - now) if len(stamps) >= 5 else 0)
            if delay:
                self.sleep(delay)
            now = self.clock()
            stamps = [t for t in stamps if t > now - 60] + [now]
            atomic_json(ledger, {"requests": stamps})
            try:
                with self.opener(req, timeout=40) as response:
                    data = json.load(response)
            except urllib.error.HTTPError as e:
                try:
                    body = json.load(e)
                    message = body.get("error") or body.get("message") or e.reason
                except (ValueError, AttributeError):
                    message = e.reason
                if e.code == 429:
                    try:
                        wait = max(60, float(e.headers.get("Retry-After", "60")))
                    except ValueError:
                        wait = 60
                    atomic_json(ledger, {"requests": stamps, "cooldown_until": now + wait})
                raise ProviderError(e.code, parsed.path, clean_message(message, self.key)) from None
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                reason = getattr(e, "reason", e)
                raise ProviderError("connection_failed", parsed.path,
                                    "HTTPS request failed: " + clean_message(reason, self.key) + "; no automatic retry") from None
            except ValueError:
                raise ProviderError("invalid_json", parsed.path, "Provider returned invalid JSON") from None
            if not isinstance(data, dict):
                raise ProviderError("invalid_response", parsed.path, "Expected a JSON object")
            if data.get("status") in {"ERROR", "NOT_AUTHORIZED"}:
                raise ProviderError(data["status"], parsed.path, clean_message(data.get("error", data.get("message", "Provider error")), self.key))
            return scrub_payload(data, self.key)

    def pages(self, path, params=None):
        rows, seen = [], set()
        for _ in range(1000):
            data = self.get(path, params)
            page = data.get("results", [])
            if not isinstance(page, list):
                raise ProviderError("invalid_results", path, "Expected a result list")
            rows.extend(page)
            next_url = data.get("next_url")
            if not next_url:
                return rows
            if next_url in seen:
                raise ProviderError("pagination_loop", path, "Repeated next_url; stopped")
            seen.add(next_url)
            path, params = next_url, None
        raise ProviderError("pagination_limit", path, "Exceeded safety limit")


def fetched():
    return datetime.now(timezone.utc).isoformat()


def grouped(client, session):
    path = f"/v2/aggs/grouped/locale/us/market/stocks/{session}"
    # Apply splits locally to BOTH prices and share volume; retain raw unadjusted bars.
    data = client.get(path, {"adjusted": "false", "include_otc": "false"})
    if data.get("adjusted") is not False or not data.get("results"):
        raise ProviderError("invalid_grouped", path, "Expected nonempty unadjusted daily bars")
    return {"session": session, "retrieved_at": fetched(), "source": BASE + path,
            "adjusted": False, "data": data}


def ensure_grouped(client, sessions, progress=print):
    for index, session in enumerate(sessions):
        path = client.state / "raw" / "grouped" / (session + ".json.gz")
        if path.exists():
            try:
                cached = read_json(path)
                valid = cached.get("session") == session and cached.get("adjusted") is False and cached["data"].get("adjusted") is False and bool(cached["data"].get("results"))
            except (OSError, EOFError, ValueError, KeyError):
                valid = False
            if valid:
                continue
        value = grouped(client, session)
        atomic_json(path, value)
        progress(f"Cached daily market {session} ({index+1}/{len(sessions)}), {len(value['data']['results'])} bars", flush=True)


def universe(client, session):
    path = client.state / "raw" / "universe" / (session + ".json.gz")
    if path.exists():
        return read_json(path)
    rows = client.pages("/v3/reference/tickers", {"market": "stocks", "locale": "us", "active": "true",
                                                   "date": session, "limit": 1000, "sort": "ticker", "order": "asc"})
    if not rows:
        raise ProviderError("empty_universe", "/v3/reference/tickers", "No US listings returned")
    value = {"as_of": session, "retrieved_at": fetched(), "source": BASE + "/v3/reference/tickers", "results": rows}
    atomic_json(path, value)
    return value


def splits(client, first, last):
    path = client.state / "raw" / "splits" / (first + "_" + last + ".json.gz")
    if path.exists():
        return read_json(path)
    rows = client.pages("/v3/reference/splits", {"execution_date.gte": first, "execution_date.lte": last,
                                                "limit": 1000, "sort": "execution_date", "order": "asc"})
    value = {"first": first, "last": last, "retrieved_at": fetched(), "results": rows,
             "source": BASE + "/v3/reference/splits"}
    atomic_json(path, value)
    return value
