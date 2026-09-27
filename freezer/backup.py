"""Backup notturno del database con rotazione. Avviato da freezer-backup.timer."""

import logging
import sqlite3
import sys
from collections.abc import Mapping
from contextlib import closing
from datetime import datetime
from pathlib import Path

from freezer.config import load_config

log = logging.getLogger("freezer.backup")


def backup_db(db_path: str, backup_dir: str, keep: int, now: datetime) -> Path:
    source_path = Path(db_path)
    if not source_path.exists():
        raise FileNotFoundError(f"database non trovato: {db_path}")
    target_dir = Path(backup_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"freezer-{now:%Y%m%d-%H%M%S}.db"
    with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(target)) as copy:
        source.backup(copy)
    for old in sorted(target_dir.glob("freezer-*.db"))[:-keep]:
        old.unlink()
    return target


def main(env: Mapping[str, str] | None = None, now: datetime | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(env)
    try:
        target = backup_db(cfg.db_path, cfg.backup_dir, cfg.backup_keep, now or datetime.now())
    except (OSError, sqlite3.Error) as exc:
        log.error("Backup fallito: %s", exc)
        return 1
    log.info("Backup creato: %s", target)
    return 0


if __name__ == "__main__":
    sys.exit(main())
