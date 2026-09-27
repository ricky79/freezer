import pytest

from freezer.config import load_config


def test_defaults():
    cfg = load_config({})
    assert cfg.db_path == "freezer.db"
    assert cfg.port == 8765
    assert cfg.warn_days == 7
    assert cfg.tz == "Europe/Rome"
    assert cfg.backup_dir == "backups"
    assert cfg.backup_keep == 14
    assert cfg.telegram_token == ""
    assert cfg.telegram_chat_id == ""


def test_overrides_and_trimming():
    cfg = load_config(
        {
            "FREEZER_DB_PATH": "/var/lib/freezer/freezer.db",
            "FREEZER_PORT": " 9000 ",
            "FREEZER_WARN_DAYS": "3",
            "TELEGRAM_BOT_TOKEN": " abc ",
            "TELEGRAM_CHAT_ID": "-100123",
        }
    )
    assert cfg.db_path == "/var/lib/freezer/freezer.db"
    assert cfg.port == 9000
    assert cfg.warn_days == 3
    assert cfg.telegram_token == "abc"
    assert cfg.telegram_chat_id == "-100123"


def test_invalid_integer_names_the_variable():
    with pytest.raises(ValueError, match="FREEZER_PORT"):
        load_config({"FREEZER_PORT": "ottomila"})


def test_backup_keep_must_be_positive():
    with pytest.raises(ValueError, match="FREEZER_BACKUP_KEEP"):
        load_config({"FREEZER_BACKUP_KEEP": "0"})
