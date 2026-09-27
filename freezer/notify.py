"""Avviso Telegram delle scadenze. Avviato ogni mattina da freezer-notify.timer."""

import argparse
import json
import logging
import sys
import urllib.error
import urllib.request
from collections.abc import Mapping
from contextlib import closing
from datetime import date

from freezer.catalog import format_quantity
from freezer.config import load_config
from freezer.db import active_lots, connect, init_db
from freezer.expiry import EXPIRED, EXPIRING, days_left, expiry_status, today_in

log = logging.getLogger("freezer.notify")

TEST_MESSAGE = "❄️ Freezer: messaggio di prova. Se lo leggi, gli avvisi funzionano."


def _day_month(value: date) -> str:
    return value.strftime("%d/%m")


def _when(days: int) -> str:
    if days == 0:
        return "oggi"
    if days == 1:
        return "domani"
    return f"tra {days} giorni"


def build_message(lots: list[dict], today: date, warn_days: int) -> str | None:
    expired: list[str] = []
    expiring: list[str] = []
    for lot in sorted(lots, key=lambda item: (item["expiry"], item["description"].casefold())):
        expiry = date.fromisoformat(lot["expiry"])
        status = expiry_status(expiry, today, warn_days)
        line = f"• {lot['description']}: {format_quantity(lot['quantity'], lot['unit'])}"
        if status == EXPIRED:
            expired.append(f"{line} (scaduto il {_day_month(expiry)})")
        elif status == EXPIRING:
            expiring.append(f"{line} ({_when(days_left(expiry, today))}, {_day_month(expiry)})")
    if not expired and not expiring:
        return None
    sections = [f"❄️ Freezer · {_day_month(today)}"]
    if expired:
        sections.append("🔴 Scaduti\n" + "\n".join(expired))
    if expiring:
        sections.append("🟠 In scadenza\n" + "\n".join(expiring))
    return "\n\n".join(sections)


def send_telegram(token: str, chat_id: str, text: str, opener=urllib.request.urlopen, timeout: float = 15) -> None:
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with opener(request, timeout=timeout) as response:
        body = json.load(response)
    if not body.get("ok"):
        raise RuntimeError(f"Telegram ha rifiutato il messaggio: {body.get('description')}")


def main(
    argv: list[str] | None = None,
    env: Mapping[str, str] | None = None,
    opener=urllib.request.urlopen,
    today: date | None = None,
) -> int:
    parser = argparse.ArgumentParser(description="Avviso Telegram delle scadenze del freezer.")
    parser.add_argument("--prova", action="store_true", help="invia solo un messaggio di prova")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    cfg = load_config(env)
    if not cfg.telegram_token or not cfg.telegram_chat_id:
        log.info("Telegram non configurato (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID): nessun avviso.")
        return 0
    if args.prova:
        text = TEST_MESSAGE
    else:
        with closing(connect(cfg.db_path)) as conn:
            init_db(conn)
            lots = active_lots(conn)
        text = build_message(lots, today or today_in(cfg.tz), cfg.warn_days)
        if text is None:
            log.info("Niente di scaduto o in scadenza: nessun messaggio.")
            return 0
    try:
        send_telegram(cfg.telegram_token, cfg.telegram_chat_id, text, opener=opener)
    except (OSError, ValueError, RuntimeError) as exc:  # URLError è un OSError
        log.error("Invio a Telegram fallito: %s", exc)
        return 1
    log.info("Messaggio inviato su Telegram.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
