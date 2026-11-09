"""Storage: slug rules, connection, per-system tables and triggers."""
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
_SLUG_RE = re.compile(r"[a-z][a-z0-9-]{1,39}")
_TABLES = ("risks", "changes", "dfd_approvals", "runs", "sequences")
_TRIGGERS = ("risks_no_delete", "changes_no_update", "changes_no_delete",
             "dfd_approvals_no_update", "dfd_approvals_no_delete")
_HERE = Path(__file__).parent


def validate_slug(slug: str) -> str:
    if not isinstance(slug, str) or not _SLUG_RE.fullmatch(slug):
        raise ValueError(f"invalid system slug {slug!r}: must match ^[a-z][a-z0-9-]{{1,39}}$")
    return slug


def _prefix(slug: str) -> str:
    return validate_slug(slug).replace("-", "_")


def table(slug: str, name: str) -> str:
    if name not in _TABLES:
        raise ValueError(f"unknown per-system table {name!r}")
    return f"{_prefix(slug)}__{name}"


def trigger_names(slug: str) -> list[str]:
    p = _prefix(slug)
    return [f"{p}__{t}" for t in _TRIGGERS]


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=5)
    conn.row_factory = sqlite3.Row
    conn.executescript((_HERE / "schema.sql").read_text())
    conn.execute("INSERT OR IGNORE INTO meta (key, value) VALUES ('schema_version', ?)",
                 (str(SCHEMA_VERSION),))
    conn.commit()
    return conn


def system_exists(conn: sqlite3.Connection, slug: str) -> bool:
    validate_slug(slug)
    return conn.execute("SELECT 1 FROM systems WHERE slug = ?", (slug,)).fetchone() is not None


def list_systems(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT slug, name, created_at FROM systems ORDER BY slug").fetchall()
    return [{"slug": r[0], "name": r[1], "created_at": r[2]} for r in rows]


def create_system(conn: sqlite3.Connection, slug: str, name: str) -> None:
    p = _prefix(slug)
    if system_exists(conn, slug):
        raise ValueError(f"system {slug!r} already exists")
    # executescript commits first, so insert the registration last: a failure
    # partway leaves no systems row and the call can be retried after cleanup.
    conn.executescript((_HERE / "system.sql").read_text().replace("{p}", p))
    conn.execute("INSERT INTO systems (slug, name, created_at) VALUES (?, ?, ?)",
                 (slug, name, now()))
    conn.executemany(f"INSERT INTO {table(slug, 'sequences')} (prefix, next) VALUES (?, 1)",
                     [("T",), ("PT",), ("DFD",)])
    conn.commit()
