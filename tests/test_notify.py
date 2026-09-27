import io
import json
import urllib.error
from datetime import date

import pytest

from builders import NOW, add_op
from freezer.db import connect, init_db
from freezer.notify import TEST_MESSAGE, build_message, main, send_telegram
from freezer.ops import apply_ops

TODAY = date(2026, 9, 27)


def lot(description, quantity, unit, expiry):
    return {"description": description, "quantity": quantity, "unit": unit, "expiry": expiry}


class FakeOpener:
    def __init__(self, body=b'{"ok": true}', error=None):
        self.body = body
        self.error = error
        self.calls = []

    def __call__(self, request, timeout):
        self.calls.append((request, timeout))
        if self.error:
            raise self.error
        return io.BytesIO(self.body)


def test_no_message_when_nothing_is_due():
    assert build_message([lot("Gelato", 500, "grammi", "2027-01-01")], TODAY, 7) is None
    assert build_message([], TODAY, 7) is None


def test_full_message():
    lots = [
        lot("Piselli", 3, "buste", "2026-09-30"),
        lot("Ragù della nonna", 2, "barattoli_grandi", "2026-09-20"),
        lot("Pizza", 1, "pezzi", "2026-09-28"),
        lot("Pane", 1, "pezzi", "2026-09-27"),
        lot("Gelato", 500, "grammi", "2027-01-01"),
    ]
    assert build_message(lots, TODAY, 7) == (
        "❄️ Freezer · 27/09\n"
        "\n"
        "🔴 Scaduti\n"
        "• Ragù della nonna: 2 barattoli grandi (scaduto il 20/09)\n"
        "\n"
        "🟠 In scadenza\n"
        "• Pane: 1 pezzo (oggi, 27/09)\n"
        "• Pizza: 1 pezzo (domani, 28/09)\n"
        "• Piselli: 3 buste (tra 3 giorni, 30/09)"
    )


def test_only_expiring_section():
    message = build_message([lot("Piselli", 3, "buste", "2026-09-30")], TODAY, 7)
    assert "Scaduti" not in message
    assert message.endswith("• Piselli: 3 buste (tra 3 giorni, 30/09)")


def test_send_telegram_posts_json():
    opener = FakeOpener()
    send_telegram("TOKEN", "-100", "ciao", opener=opener)
    request, timeout = opener.calls[0]
    assert request.full_url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert request.get_method() == "POST"
    assert json.loads(request.data) == {"chat_id": "-100", "text": "ciao"}
    assert timeout == 15


def test_send_telegram_raises_when_telegram_refuses():
    opener = FakeOpener(body=b'{"ok": false, "description": "chat not found"}')
    with pytest.raises(RuntimeError, match="chat not found"):
        send_telegram("TOKEN", "-100", "ciao", opener=opener)


@pytest.fixture
def env(tmp_path):
    db_path = str(tmp_path / "notify.db")
    conn = connect(db_path)
    init_db(conn)
    conn.close()
    return {"FREEZER_DB_PATH": db_path, "TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_CHAT_ID": "C"}


def add_lot(env, expiry):
    conn = connect(env["FREEZER_DB_PATH"])
    apply_ops(conn, [add_op(expiry=expiry)], NOW)
    conn.close()


def test_main_without_telegram_config_does_nothing(env):
    opener = FakeOpener()
    env = {"FREEZER_DB_PATH": env["FREEZER_DB_PATH"]}
    assert main([], env, opener=opener, today=TODAY) == 0
    assert opener.calls == []


def test_main_sends_when_something_is_due(env):
    add_lot(env, "2026-09-29")
    opener = FakeOpener()
    assert main([], env, opener=opener, today=TODAY) == 0
    sent = json.loads(opener.calls[0][0].data)
    assert "Piselli: 5 buste (tra 2 giorni, 29/09)" in sent["text"]


def test_main_sends_nothing_when_nothing_is_due(env):
    add_lot(env, "2027-09-29")
    opener = FakeOpener()
    assert main([], env, opener=opener, today=TODAY) == 0
    assert opener.calls == []


def test_main_returns_1_on_network_error(env):
    add_lot(env, "2026-09-29")
    opener = FakeOpener(error=urllib.error.URLError("rete assente"))
    assert main([], env, opener=opener, today=TODAY) == 1


def test_main_prova_sends_test_message(env):
    opener = FakeOpener()
    assert main(["--prova"], env, opener=opener, today=TODAY) == 0
    assert json.loads(opener.calls[0][0].data)["text"] == TEST_MESSAGE


def telegram_length(text):
    return len(text.encode("utf-16-le")) // 2  # Telegram conta in unità UTF-16


def test_long_message_is_cut_to_telegram_limit():
    expired = [lot(f"Scaduto numero {i:02d} " + "x" * 60, 2, "buste", "2026-09-01") for i in range(30)]
    expiring = [lot(f"In scadenza numero {i:02d} " + "y" * 60, 3, "porzioni", "2026-09-30") for i in range(30)]
    message = build_message(expired + expiring, TODAY, 7)
    assert telegram_length(message) <= 4096
    shown = message.count("\n• ")
    assert message.endswith(f"… e altri {60 - shown}: li trovi nell'app.")
    assert "Scaduto numero 00" in message  # gli scaduti hanno la precedenza
