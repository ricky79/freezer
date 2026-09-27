import pytest

from builders import LATER, NOW, add_op, delete_op, edit_op, take_op
from freezer.db import active_lots, get_lot
from freezer.ops import APPLIED, DUPLICATE, IGNORED, INVALID, apply_ops


def statuses(results):
    return [result["status"] for result in results]


def lot(conn, lot_id="lot-1"):
    return dict(get_lot(conn, lot_id))


def test_add_creates_active_lot_with_trimmed_description(conn):
    results = apply_ops(conn, [add_op(description="  Piselli  ")], NOW)
    assert results == [{"op_id": "op-add", "status": APPLIED}]
    row = lot(conn)
    assert row["description"] == "Piselli"
    assert row["status"] == "active"
    assert row["quantity"] == 5
    assert row["created_at"] == NOW
    assert row["updated_at"] == NOW


def test_description_of_100_characters_is_valid(conn):
    assert statuses(apply_ops(conn, [add_op(description="x" * 100)], NOW)) == [APPLIED]


def test_add_with_existing_lot_id_is_ignored(conn):
    apply_ops(conn, [add_op("op1")], NOW)
    results = apply_ops(conn, [add_op("op2", description="Altro nome")], LATER)
    assert statuses(results) == [IGNORED]
    assert lot(conn)["description"] == "Piselli"


def test_resending_the_same_queue_has_no_effect(conn):
    queue = [add_op(), take_op("op-take", 2)]
    assert statuses(apply_ops(conn, queue, NOW)) == [APPLIED, APPLIED]
    assert statuses(apply_ops(conn, queue, LATER)) == [DUPLICATE, DUPLICATE]
    assert lot(conn)["quantity"] == 3


def test_same_op_twice_in_one_batch_is_duplicate(conn):
    apply_ops(conn, [add_op()], NOW)
    results = apply_ops(conn, [take_op("t", 1), take_op("t", 1)], NOW)
    assert statuses(results) == [APPLIED, DUPLICATE]
    assert lot(conn)["quantity"] == 4


def test_add_then_take_in_same_batch(conn):
    results = apply_ops(conn, [add_op(), take_op("op-take", 2)], NOW)
    assert statuses(results) == [APPLIED, APPLIED]
    assert lot(conn)["quantity"] == 3


def test_takes_from_two_phones_add_up(conn):
    apply_ops(conn, [add_op()], NOW)
    apply_ops(conn, [take_op("phone-a", 2)], NOW)
    apply_ops(conn, [take_op("phone-b", 1)], LATER)
    assert lot(conn)["quantity"] == 2
    assert lot(conn)["updated_at"] == LATER


def test_take_more_than_available_consumes_the_lot(conn):
    apply_ops(conn, [add_op()], NOW)
    assert statuses(apply_ops(conn, [take_op("t", 10)], NOW)) == [APPLIED]
    row = lot(conn)
    assert row["quantity"] == 0
    assert row["status"] == "consumed"
    assert active_lots(conn) == []


def test_take_exactly_all_consumes_the_lot(conn):
    apply_ops(conn, [add_op(), take_op("t", 5)], NOW)
    assert lot(conn)["status"] == "consumed"


def test_take_on_missing_consumed_or_deleted_lot_is_ignored(conn):
    apply_ops(conn, [add_op("a1", "consumed"), take_op("t1", 5, "consumed")], NOW)
    apply_ops(conn, [add_op("a2", "deleted"), delete_op("d2", "deleted")], NOW)
    results = apply_ops(
        conn,
        [take_op("t2", 1, "missing"), take_op("t3", 1, "consumed"), take_op("t4", 1, "deleted")],
        LATER,
    )
    assert statuses(results) == [IGNORED, IGNORED, IGNORED]


def test_edit_updates_only_given_fields(conn):
    apply_ops(conn, [add_op()], NOW)
    results = apply_ops(conn, [edit_op("e", {"quantity": 8, "expiry": "2027-02-01"})], LATER)
    assert statuses(results) == [APPLIED]
    row = lot(conn)
    assert (row["description"], row["quantity"], row["expiry"]) == ("Piselli", 8, "2027-02-01")
    assert row["updated_at"] == LATER
    assert row["created_at"] == NOW


def test_edit_last_arrived_wins(conn):
    apply_ops(conn, [add_op()], NOW)
    apply_ops(conn, [edit_op("e1", {"description": "Piselli fini"})], NOW)
    apply_ops(conn, [edit_op("e2", {"description": "Piselli grossi"})], LATER)
    assert lot(conn)["description"] == "Piselli grossi"


def test_edit_on_non_active_lot_is_ignored(conn):
    apply_ops(conn, [add_op(), delete_op("d")], NOW)
    assert statuses(apply_ops(conn, [edit_op("e", {"quantity": 2})], NOW)) == [IGNORED]


def test_delete_marks_deleted_and_second_delete_is_ignored(conn):
    apply_ops(conn, [add_op()], NOW)
    assert statuses(apply_ops(conn, [delete_op("d1")], NOW)) == [APPLIED]
    assert lot(conn)["status"] == "deleted"
    assert statuses(apply_ops(conn, [delete_op("d2")], NOW)) == [IGNORED]


@pytest.mark.parametrize(
    "op",
    [
        {"op_id": "x", "type": "explode"},
        {"op_id": "x", "type": ["add"]},
        {"op_id": "x", "type": "add"},
        {"op_id": "x", "type": "add", "lot": "non un dizionario"},
        add_op("x", lot_id=""),
        add_op("x", quantity=0),
        add_op("x", quantity=100000),
        add_op("x", quantity=2.5),
        add_op("x", quantity=True),
        add_op("x", quantity="3"),
        add_op("x", category="gelati"),
        add_op("x", category=["carne"]),
        add_op("x", unit="litri"),
        add_op("x", expiry="2027-02-30"),
        add_op("x", expiry="31/01/2027"),
        add_op("x", expiry="2026-W39-1"),
        add_op("x", description="   "),
        add_op("x", description="x" * 101),
        add_op("x", description=None),
        take_op("x", 0),
        take_op("x", "2"),
        {"op_id": "x", "type": "take", "amount": 1},
        edit_op("x", {}),
        edit_op("x", {"status": "active"}),
        edit_op("x", {"quantity": 0}),
        edit_op("x", "quantity=3"),
        delete_op("x", lot_id=5),
    ],
)
def test_malformed_ops_are_invalid_and_recorded(conn, op):
    apply_ops(conn, [add_op("seed")], NOW)  # lotto lot-1 esistente per take/edit/delete
    assert apply_ops(conn, [op], NOW) == [{"op_id": "x", "status": INVALID}]
    assert apply_ops(conn, [op], LATER) == [{"op_id": "x", "status": DUPLICATE}]
    assert lot(conn)["quantity"] == 5


@pytest.mark.parametrize("op", [{"type": "add"}, {"op_id": "", "type": "add"}, {"op_id": 7}, "ciao", None])
def test_op_without_valid_op_id_is_invalid(conn, op):
    assert apply_ops(conn, [op], NOW) == [{"op_id": None, "status": INVALID}]


def test_invalid_op_does_not_block_the_others(conn):
    results = apply_ops(conn, [{"op_id": "bad", "type": "explode"}, add_op()], NOW)
    assert statuses(results) == [INVALID, APPLIED]
