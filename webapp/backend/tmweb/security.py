"""Session store and the allowed Host and Origin values for the API lock."""
import secrets
import threading

COOKIE = "tmweb_session"
CSRF_HEADER = "X-CSRF-Token"
DEV_ORIGIN = "http://localhost:5173"


def _same(a: str, b: str) -> bool:
    return secrets.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class SessionStore:
    """Holds the one-time sign-in token and the sessions it creates, in memory only."""

    def __init__(self, signin_token: str):
        if not signin_token:
            raise ValueError("signin_token must not be empty")
        self._token: str | None = signin_token
        self._sessions: dict[str, str] = {}
        self._lock = threading.Lock()

    def consume(self, token: str) -> str | None:
        """Return a new session ID if `token` is the unused sign-in token, else None."""
        with self._lock:
            if self._token is None or not _same(token, self._token):
                return None
            self._token = None
            session_id = secrets.token_urlsafe(32)
            self._sessions[session_id] = secrets.token_urlsafe(32)
            return session_id

    def csrf(self, session_id: str) -> str | None:
        with self._lock:
            for known, csrf in self._sessions.items():
                if _same(session_id, known):
                    return csrf
            return None


class HttpOnly:
    """ASGI middleware: refuse websocket scopes so nothing bypasses the HTTP lock."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": 1008})
            return
        await self.app(scope, receive, send)


def allowed_hosts(port: int) -> set[str]:
    return {f"127.0.0.1:{port}", f"localhost:{port}"}


def allowed_origins(port: int, dev: bool) -> set[str]:
    origins = {f"http://{host}" for host in allowed_hosts(port)}
    if dev:
        origins.add(DEV_ORIGIN)
    return origins
