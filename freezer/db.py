"""Accesso a SQLite: schema, connessione, transazioni, letture per l'istantanea."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS lots (
    id          TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category    TEXT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity >= 0),
    unit        TEXT NOT NULL,
    expiry      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('active', 'consumed', 'deleted')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lots_status ON lots (status);
CREATE TABLE IF NOT EXISTS applied_ops (
    op_id      TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    # isolation_level=None: niente transazioni implicite, le apriamo noi con BEGIN IMMEDIATE.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    # IMMEDIATE prende subito il lock di scrittura: due telefoni che sincronizzano
    # insieme vengono serializzati invece di fallire con "database is locked".
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def get_lot(conn: sqlite3.Connection, lot_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()


def active_lots(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, description, category, quantity, unit, expiry FROM lots "
        "WHERE status = 'active' "
        "ORDER BY expiry, description COLLATE NOCASE, id"
    ).fetchall()
    return [dict(row) for row in rows]


def suggestions(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT description, category, unit FROM lots "
        "WHERE status IN ('active', 'consumed') "
        "ORDER BY created_at DESC, rowid DESC"
    )
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        key = row["description"].casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
        if len(result) == limit:
            break
    return result
