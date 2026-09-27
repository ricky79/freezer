import sqlite3
from contextlib import closing
from datetime import datetime

import pytest

from builders import NOW, add_op
from freezer.backup import backup_db, main
from freezer.db import connect, init_db
from freezer.ops import apply_ops


@pytest.fixture
def db_path(tmp_path):
    path = str(tmp_path / "freezer.db")
    with closing(connect(path)) as conn:
        init_db(conn)
        apply_ops(conn, [add_op()], NOW)
    return path


def test_backup_is_a_valid_copy(db_path, tmp_path):
    target = backup_db(db_path, str(tmp_path / "backups"), 14, datetime(2026, 9, 27, 3, 0))
    assert target.name == "freezer-20260927-030000.db"
    with closing(sqlite3.connect(target)) as copy:
        assert copy.execute("SELECT COUNT(*) FROM lots").fetchone()[0] == 1


def test_rotation_keeps_the_newest(db_path, tmp_path):
    backups = tmp_path / "backups"
    for day in range(1, 6):
        backup_db(db_path, str(backups), 3, datetime(2026, 9, day, 3, 0))
    assert sorted(p.name for p in backups.iterdir()) == [
        "freezer-20260903-030000.db",
        "freezer-20260904-030000.db",
        "freezer-20260905-030000.db",
    ]


def test_main_ok(db_path, tmp_path):
    env = {"FREEZER_DB_PATH": db_path, "FREEZER_BACKUP_DIR": str(tmp_path / "b")}
    assert main(env, now=datetime(2026, 9, 27, 3, 0)) == 0
    assert (tmp_path / "b" / "freezer-20260927-030000.db").exists()


def test_main_missing_database_fails_without_creating_it(tmp_path):
    missing = tmp_path / "manca.db"
    env = {"FREEZER_DB_PATH": str(missing), "FREEZER_BACKUP_DIR": str(tmp_path / "b")}
    assert main(env) == 1
    assert not missing.exists()
