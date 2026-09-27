"""Validazione e applicazione delle operazioni inviate dai telefoni (spec §4.2)."""

import logging
import re
import sqlite3
from datetime import date

from freezer.catalog import CATEGORY_CODES, UNIT_CODES
from freezer.db import get_lot, write_transaction

log = logging.getLogger(__name__)

APPLIED = "applied"
DUPLICATE = "duplicate"
IGNORED = "ignored"
INVALID = "invalid"

MAX_ID_LENGTH = 100
MAX_DESCRIPTION = 100
MAX_QUANTITY = 99999
_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


class InvalidOp(ValueError):
    """Operazione malformata: registrata come `invalid` e scartata."""


def _identifier(value, name: str) -> str:
    if not isinstance(value, str) or not value or len(value) > MAX_ID_LENGTH:
        raise InvalidOp(f"{name} non valido: {value!r}")
    return value


def _description(value) -> str:
    if not isinstance(value, str):
        raise InvalidOp("descrizione mancante")
    text = value.strip()
    if not 1 <= len(text) <= MAX_DESCRIPTION:
        raise InvalidOp("descrizione vuota o più lunga di 100 caratteri")
    return text


def _integer(value, name: str, minimum: int, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise InvalidOp(f"{name} deve essere un intero: {value!r}")
    if value < minimum or (maximum is not None and value > maximum):
        raise InvalidOp(f"{name} fuori intervallo: {value}")
    return value


def _code(value, allowed: frozenset[str], name: str) -> str:
    if not isinstance(value, str) or value not in allowed:
        raise InvalidOp(f"{name} sconosciuto: {value!r}")
    return value


def _expiry(value) -> str:
    if not isinstance(value, str) or not _DATE_RE.fullmatch(value):
        raise InvalidOp(f"scadenza non valida: {value!r}")
    try:
        date.fromisoformat(value)
    except ValueError:
        raise InvalidOp(f"scadenza non valida: {value!r}") from None
    return value


_FIELD_VALIDATORS = {
    "description": _description,
    "category": lambda value: _code(value, CATEGORY_CODES, "tipo"),
    "quantity": lambda value: _integer(value, "quantità", 1, MAX_QUANTITY),
    "unit": lambda value: _code(value, UNIT_CODES, "unità"),
    "expiry": _expiry,
}


def _is_active(lot: sqlite3.Row | None) -> bool:
    return lot is not None and lot["status"] == "active"


def _add(conn: sqlite3.Connection, op: dict, now: str) -> str:
    lot = op.get("lot")
    if not isinstance(lot, dict):
        raise InvalidOp("lotto mancante")
    lot_id = _identifier(lot.get("id"), "id del lotto")
    values = {name: validate(lot.get(name)) for name, validate in _FIELD_VALIDATORS.items()}
    if get_lot(conn, lot_id) is not None:
        return IGNORED
    conn.execute(
        "INSERT INTO lots (id, description, category, quantity, unit, expiry, status, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?)",
        (
            lot_id,
            values["description"],
            values["category"],
            values["quantity"],
            values["unit"],
            values["expiry"],
            now,
            now,
        ),
    )
    return APPLIED


def _take(conn: sqlite3.Connection, op: dict, now: str) -> str:
    lot_id = _identifier(op.get("lot_id"), "lot_id")
    amount = _integer(op.get("amount"), "quantità da prendere", 1)
    lot = get_lot(conn, lot_id)
    if not _is_active(lot):
        return IGNORED
    quantity = max(0, lot["quantity"] - amount)
    status = "active" if quantity > 0 else "consumed"
    conn.execute(
        "UPDATE lots SET quantity = ?, status = ?, updated_at = ? WHERE id = ?",
        (quantity, status, now, lot_id),
    )
    return APPLIED


def _edit(conn: sqlite3.Connection, op: dict, now: str) -> str:
    lot_id = _identifier(op.get("lot_id"), "lot_id")
    fields = op.get("fields")
    if not isinstance(fields, dict) or not fields:
        raise InvalidOp("nessun campo da modificare")
    unknown = set(fields) - set(_FIELD_VALIDATORS)
    if unknown:
        raise InvalidOp(f"campi non modificabili: {sorted(unknown)}")
    values = {name: _FIELD_VALIDATORS[name](value) for name, value in fields.items()}
    if not _is_active(get_lot(conn, lot_id)):
        return IGNORED
    # I nomi delle colonne vengono da _FIELD_VALIDATORS, mai dall'input.
    assignments = ", ".join(f"{name} = ?" for name in values)
    conn.execute(
        f"UPDATE lots SET {assignments}, updated_at = ? WHERE id = ?",
        (*values.values(), now, lot_id),
    )
    return APPLIED


def _delete(conn: sqlite3.Connection, op: dict, now: str) -> str:
    lot_id = _identifier(op.get("lot_id"), "lot_id")
    if not _is_active(get_lot(conn, lot_id)):
        return IGNORED
    conn.execute("UPDATE lots SET status = 'deleted', updated_at = ? WHERE id = ?", (now, lot_id))
    return APPLIED


_HANDLERS = {"add": _add, "take": _take, "edit": _edit, "delete": _delete}


def _apply_op(conn: sqlite3.Connection, op, now: str) -> dict:
    op_id = op.get("op_id") if isinstance(op, dict) else None
    if not isinstance(op_id, str) or not op_id or len(op_id) > MAX_ID_LENGTH:
        log.warning("Operazione senza op_id valido: %r", op)
        return {"op_id": None, "status": INVALID}
    if conn.execute("SELECT 1 FROM applied_ops WHERE op_id = ?", (op_id,)).fetchone():
        return {"op_id": op_id, "status": DUPLICATE}
    op_type = op.get("type")
    handler = _HANDLERS.get(op_type) if isinstance(op_type, str) else None
    try:
        if handler is None:
            raise InvalidOp(f"tipo di operazione sconosciuto: {op_type!r}")
        status = handler(conn, op, now)
    except InvalidOp as exc:
        log.warning("Operazione %s scartata: %s", op_id, exc)
        status = INVALID
    conn.execute("INSERT INTO applied_ops (op_id, applied_at) VALUES (?, ?)", (op_id, now))
    return {"op_id": op_id, "status": status}


def apply_ops(conn: sqlite3.Connection, ops: list, now: str) -> list[dict]:
    """Applica le operazioni in ordine, in un'unica transazione."""
    with write_transaction(conn):
        return [_apply_op(conn, op, now) for op in ops]
