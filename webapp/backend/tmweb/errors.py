"""Maps core errors to HTTP responses."""
import sqlite3

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from tmreg import config
from tmreg.core import RegistryError, StaleRecord


def install(app: FastAPI) -> None:
    @app.exception_handler(RegistryError)
    async def registry_error(request: Request, exc: RegistryError):
        if isinstance(exc, StaleRecord):
            raise exc  # the write routes map this to 409
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(config.ConfigError)
    async def config_error(request: Request, exc: config.ConfigError):
        return JSONResponse({"detail": str(exc)}, status_code=422)

    @app.exception_handler(sqlite3.OperationalError)
    async def busy(request: Request, exc: sqlite3.OperationalError):
        return JSONResponse({"detail": "database is busy or unavailable"}, status_code=503)
