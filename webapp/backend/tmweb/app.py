"""The FastAPI app: the lock, the one-time sign-in, the session probe, and the SPA."""
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from tmreg import config

from .security import (
    COOKIE,
    CSRF_HEADER,
    SessionStore,
    _same,
    allowed_hosts,
    allowed_origins,
)

SIGNIN_REFUSED = (
    "This sign-in link has been used or is not valid. "
    "Close the app's Terminal window and start it again for a new link."
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
        if request.headers.get("host") not in hosts:
            return JSONResponse({"detail": "unknown host"}, status_code=400)
        path = request.url.path
        if path == "/api" or path.startswith("/api/"):
            sessions: SessionStore = request.app.state.sessions
            session_id = request.cookies.get(COOKIE)
            csrf = sessions.csrf(session_id) if session_id else None
            if csrf is None:
                return JSONResponse({"detail": "signed out"}, status_code=401)
            if request.method not in ("GET", "HEAD"):
                sent = request.headers.get(CSRF_HEADER, "")
                if not _same(sent, csrf) or request.headers.get("origin") not in origins:
                    return JSONResponse({"detail": "forbidden"}, status_code=403)
        return await call_next(request)

    @app.get("/signin")
    def signin(request: Request, token: str = ""):
        session_id = request.app.state.sessions.consume(token)
        if session_id is None:
            return PlainTextResponse(SIGNIN_REFUSED, status_code=403)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            COOKIE, session_id, httponly=True, samesite="strict", path="/"
        )
        return response

    @app.get("/api/session")
    def session(request: Request):
        csrf = request.app.state.sessions.csrf(request.cookies[COOKIE])
        project = config.load_project(request.app.state.root)
        trial = (request.app.state.root / "registry" / "trial.db").is_file()
        return {"reviewer": project.reviewer_name, "csrf": csrf, "trial": trial}

    if static_dir is not None:
        index = static_dir / "index.html"
        if (static_dir / "assets").is_dir():
            app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def spa(full_path: str):
            if full_path == "api" or full_path.startswith("api/"):
                return JSONResponse({"detail": "Not Found"}, status_code=404)
            return FileResponse(index)

    return app
