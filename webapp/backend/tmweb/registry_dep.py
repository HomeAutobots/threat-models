"""One Registry per request. Nothing here creates a database file."""
from pathlib import Path
from typing import AsyncIterator

from fastapi import HTTPException, Request

from tmreg.core import Registry

_FILES = {"main": "registry.db", "trial": "trial.db"}


def db_path(root: Path, reg: str) -> Path:
    name = _FILES.get(reg)
    if name is None:
        raise HTTPException(404, "no such register")
    return Path(root) / "registry" / name


# Async, like the routes that use it: the sqlite connection must be opened, used, and closed on
# one thread, and async code on the event loop stays on one thread.
async def get_registry(reg: str, request: Request) -> AsyncIterator[Registry]:
    root = request.app.state.root
    if not db_path(root, reg).is_file():  # before Registry(), which would create it
        raise HTTPException(404, f"no {reg} register yet")
    registry = Registry(root, trial=(reg == "trial"))
    try:
        yield registry
    finally:
        registry.close()
