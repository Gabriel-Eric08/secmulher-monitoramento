import logging
import time
import uuid

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.context import definir_contexto

log = logging.getLogger("app.request")


class RequestContextMiddleware:
    """ASGI puro: define request_id/ip/user-agent (contextvar), devolve `X-Request-ID` e loga a requisição."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        request_id = headers.get("x-request-id") or uuid.uuid4().hex
        client = scope.get("client")
        definir_contexto(
            {
                "request_id": request_id,
                "ip": client[0] if client else None,
                "user_agent": (headers.get("user-agent") or "")[:300] or None,
            }
        )
        inicio = time.perf_counter()
        status = 500

        async def send_wrapper(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            log.info(
                "%s %s -> %s (%.1f ms)",
                scope["method"],
                scope["path"],
                status,
                (time.perf_counter() - inicio) * 1000,
                extra={"request_id": request_id},
            )
