"""The only row writer: change log, hash chain, replay."""
import hashlib
import json

from . import db
from .model import JSON_COLUMNS, KEY_COLUMNS

GENESIS = "0" * 64
_RECORD_KEYS = ("seq", "at", "op", "tbl", "row_key", "actor", "diff", "note")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(prev_hash: str, record: dict) -> str:
    return hashlib.sha256((prev_hash + canonical(record)).encode("utf-8")).hexdigest()


def _check_tbl(tbl: str) -> None:
    if tbl not in KEY_COLUMNS:
        raise ValueError(f"cannot write table {tbl!r}")


def _columns(conn, slug, tbl) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({db.table(slug, tbl)})")]


def _decode(tbl: str, row: dict) -> dict:
    for col in JSON_COLUMNS[tbl]:
        if row.get(col) is not None:
            row[col] = json.loads(row[col])
    return row


def _encode(value):
    return None if value is None else canonical(value)


def write_row(conn, slug, tbl, key, fields: dict, *, op: str, actor: str, note: str = "") -> dict:
    _check_tbl(tbl)
    t = db.table(slug, tbl)
    keycol = KEY_COLUMNS[tbl]
    cols = _columns(conn, slug, tbl)
    fields = dict(fields)
    if fields.pop(keycol, key) != key:
        raise ValueError(f"{keycol} in fields does not match key {key!r}")
    for f in fields:
        if f not in cols:
            raise ValueError(f"unknown column {f!r} for {tbl}")

    row = conn.execute(f"SELECT * FROM {t} WHERE {keycol} = ?", (key,)).fetchone()
    old = _decode(tbl, dict(row)) if row is not None else {}
    diff = {f: [old.get(f), v] for f, v in fields.items() if old.get(f) != v}
    if not diff:
        raise ValueError("no changes")

    if row is None:
        names = [keycol] + list(diff)
        conn.execute(
            f"INSERT INTO {t} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
            [key] + [_enc(tbl, f, new) for f, (_, new) in diff.items()])
    else:
        sets = ", ".join(f"{f} = ?" for f in diff)
        conn.execute(f"UPDATE {t} SET {sets} WHERE {keycol} = ?",
                     [_enc(tbl, f, new) for f, (_, new) in diff.items()] + [key])

    ct = db.table(slug, "changes")
    last = conn.execute(f"SELECT seq, hash FROM {ct} ORDER BY seq DESC LIMIT 1").fetchone()
    prev_hash, seq = (last["hash"], last["seq"] + 1) if last else (GENESIS, 1)
    record = {"seq": seq, "at": db.now(), "op": op, "tbl": tbl, "row_key": key,
              "actor": actor, "diff": diff, "note": note}
    h = content_hash(prev_hash, record)
    conn.execute(
        f"INSERT INTO {ct} (seq, at, op, tbl, row_key, actor, diff, note, prev_hash, hash) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (seq, record["at"], op, tbl, key, actor, canonical(diff), note, prev_hash, h))
    return {**record, "prev_hash": prev_hash, "hash": h}


def _enc(tbl: str, field: str, value):
    return _encode(value) if field in JSON_COLUMNS[tbl] else value


def read_rows(conn, slug, tbl) -> dict[str, dict]:
    _check_tbl(tbl)
    keycol = KEY_COLUMNS[tbl]
    rows = conn.execute(f"SELECT * FROM {db.table(slug, tbl)} ORDER BY rowid")
    return {r[keycol]: _decode(tbl, dict(r)) for r in rows}


def changes(conn, slug, key: str | None = None) -> list[dict]:
    sql = f"SELECT * FROM {db.table(slug, 'changes')}"
    args: tuple = ()
    if key is not None:
        sql += " WHERE row_key = ?"
        args = (key,)
    out = []
    for r in conn.execute(sql + " ORDER BY seq", args):
        d = dict(r)
        d["diff"] = json.loads(d["diff"])
        out.append(d)
    return out


def _diff_problem(ch: dict) -> str | None:
    """Why a change row's decoded diff cannot be replayed, or None when it can."""
    diff = ch["diff"]
    if ch["tbl"] not in KEY_COLUMNS:
        return f"change #{ch['seq']}: table {ch['tbl']!r} is not one the registry writes"
    if not isinstance(diff, dict) or not all(isinstance(v, list) and len(v) == 2 for v in diff.values()):
        return f"change #{ch['seq']}: diff is not a map of field changes"
    return None


def changes_tolerant(conn, slug) -> list[dict]:
    """Like changes(), but a diff that is not valid JSON comes back as None instead of raising."""
    out = []
    for r in conn.execute(f"SELECT * FROM {db.table(slug, 'changes')} ORDER BY seq"):
        d = dict(r)
        try:
            d["diff"] = json.loads(d["diff"])
            d["diff_valid"] = True
        except (TypeError, ValueError):
            d["diff"], d["diff_valid"] = None, False
        out.append(d)
    return out


def verify_chain(conn, slug) -> list[str]:
    problems = []
    prev = GENESIS
    expected_seq = 1
    for ch in changes_tolerant(conn, slug):
        n = ch["seq"]
        if n != expected_seq:
            problems.append(f"change #{n}: expected sequence number {expected_seq} (missing or reordered rows)")
        expected_seq = n + 1 if isinstance(n, int) else expected_seq + 1
        if ch["prev_hash"] != prev:
            problems.append(f"change #{n}: prev_hash does not match the previous change")
        if not ch["diff_valid"]:
            problems.append(f"change #{n}: diff is not valid JSON")
        else:
            record = {k: ch[k] for k in _RECORD_KEYS}
            if ch["hash"] != content_hash(ch["prev_hash"], record):
                problems.append(f"change #{n}: hash does not match its contents")
            shape = _diff_problem(ch)
            if shape:
                problems.append(shape)
        prev = ch["hash"]
    return problems


def replay(conn, slug) -> dict[tuple[str, str], dict]:
    """Rebuild rows from the log. Changes whose diff cannot be read are skipped (verify_chain reports them)."""
    blank = {tbl: {c: None for c in _columns(conn, slug, tbl)} for tbl in KEY_COLUMNS}
    rows: dict[tuple[str, str], dict] = {}
    for ch in changes_tolerant(conn, slug):
        if not ch["diff_valid"] or _diff_problem(ch):
            continue
        tbl, key = ch["tbl"], ch["row_key"]
        row = rows.setdefault((tbl, key), {**blank[tbl], KEY_COLUMNS[tbl]: key})
        for field, (_, new) in ch["diff"].items():
            row[field] = new
    return rows
