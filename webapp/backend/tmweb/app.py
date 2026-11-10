"""The FastAPI app: the lock, the one-time sign-in, the session probe, and the SPA."""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from tmreg import config

from . import diagrams, errors
from .api_read import router as read_router
from .api_write import router as write_router
from .security import (
    COOKIE,
    CSRF_HEADER,
    HttpAndLifespanOnly,
    SessionStore,
    same,
    allowed_hosts,
    allowed_origins,
)

log = logging.getLogger("tmweb")

SIGNIN_REFUSED = (
    "This sign-in link has been used or is not valid. "
    "Close the app's Terminal window and start it again for a new link."
)

NOT_BUILT = (
    "The app's pages aren't built yet. Start it with webapp/start.command or make web."
)

# Nothing from the network loads at run time. Styles need 'unsafe-inline' (Mantine's style tags);
# scripts stay 'self' only, except that a /diagrams/ page also allows its export's inline scripts
# by their hashes (diagrams_csp).
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)

DIAGRAMS_ROUTE = "/diagrams/{reg}/{slug}/{sha256}/{path:path}"


def diagrams_csp(hashes: list[str]) -> str:
    """The app's CSP, with script-src also allowing an export's inline scripts by their hashes."""
    allowed = "".join(f" {h}" for h in hashes if diagrams.HASH_RE.fullmatch(h))
    return CSP.replace("script-src 'self';", f"script-src 'self'{allowed};", 1)


def _under(path: str, prefix: str) -> bool:
    return path == prefix or path.startswith(prefix + "/")


def _locked_headers(response, path: str) -> None:
    """The headers every locked response carries, whatever its status."""
    if _under(path, "/api") or _under(path, "/diagrams"):
        response.headers["Cache-Control"] = "no-store"
    if _under(path, "/diagrams"):
        response.headers["X-Content-Type-Options"] = "nosniff"
        # No other origin may load these files, not even a page on another localhost port that
        # the browser sends the session cookie to.
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        # The viewer opens AI-written http(s) property values with window.open and no noopener:
        # a page opened that way gets no handle on this one, and no URL of it.
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
        response.headers["Referrer-Policy"] = "no-referrer"


def create_app(
    root: Path,
    *,
    port: int,
    signin_token: str,
    static_dir: Path | None = None,
    dev: bool = False,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    app.state.root = root
    app.state.port = port
    app.state.sessions = SessionStore(signin_token)
    hosts = allowed_hosts(port)
    origins = allowed_origins(port, dev)

    @app.middleware("http")
    async def lock(request: Request, call_next):
        path = request.scope["path"]  # the path the router matches
        is_api = _under(path, "/api")
        is_diagrams = _under(path, "/diagrams")
        if request.headers.get("host") not in hosts:
            response = JSONResponse({"detail": "unknown host"}, status_code=400)
        elif not (is_api or is_diagrams):
            return await call_next(request)
        else:
            checked = _api_checked if is_api else _diagrams_checked
            try:
                response = await checked(request, call_next)
            except Exception:
                # The traceback goes to the Terminal; the browser gets no detail.
                log.exception("unhandled error in %s %s", request.method, path)
                response = JSONResponse({"detail": "internal error"}, status_code=500)
        _locked_headers(response, path)
        return response

    @app.middleware("http")
    async def csp(request: Request, call_next):
        response = await call_next(request)
        # Every response gets the app's CSP, except that a /diagrams/ response keeps its own: the
        # app's CSP plus that export's script hashes (diagrams_csp).
        own = "content-security-policy" in response.headers
        if not (own and request.scope["path"].startswith("/diagrams/")):
            response.headers["Content-Security-Policy"] = CSP
        return response

    @app.exception_handler(Exception)
    async def outer_error(request: Request, exc: Exception):
        # Runs in ServerErrorMiddleware, outside the middleware above, so set their headers here.
        # Starlette re-raises after sending, so the server still logs the traceback.
        response = JSONResponse({"detail": "internal error"}, status_code=500)
        response.headers["Content-Security-Policy"] = CSP
        _locked_headers(response, request.scope["path"])
        return response

    async def _api_checked(request: Request, call_next):
        sessions: SessionStore = request.app.state.sessions
        session_id = request.cookies.get(COOKIE)
        csrf = sessions.csrf(session_id) if session_id else None
        sent = request.headers.get(CSRF_HEADER)
        if csrf is None or not sent or not same(sent, csrf):
            return JSONResponse({"detail": "signed out"}, status_code=401)
        if request.method not in ("GET", "HEAD") and request.headers.get("origin") not in origins:
            return JSONResponse({"detail": "forbidden"}, status_code=403)
        return await call_next(request)

    async def _diagrams_checked(request: Request, call_next):
        # The session cookie alone: a link the owner opens can't send the CSRF header, and these
        # routes only read.
        sessions: SessionStore = request.app.state.sessions
        session_id = request.cookies.get(COOKIE)
        if not session_id or sessions.csrf(session_id) is None:
            return JSONResponse({"detail": "signed out"}, status_code=401)
        if request.method not in ("GET", "HEAD"):
            return JSONResponse({"detail": "method not allowed"}, status_code=405,
                                headers={"Allow": "GET, HEAD"})
        return await call_next(request)

    @app.get("/signin")
    def signin(request: Request, token: str = ""):
        session_id = request.app.state.sessions.consume(token)
        if session_id is None:
            return PlainTextResponse(SIGNIN_REFUSED, status_code=403)
        response = RedirectResponse(
            f"/#k={request.app.state.sessions.csrf(session_id)}", status_code=303
        )
        response.set_cookie(
            COOKIE, session_id, httponly=True, samesite="strict", path="/"
        )
        return response

    @app.get("/api/session")
    def session(request: Request):
        project = config.load_project(request.app.state.root)
        trial = (request.app.state.root / "registry" / "trial.db").is_file()
        return {"reviewer": project.reviewer_name, "trial": trial}

    app.include_router(read_router)
    app.include_router(write_router)
    errors.install(app)

    @app.api_route(DIAGRAMS_ROUTE, methods=["GET", "HEAD"], include_in_schema=False)
    def diagram_file(reg: str, slug: str, sha256: str, path: str, request: Request):
        found = diagrams.find(request.app.state.root, reg, slug, sha256, path)
        if found is None:
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        file, hashes = found
        return FileResponse(file, media_type=diagrams.media_type(file),
                            headers={"Content-Security-Policy": diagrams_csp(hashes)})

    if static_dir is not None:
        index = static_dir / "index.html"
        if (static_dir / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/favicon.svg", include_in_schema=False)
        def favicon():
            # Only this one file is served from the root; everything else falls to the SPA page.
            icon = static_dir / "favicon.svg"
            if not icon.is_file():
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(icon, media_type="image/svg+xml")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if _under("/" + full_path, "/api") or _under("/" + full_path, "/diagrams"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            if not index.is_file():
                return PlainTextResponse(NOT_BUILT, status_code=503)
            return FileResponse(index)

    app.add_middleware(HttpAndLifespanOnly)  # added last, so it runs first
    return app
