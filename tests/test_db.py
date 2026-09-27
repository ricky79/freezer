import pytest

from builders import LATER, NOW, add_op, delete_op, take_op
from freezer.db import active_lots, suggestions, write_transaction
from freezer.ops import apply_ops


def test_active_lots_sorted_by_expiry_then_description(conn):
    apply_ops(
        conn,
        [
            add_op("a", "l1", description="zucchine", expiry="2027-01-10"),
            add_op("b", "l2", description="Asparagi", expiry="2027-01-10"),
            add_op("c", "l3", description="Burro", expiry="2026-12-01"),
        ],
        NOW,
    )
    assert [lot["description"] for lot in active_lots(conn)] == ["Burro", "Asparagi", "zucchine"]


def test_active_lots_shape(conn):
    apply_ops(conn, [add_op()], NOW)
    assert active_lots(conn) == [
        {
            "id": "lot-1",
            "description": "Piselli",
            "category": "verdure",
            "quantity": 5,
            "unit": "buste",
            "expiry": "2027-01-31",
        }
    ]


def test_suggestions_dedupe_case_insensitive_most_recent_wins(conn):
    apply_ops(conn, [add_op("a", "l1", description="Ragù", category="sughi", unit="barattoli_grandi")], NOW)
    apply_ops(conn, [take_op("b", 99, "l1")], NOW)  # consumato: resta nei suggerimenti
    apply_ops(conn, [add_op("c", "l2", description="ragù", category="sughi", unit="barattoli_piccoli")], LATER)
    assert suggestions(conn) == [{"description": "ragù", "category": "sughi", "unit": "barattoli_piccoli"}]


def test_suggestions_exclude_deleted_lots(conn):
    apply_ops(conn, [add_op("a", "l1", description="Errore di battitura"), delete_op("b", "l1")], NOW)
    assert suggestions(conn) == []


def test_suggestions_limit(conn):
    apply_ops(conn, [add_op(f"op{i}", f"l{i}", description=f"Cosa {i}") for i in range(5)], NOW)
    assert len(suggestions(conn, limit=3)) == 3


def test_write_transaction_rolls_back_on_error(conn):
    with pytest.raises(RuntimeError):
        with write_transaction(conn):
            conn.execute("INSERT INTO applied_ops (op_id, applied_at) VALUES ('x', 'ora')")
            raise RuntimeError("boom")
    assert conn.execute("SELECT COUNT(*) FROM applied_ops").fetchone()[0] == 0
