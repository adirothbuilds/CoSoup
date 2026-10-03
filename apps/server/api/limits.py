"""Reject oversized bodies before multipart spooling or JSON deserialization."""
from starlette.responses import JSONResponse


class BodyLimit:
    def __init__(self, app, upload_bytes):
        self.app, self.upload_bytes = app, upload_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] not in {"POST", "PATCH", "PUT"}:
            return await self.app(scope, receive, send)
        maximum = self.upload_bytes+1024*1024 if scope["path"] == "/api/v1/uploads" else 1024*1024
        headers = dict(scope.get("headers", []))
        try:
            length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            length = maximum+1
        if length > maximum:
            return await JSONResponse({"error": {"code": "body_size_limit", "message": "Request body exceeds configured maximum"}}, status_code=413)(scope, receive, send)
        size = 0
        async def guarded():
            nonlocal size
            message = await receive()
            size += len(message.get("body", b""))
            if size > maximum:
                from ..errors import ServiceError
                raise ServiceError("body_size_limit", "Request body exceeds configured maximum", 413)
            return message
        await self.app(scope, guarded, send)
