"""Configurazione da variabili d'ambiente (in produzione: /etc/freezer/freezer.env)."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    db_path: str
    port: int
    warn_days: int
    tz: str
    backup_dir: str
    backup_keep: int
    telegram_token: str
    telegram_chat_id: str


def _text(env: Mapping[str, str], name: str, default: str) -> str:
    return env.get(name, "").strip() or default


def _int(env: Mapping[str, str], name: str, default: int, minimum: int) -> int:
    raw = env.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} deve essere un numero intero, trovato {raw!r}") from None
    if value < minimum:
        raise ValueError(f"{name} deve essere almeno {minimum}, trovato {value}")
    return value


def load_config(env: Mapping[str, str] | None = None) -> Config:
    env = os.environ if env is None else env
    return Config(
        db_path=_text(env, "FREEZER_DB_PATH", "freezer.db"),
        port=_int(env, "FREEZER_PORT", 8765, 1),
        warn_days=_int(env, "FREEZER_WARN_DAYS", 7, 0),
        tz=_text(env, "FREEZER_TZ", "Europe/Rome"),
        backup_dir=_text(env, "FREEZER_BACKUP_DIR", "backups"),
        backup_keep=_int(env, "FREEZER_BACKUP_KEEP", 14, 1),
        telegram_token=_text(env, "TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=_text(env, "TELEGRAM_CHAT_ID", ""),
    )
