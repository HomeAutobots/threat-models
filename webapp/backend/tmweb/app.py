"""The FastAPI app: the lock, the one-time sign-in, the session probe, and the SPA."""
import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from tmreg import config

from . import errors
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

# Nothing from the network loads at run time. Styles need 'unsafe-inline' (Mantine's style tag,
# mermaid's SVG); scripts stay 'self' only.
CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self'; "
    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
)


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
        path = request.url.path
        is_api = path == "/api" or path.startswith("/api/")
        if request.headers.get("host") not in hosts:
            response = JSONResponse({"detail": "unknown host"}, status_code=400)
        elif not is_api:
            return await call_next(request)
        else:
            try:
                response = await _api_checked(request, call_next)
            except Exception:
                # The traceback goes to the Terminal; the browser gets no detail.
                log.exception("unhandled error in %s %s", request.method, path)
                response = JSONResponse({"detail": "internal error"}, status_code=500)
        if is_api:
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.middleware("http")
    async def csp(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = CSP
        return response

    @app.exception_handler(Exception)
    async def outer_error(request: Request, exc: Exception):
        # Runs in ServerErrorMiddleware, outside the middleware above, so set their headers here.
        # Starlette re-raises after sending, so the server still logs the traceback.
        response = JSONResponse({"detail": "internal error"}, status_code=500)
        response.headers["Content-Security-Policy"] = CSP
        path = request.url.path
        if path == "/api" or path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
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
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            if not index.is_file():
                return PlainTextResponse(NOT_BUILT, status_code=503)
            return FileResponse(index)

    app.add_middleware(HttpAndLifespanOnly)  # added last, so it runs first
    return app
