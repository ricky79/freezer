"""Costruttori di operazioni per i test."""

NOW = "2026-09-27T18:00:00+02:00"
LATER = "2026-09-27T19:00:00+02:00"


def add_op(op_id="op-add", lot_id="lot-1", **lot_fields):
    lot = {
        "id": lot_id,
        "description": "Piselli",
        "category": "verdure",
        "quantity": 5,
        "unit": "buste",
        "expiry": "2027-01-31",
    }
    lot.update(lot_fields)
    return {"op_id": op_id, "type": "add", "at": NOW, "lot": lot}


def take_op(op_id, amount, lot_id="lot-1"):
    return {"op_id": op_id, "type": "take", "at": NOW, "lot_id": lot_id, "amount": amount}


def edit_op(op_id, fields, lot_id="lot-1"):
    return {"op_id": op_id, "type": "edit", "at": NOW, "lot_id": lot_id, "fields": fields}


def delete_op(op_id, lot_id="lot-1"):
    return {"op_id": op_id, "type": "delete", "at": NOW, "lot_id": lot_id}
