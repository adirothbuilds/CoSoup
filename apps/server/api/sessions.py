"""Revocable owner sessions. Only a digest of the cookie is stored in PostgreSQL."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select

from ..errors import ServiceError
from ..persistence.models import Policy


class BrowserSessions:
    def __init__(self, settings, database, verifier):
        self.settings, self.database, self.verifier = settings, database, verifier.hex()
        self.cookie = "__Host-scanner_session" if settings.browser_secure_cookie else "scanner_dev_session"

    def check_origin(self, request):
        if not self.settings.browser_origin:
            raise ServiceError("browser_not_configured", "Configure the private browser_origin before connecting", 503)
        if request.headers.get("origin") != self.settings.browser_origin:
            raise ServiceError("invalid_origin", "Request origin does not match the configured private browser origin", 403)

    def identity(self, value):
        return "session:" + hashlib.sha256(value.encode()).hexdigest()

    def read(self, request, mutation=True):
        value = request.cookies.get(self.cookie, "")
        if not value or len(value) > 128:
            raise ServiceError("session_expired", "Connect to the private server again", 401)
        with self.database.session() as db:
            row = db.get(Policy, self.identity(value))
            data = row.values if row and row.owner_id == self.settings.owner_id else None
        if not data or data["verifier"] != self.verifier or datetime.fromisoformat(data["expires_at"]) <= datetime.now(timezone.utc):
            raise ServiceError("session_expired", "Connect to the private server again", 401)
        if mutation and request.method not in {"GET", "HEAD", "OPTIONS"}:
            self.check_origin(request)
            if not hmac.compare_digest(request.headers.get("x-scanner-csrf", ""), data["csrf_token"]):
                raise ServiceError("invalid_csrf", "Mutation requires the current session CSRF token", 403)
        return data

    def create(self, request, response):
        self.check_origin(request)
        value = secrets.token_urlsafe(48)
        expires = datetime.now(timezone.utc) + timedelta(hours=self.settings.browser_session_hours)
        data = {"expires_at": expires.isoformat(), "csrf_token": secrets.token_urlsafe(32), "verifier": self.verifier}
        with self.database.session() as db:
            # Bound retained sessions without a new schema/role. Oldest sessions are revoked.
            rows = list(db.scalars(select(Policy).where(Policy.owner_id == self.settings.owner_id,
                         Policy.id.like("session:%"))))
            rows.sort(key=lambda r: r.values.get("expires_at", ""))
            for old in rows[:max(0, len(rows)-15)]:
                db.delete(old)
            db.add(Policy(id=self.identity(value), owner_id=self.settings.owner_id, values=data))
        response.set_cookie(self.cookie, value, max_age=self.settings.browser_session_hours*3600,
                            httponly=True, secure=self.settings.browser_secure_cookie, samesite="strict", path="/")
        return {"owner_id": self.settings.owner_id, "expires_at": data["expires_at"], "csrf_token": data["csrf_token"]}

    def revoke(self, request, response):
        self.read(request)
        with self.database.session() as db:
            db.execute(delete(Policy).where(Policy.id == self.identity(request.cookies[self.cookie]),
                                           Policy.owner_id == self.settings.owner_id))
        response.delete_cookie(self.cookie, path="/", secure=self.settings.browser_secure_cookie, httponly=True, samesite="strict")
        return {"status": "disconnected"}
