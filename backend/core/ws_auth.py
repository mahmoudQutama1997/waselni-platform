from urllib.parse import parse_qs

from channels.db import database_sync_to_async
from rest_framework_simplejwt.authentication import JWTAuthentication

SUBPROTOCOL_PREFIX = "waselni.jwt."
BEARER_PREFIX = "bearer."


def _token_from_scope(scope):
    """Prefer the JWT sent as a WebSocket subprotocol.

    Browsers cannot set Authorization headers on WebSocket handshakes. The
    subprotocol is still a handshake header but keeps the token out of request
    URLs, browser history and most access logs. The query parameter remains as
    a compatibility fallback for native clients.
    """
    for protocol in scope.get("subprotocols") or []:
        if protocol.startswith(SUBPROTOCOL_PREFIX):
            return protocol[len(SUBPROTOCOL_PREFIX):]
        if protocol.startswith(BEARER_PREFIX):
            return protocol[len(BEARER_PREFIX):]
    query = parse_qs(scope.get("query_string", b"").decode())
    return query.get("token", [None])[0]


@database_sync_to_async
def get_user(token):
    try:
        validated = JWTAuthentication().get_validated_token(token)
        return JWTAuthentication().get_user(validated)
    except Exception:
        return None


class JwtQueryAuthMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        token = _token_from_scope(scope)
        scope["user"] = await get_user(token) if token else None
        return await self.app(scope, receive, send)
