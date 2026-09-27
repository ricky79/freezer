# Freezer di cantina — Piano di implementazione

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Webapp PWA offline-first per l'inventario del freezer di famiglia, con server Python su PC Linux, sincronizzazione a operazioni e avviso Telegram giornaliero.

**Architecture:** Il server FastAPI + SQLite applica operazioni idempotenti (`add`/`take`/`edit`/`delete`) e restituisce un'istantanea completa. Il telefono tiene istantanea + coda in `localStorage`, mostra "istantanea + coda applicata localmente" e sincronizza quando il PC è raggiungibile. Caddy (`tls internal`) espone l'HTTPS richiesto da iOS per il service worker; systemd gestisce app, notifica e backup.

**Tech Stack:** Python 3.12, FastAPI, uvicorn, SQLite (`sqlite3` stdlib), `urllib` stdlib, pytest + httpx; JavaScript vanilla a moduli ES senza build; Caddy 2; systemd.

**Spec:** `docs/superpowers/specs/2026-09-27-freezer-inventario-design.md`

## Global Constraints

- Python 3.12 (Windows in sviluppo: 3.12.10; Linux Mint 22.2: 3.12.3). Dipendenze runtime solo: `fastapi`, `uvicorn`, `tzdata`.
- Niente Node, niente build frontend: file statici in `web/` serviti così come sono.
- Tutta l'interfaccia e i messaggi utente sono **in italiano**.
- Porta interna dell'app: **8765** (configurabile con `FREEZER_PORT`). **Mai la 5000** (occupata sul PC Linux).
- uvicorn ascolta **solo su 127.0.0.1**. Caddy su 443 (HTTPS) e 80 (pagina certificato), porte parametrizzabili.
- Il catalogo (tipi, unità) esiste **solo** in `freezer/catalog.py`; il client lo riceve nell'istantanea.
- Tipi: `carne` Carne · `pesce` Pesce · `verdure` Verdure · `frutta` Frutta · `sughi` Sughi · `piatti_pronti` Piatti pronti · `pane_pizza` Pane e pizza · `dolci` Dolci · `altro` Altro.
- Unità: `pezzi` (pezzo/pezzi), `buste` (busta/buste), `porzioni` (porzione/porzioni), `vaschette` (vaschetta/vaschette), `barattoli_piccoli` (barattolo piccolo/barattoli piccoli), `barattoli_grandi` (barattolo grande/barattoli grandi), `grammi` (g/g).
- `quantity` intero 1–99999 in `add`/`edit`; `amount` intero ≥ 1; `description` 1–100 caratteri dopo il trim; `expiry` `YYYY-MM-DD`.
- `warn_days` default 7; fuso `Europe/Rome`.
- Esiti operazioni: `applied`, `duplicate`, `ignored`, `invalid`. `/api/sync`: max 500 operazioni, 200 anche con operazioni `invalid`, 400 solo per corpo malformato.
- Timeout client sync: 5 s; ritentativo ogni 30 s finché la coda non è vuota.
- Chiavi `localStorage`: `freezer.snapshot`, `freezer.queue`, `freezer.lastSync`.
- Le fine riga nel repository sono **LF** (gli script girano su Linux).
- Comandi in questo piano: Git Bash su Windows, dalla radice del repository `C:\Progetti\freezer`. Il Python del venv è `.venv/Scripts/python` (su Linux sarebbe `.venv/bin/python`).

## Review Focus

1. **Descrizioni con caratteri speciali** (`Pollo <arrosto> & "patate"`, `Ragù 🍝`): devono arrivare al server e tornare identiche, ed essere mostrate come testo, mai interpretate come HTML. Test: Task 3 (`test_sync_roundtrips_special_characters`), Task 6 (`escapeHtml`).
2. **Date vicino a mezzanotte e date `YYYY-MM-DD` lette come UTC**: "oggi" è la data locale del telefono; una scadenza non deve mai slittare di un giorno. Test: Task 6 (`todayIso` alle 23:59 e alle 00:01, `daysLeft` senza oggetti `Date` UTC).
3. **Quantità scritte male nei campi** (`"1,5"`, `"0"`, `""`, `"abc"`, `"100000"`, `" 12 "`): vanno rifiutate con un messaggio, tranne `" 12 "` che vale 12. Test: Task 6 (`parseQuantity`).
4. **`localStorage` assente, pieno o corrotto** (navigazione privata, JSON rovinato): l'app deve partire lo stesso con valori vuoti. Test: Task 6 (`persist` con storage finto che lancia eccezioni o contiene JSON non valido).
5. **"Aggiungi" e poi "Prendi" sullo stesso lotto offline, prima di sincronizzare**, e **coda più lunga di 500 operazioni**: il server deve applicarle nello stesso invio in ordine, e il client deve spezzare la coda in blocchi da 500. Test: Task 2 (`test_add_then_take_in_same_batch`), Task 6 (`store` add + take), Task 7 (blocchi da 500).

## Struttura dei file

| File | Responsabilità |
|---|---|
| `freezer/catalog.py` | Tipi e unità, formattazione quantità |
| `freezer/expiry.py` | Stato di scadenza (Python) |
| `freezer/config.py` | Lettura configurazione da variabili d'ambiente |
| `freezer/db.py` | Connessione, schema, transazione di scrittura, query istantanea e suggerimenti |
| `freezer/ops.py` | Validazione e applicazione delle operazioni |
| `freezer/api.py` | App FastAPI: `/api/inventory`, `/api/sync`, `/sw.js` versionato, file statici |
| `freezer/notify.py` | Costruzione e invio del messaggio Telegram, `main` |
| `freezer/backup.py` | Backup SQLite e rotazione, `main` |
| `web/expiry.js` | Date locali, stato e testi di scadenza, `addMonths` |
| `web/format.js` | Formattazione quantità, `normalizeText`, `escapeHtml`, `parseQuantity` |
| `web/persist.js` | Lettura/scrittura `localStorage` protetta |
| `web/store.js` | Applicazione locale delle operazioni, vista, coda, creazione operazioni |
| `web/sync.js` | Ciclo di sincronizzazione (fetch iniettabile) |
| `web/app.js` | Interfaccia: rendering, eventi, dialoghi, avvio sync e service worker |
| `web/index.html`, `web/style.css` | Struttura e stile |
| `web/sw.js`, `web/manifest.webmanifest`, `web/icons/*` | PWA offline |
| `tools/make_icons.py` | Genera le icone PNG (solo stdlib) |
| `tests/js/test.html`, `tests/js/harness.js`, `tests/js/*.test.js` | Test JS nel browser |
| `deploy/*` | Caddyfile, pagina certificato, unità systemd, `install.sh`, esempio env |

---

### Task 1: Fondamenta — progetto, catalogo, scadenze, configurazione

**Files:**
- Create: `.gitignore`, `.gitattributes`, `pyproject.toml`, `requirements.txt`, `requirements-dev.txt`
- Create: `freezer/__init__.py`, `freezer/catalog.py`, `freezer/expiry.py`, `freezer/config.py`
- Test: `tests/test_catalog.py`, `tests/test_expiry.py`, `tests/test_config.py`

**Interfaces:**
- Consumes: nulla.
- Produces:
  - `freezer.catalog`: `CATEGORIES: list[tuple[str, str]]`, `UNITS: list[tuple[str, str, str]]`, `CATEGORY_CODES: frozenset[str]`, `UNIT_CODES: frozenset[str]`, `catalog_json() -> dict`, `format_quantity(quantity: int, unit: str) -> str`.
  - `freezer.expiry`: `EXPIRED`, `EXPIRING`, `OK` (stringhe `"expired"`, `"expiring"`, `"ok"`), `today_in(tz: str) -> date`, `days_left(expiry: date, today: date) -> int`, `expiry_status(expiry: date, today: date, warn_days: int) -> str`.
  - `freezer.config`: `Config` (dataclass frozen: `db_path: str`, `port: int`, `warn_days: int`, `tz: str`, `backup_dir: str`, `backup_keep: int`, `telegram_token: str`, `telegram_chat_id: str`), `load_config(env: Mapping[str, str] | None = None) -> Config`.

- [ ] **Step 1: File di progetto**

`.gitignore`:
```
.venv/
__pycache__/
.pytest_cache/
*.db
*.db-wal
*.db-shm
backups/
```

`.gitattributes`:
```
* text=auto eol=lf
*.png binary
```

`pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = [".", "tests"]
```

`requirements.txt`:
```
fastapi>=0.115,<1
uvicorn>=0.30,<1
tzdata>=2024.1
```

`requirements-dev.txt`:
```
-r requirements.txt
pytest>=8
httpx>=0.27
```

`freezer/__init__.py`:
```python
"""Inventario del freezer di cantina."""
```

- [ ] **Step 2: Crea il venv e installa le dipendenze**

Run: `python -m venv .venv && .venv/Scripts/python -m pip install -q -r requirements-dev.txt`
Expected: nessun errore.

- [ ] **Step 3: Scrivi i test che falliscono**

`tests/test_catalog.py`:
```python
import pytest

from freezer.catalog import CATEGORY_CODES, UNIT_CODES, catalog_json, format_quantity


def test_catalog_contains_requested_codes():
    assert "sughi" in CATEGORY_CODES
    assert {"barattoli_piccoli", "barattoli_grandi", "grammi"} <= UNIT_CODES
    assert len(CATEGORY_CODES) == 9
    assert len(UNIT_CODES) == 7


def test_catalog_json_shape():
    data = catalog_json()
    assert data["categories"][0] == {"code": "carne", "label": "Carne"}
    assert {"code": "buste", "singular": "busta", "plural": "buste"} in data["units"]


@pytest.mark.parametrize(
    ("quantity", "unit", "expected"),
    [
        (1, "buste", "1 busta"),
        (3, "buste", "3 buste"),
        (1, "barattoli_piccoli", "1 barattolo piccolo"),
        (2, "barattoli_grandi", "2 barattoli grandi"),
        (500, "grammi", "500 g"),
        (1, "grammi", "1 g"),
    ],
)
def test_format_quantity(quantity, unit, expected):
    assert format_quantity(quantity, unit) == expected
```

`tests/test_expiry.py`:
```python
from datetime import date

import pytest

from freezer.expiry import EXPIRED, EXPIRING, OK, days_left, expiry_status, today_in

TODAY = date(2026, 9, 27)


def test_days_left_crosses_month():
    assert days_left(date(2026, 10, 2), TODAY) == 5


@pytest.mark.parametrize(
    ("expiry", "expected"),
    [
        (date(2026, 9, 26), EXPIRED),   # ieri
        (date(2026, 9, 27), EXPIRING),  # oggi
        (date(2026, 9, 28), EXPIRING),  # domani
        (date(2026, 10, 4), EXPIRING),  # oggi + 7
        (date(2026, 10, 5), OK),        # oggi + 8
    ],
)
def test_expiry_status_boundaries(expiry, expected):
    assert expiry_status(expiry, TODAY, 7) == expected


def test_warn_days_zero_only_today_is_expiring():
    assert expiry_status(TODAY, TODAY, 0) == EXPIRING
    assert expiry_status(date(2026, 9, 28), TODAY, 0) == OK


def test_today_in_returns_a_date():
    assert isinstance(today_in("Europe/Rome"), date)
```

`tests/test_config.py`:
```python
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
```

- [ ] **Step 4: Verifica che falliscano**

Run: `.venv/Scripts/python -m pytest -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'freezer.catalog'` (e analoghi).

- [ ] **Step 5: Implementa**

`freezer/catalog.py`:
```python
"""Tipi e unità: unica fonte di verità, inviata anche al telefono."""

CATEGORIES: list[tuple[str, str]] = [
    ("carne", "Carne"),
    ("pesce", "Pesce"),
    ("verdure", "Verdure"),
    ("frutta", "Frutta"),
    ("sughi", "Sughi"),
    ("piatti_pronti", "Piatti pronti"),
    ("pane_pizza", "Pane e pizza"),
    ("dolci", "Dolci"),
    ("altro", "Altro"),
]

UNITS: list[tuple[str, str, str]] = [
    ("pezzi", "pezzo", "pezzi"),
    ("buste", "busta", "buste"),
    ("porzioni", "porzione", "porzioni"),
    ("vaschette", "vaschetta", "vaschette"),
    ("barattoli_piccoli", "barattolo piccolo", "barattoli piccoli"),
    ("barattoli_grandi", "barattolo grande", "barattoli grandi"),
    ("grammi", "g", "g"),
]

CATEGORY_CODES = frozenset(code for code, _ in CATEGORIES)
UNIT_CODES = frozenset(code for code, _, _ in UNITS)
_UNIT_LABELS = {code: (singular, plural) for code, singular, plural in UNITS}


def catalog_json() -> dict:
    return {
        "categories": [{"code": code, "label": label} for code, label in CATEGORIES],
        "units": [
            {"code": code, "singular": singular, "plural": plural}
            for code, singular, plural in UNITS
        ],
    }


def format_quantity(quantity: int, unit: str) -> str:
    singular, plural = _UNIT_LABELS[unit]
    return f"{quantity} {singular if quantity == 1 else plural}"
```

`freezer/expiry.py`:
```python
"""Stato di scadenza di un lotto. Stessa regola di web/expiry.js."""

from datetime import date, datetime
from zoneinfo import ZoneInfo

EXPIRED = "expired"
EXPIRING = "expiring"
OK = "ok"


def today_in(tz: str) -> date:
    return datetime.now(ZoneInfo(tz)).date()


def days_left(expiry: date, today: date) -> int:
    return (expiry - today).days


def expiry_status(expiry: date, today: date, warn_days: int) -> str:
    days = days_left(expiry, today)
    if days < 0:
        return EXPIRED
    if days <= warn_days:
        return EXPIRING
    return OK
```

`freezer/config.py`:
```python
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
```

- [ ] **Step 6: Verifica che passino**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tutti PASS.

- [ ] **Step 7: Commit**

```bash
git add .gitignore .gitattributes pyproject.toml requirements.txt requirements-dev.txt freezer tests
git commit -m "feat: catalogo, stato di scadenza e configurazione"
```

---
### Task 2: Database e regole delle operazioni

**Files:**
- Create: `freezer/db.py`, `freezer/ops.py`
- Test: `tests/conftest.py`, `tests/builders.py`, `tests/test_db.py`, `tests/test_ops.py`

**Interfaces:**
- Consumes: `freezer.catalog.CATEGORY_CODES`, `freezer.catalog.UNIT_CODES`.
- Produces:
  - `freezer.db`: `connect(path: str) -> sqlite3.Connection` (autocommit, `row_factory=sqlite3.Row`, WAL, busy_timeout 5000), `init_db(conn) -> None`, `write_transaction(conn)` (context manager, `BEGIN IMMEDIATE`/`COMMIT`/`ROLLBACK`), `get_lot(conn, lot_id: str) -> sqlite3.Row | None`, `active_lots(conn) -> list[dict]` (chiavi `id, description, category, quantity, unit, expiry`), `suggestions(conn, limit: int = 200) -> list[dict]` (chiavi `description, category, unit`).
  - `freezer.ops`: costanti `APPLIED`, `DUPLICATE`, `IGNORED`, `INVALID`; `apply_ops(conn, ops: list, now: str) -> list[dict]` (ogni elemento `{"op_id": str | None, "status": str}`).
  - `tests/builders.py`: `add_op`, `take_op`, `edit_op`, `delete_op` (costruttori di operazioni per i test), costanti `NOW`, `LATER`.

- [ ] **Step 1: Fixture e costruttori per i test**

`tests/conftest.py`:
```python
import pytest

from freezer.db import connect, init_db


@pytest.fixture
def conn(tmp_path):
    connection = connect(str(tmp_path / "test.db"))
    init_db(connection)
    yield connection
    connection.close()
```

`tests/builders.py`:
```python
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
```

- [ ] **Step 2: Scrivi i test del database**

`tests/test_db.py`:
```python
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
```

- [ ] **Step 3: Scrivi i test delle operazioni**

`tests/test_ops.py`:
```python
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
```

- [ ] **Step 4: Verifica che falliscano**

Run: `.venv/Scripts/python -m pytest tests/test_db.py tests/test_ops.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'freezer.db'`.

- [ ] **Step 5: Implementa `freezer/db.py`**

```python
"""Accesso a SQLite: schema, connessione, transazioni, letture per l'istantanea."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

SCHEMA = """
CREATE TABLE IF NOT EXISTS lots (
    id          TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    category    TEXT NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity >= 0),
    unit        TEXT NOT NULL,
    expiry      TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('active', 'consumed', 'deleted')),
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS lots_status ON lots (status);
CREATE TABLE IF NOT EXISTS applied_ops (
    op_id      TEXT PRIMARY KEY,
    applied_at TEXT NOT NULL
);
"""


def connect(path: str) -> sqlite3.Connection:
    # isolation_level=None: niente transazioni implicite, le apriamo noi con BEGIN IMMEDIATE.
    conn = sqlite3.connect(path, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)


@contextmanager
def write_transaction(conn: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    # IMMEDIATE prende subito il lock di scrittura: due telefoni che sincronizzano
    # insieme vengono serializzati invece di fallire con "database is locked".
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def get_lot(conn: sqlite3.Connection, lot_id: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM lots WHERE id = ?", (lot_id,)).fetchone()


def active_lots(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT id, description, category, quantity, unit, expiry FROM lots "
        "WHERE status = 'active' "
        "ORDER BY expiry, description COLLATE NOCASE, id"
    ).fetchall()
    return [dict(row) for row in rows]


def suggestions(conn: sqlite3.Connection, limit: int = 200) -> list[dict]:
    rows = conn.execute(
        "SELECT description, category, unit FROM lots "
        "WHERE status IN ('active', 'consumed') "
        "ORDER BY created_at DESC, rowid DESC"
    )
    seen: set[str] = set()
    result: list[dict] = []
    for row in rows:
        key = row["description"].casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(dict(row))
        if len(result) == limit:
            break
    return result
```

- [ ] **Step 6: Implementa `freezer/ops.py`**

```python
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
```

- [ ] **Step 7: Verifica che passino**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tutti PASS.

- [ ] **Step 8: Commit**

```bash
git add freezer/db.py freezer/ops.py tests/conftest.py tests/builders.py tests/test_db.py tests/test_ops.py
git commit -m "feat: database SQLite e regole idempotenti delle operazioni"
```

---

### Task 3: API FastAPI

**Files:**
- Create: `freezer/api.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `load_config`, `Config` (Task 1); `connect`, `init_db`, `active_lots`, `suggestions` (Task 2); `apply_ops` (Task 2); `catalog_json` (Task 1).
- Produces:
  - `freezer.api.create_app(config: Config | None = None, web_dir: Path = WEB_DIR) -> FastAPI`, avviabile con `uvicorn --factory freezer.api:create_app`.
  - `GET /api/inventory` → istantanea `{"server_time", "warn_days", "catalog", "lots", "suggestions"}`.
  - `POST /api/sync` con `{"ops": [...]}` → `{"results": [...], ...istantanea}`; 400 con `{"error": "..."}` per corpo malformato o più di 500 operazioni.
  - Le risposte `/api/*` hanno `Cache-Control: no-store`.
  - `WEB_DIR` = cartella `web/` del repository, montata su `/` con `html=True`.

- [ ] **Step 1: Scrivi i test che falliscono**

`tests/test_api.py`:
```python
import pytest
from fastapi.testclient import TestClient

from builders import add_op, take_op
from freezer.api import create_app
from freezer.config import load_config

SPECIAL = 'Pollo <arrosto> & "patate" 🍝 Ragù'


@pytest.fixture
def client(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>Freezer</h1>", encoding="utf-8")
    cfg = load_config({"FREEZER_DB_PATH": str(tmp_path / "api.db"), "FREEZER_WARN_DAYS": "5"})
    with TestClient(create_app(cfg, web_dir=web)) as test_client:
        yield test_client


def sync(client, ops):
    return client.post("/api/sync", json={"ops": ops})


def test_inventory_empty_snapshot(client):
    response = client.get("/api/inventory")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    data = response.json()
    assert set(data) == {"server_time", "warn_days", "catalog", "lots", "suggestions"}
    assert data["warn_days"] == 5
    assert data["lots"] == []
    assert data["suggestions"] == []
    assert len(data["catalog"]["categories"]) == 9
    assert "T" in data["server_time"]


def test_sync_applies_ops_and_returns_snapshot(client):
    response = sync(client, [add_op(), take_op("t", 2)])
    assert response.status_code == 200
    data = response.json()
    assert data["results"] == [
        {"op_id": "op-add", "status": "applied"},
        {"op_id": "t", "status": "applied"},
    ]
    assert data["lots"][0]["quantity"] == 3
    assert data["suggestions"] == [{"description": "Piselli", "category": "verdure", "unit": "buste"}]


def test_resending_is_duplicate(client):
    sync(client, [add_op(), take_op("t", 2)])
    data = sync(client, [add_op(), take_op("t", 2)]).json()
    assert [r["status"] for r in data["results"]] == ["duplicate", "duplicate"]
    assert data["lots"][0]["quantity"] == 3


def test_sync_roundtrips_special_characters(client):
    sync(client, [add_op(description=SPECIAL)])
    assert client.get("/api/inventory").json()["lots"][0]["description"] == SPECIAL


def test_invalid_op_still_returns_200(client):
    response = sync(client, [{"op_id": "x", "type": "explode"}, add_op()])
    assert response.status_code == 200
    assert [r["status"] for r in response.json()["results"]] == ["invalid", "applied"]


def test_empty_ops_returns_snapshot(client):
    data = sync(client, []).json()
    assert data["results"] == []
    assert data["lots"] == []


@pytest.mark.parametrize(
    "body",
    [b"{non json", b"[]", b'{"ops": "x"}', b'{"altro": []}', b"\xff\xfe"],
)
def test_malformed_body_is_400(client, body):
    response = client.post("/api/sync", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 400
    assert "error" in response.json()


def test_at_most_500_ops(client):
    ops = [add_op(f"op{i}", f"lot{i}") for i in range(501)]
    assert sync(client, ops).status_code == 400
    assert sync(client, ops[:500]).status_code == 200


def test_static_index_is_served(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Freezer" in response.text
```

- [ ] **Step 2: Verifica che falliscano**

Run: `.venv/Scripts/python -m pytest tests/test_api.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'freezer.api'`.

- [ ] **Step 3: Implementa `freezer/api.py`**

```python
"""App FastAPI: istantanea, sincronizzazione e file statici dell'interfaccia."""

import json
import mimetypes
from contextlib import closing
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool

from freezer.catalog import catalog_json
from freezer.config import Config, load_config
from freezer.db import active_lots, connect, init_db, suggestions
from freezer.ops import apply_ops

WEB_DIR = Path(__file__).resolve().parent.parent / "web"
MAX_OPS = 500
NO_STORE = {"Cache-Control": "no-store"}

# Su Windows il registro può associare .js a text/plain e i moduli ES non partirebbero.
mimetypes.add_type("text/javascript", ".js")
mimetypes.add_type("application/manifest+json", ".webmanifest")


def _bad_request(message: str) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=400, headers=NO_STORE)


def create_app(config: Config | None = None, web_dir: Path = WEB_DIR) -> FastAPI:
    cfg = config or load_config()
    tz = ZoneInfo(cfg.tz)
    with closing(connect(cfg.db_path)) as conn:
        init_db(conn)

    app = FastAPI(title="Freezer", docs_url=None, redoc_url=None, openapi_url=None)

    def now() -> str:
        return datetime.now(tz).isoformat(timespec="seconds")

    def snapshot(conn) -> dict:
        return {
            "server_time": now(),
            "warn_days": cfg.warn_days,
            "catalog": catalog_json(),
            "lots": active_lots(conn),
            "suggestions": suggestions(conn),
        }

    def read_snapshot() -> dict:
        with closing(connect(cfg.db_path)) as conn:
            return snapshot(conn)

    def sync_ops(ops: list) -> dict:
        with closing(connect(cfg.db_path)) as conn:
            results = apply_ops(conn, ops, now())
            return {"results": results, **snapshot(conn)}

    @app.get("/api/inventory")
    def inventory() -> JSONResponse:
        return JSONResponse(read_snapshot(), headers=NO_STORE)

    @app.post("/api/sync")
    async def sync(request: Request) -> JSONResponse:
        try:
            body = json.loads(await request.body())
        except ValueError:  # include JSONDecodeError e UnicodeDecodeError
            return _bad_request("Il corpo della richiesta non è JSON valido.")
        ops = body.get("ops") if isinstance(body, dict) else None
        if not isinstance(ops, list):
            return _bad_request('Serve un oggetto con la lista "ops".')
        if len(ops) > MAX_OPS:
            return _bad_request(f"Al massimo {MAX_OPS} operazioni per richiesta.")
        return JSONResponse(await run_in_threadpool(sync_ops, ops), headers=NO_STORE)

    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
    return app
```

- [ ] **Step 4: Verifica che passino**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tutti PASS.

- [ ] **Step 5: Prova manuale del server**

Crea un segnaposto `web/index.html` (verrà sostituito nel Task 8):
```html
<!doctype html>
<title>Freezer</title>
<p>Freezer</p>
```
Run (in background): `.venv/Scripts/python -m uvicorn --factory freezer.api:create_app --host 127.0.0.1 --port 8765`
Poi: `curl -s http://127.0.0.1:8765/api/inventory`
Expected: JSON con `"lots":[]` e il catalogo. Ferma il server.

- [ ] **Step 6: Commit**

```bash
git add freezer/api.py tests/test_api.py web/index.html
git commit -m "feat: API di inventario e sincronizzazione"
```

---

### Task 4: Avviso Telegram

**Files:**
- Create: `freezer/notify.py`
- Test: `tests/test_notify.py`

**Interfaces:**
- Consumes: `format_quantity` (Task 1); `EXPIRED`, `EXPIRING`, `days_left`, `expiry_status`, `today_in` (Task 1); `load_config` (Task 1); `connect`, `init_db`, `active_lots` (Task 2).
- Produces:
  - `build_message(lots: list[dict], today: date, warn_days: int) -> str | None` (usa le chiavi `description`, `quantity`, `unit`, `expiry`).
  - `send_telegram(token: str, chat_id: str, text: str, opener=urllib.request.urlopen, timeout: float = 15) -> None` (solleva in caso di errore).
  - `main(argv=None, env=None, opener=urllib.request.urlopen, today: date | None = None) -> int`; `python -m freezer.notify [--prova]`.
  - `TEST_MESSAGE: str`.

Il formato del messaggio è quello della spec §6 (testo per gli scaduti: `(scaduto il 20/09)`).

- [ ] **Step 1: Scrivi i test che falliscono**

`tests/test_notify.py`:
```python
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
```

- [ ] **Step 2: Verifica che falliscano**

Run: `.venv/Scripts/python -m pytest tests/test_notify.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'freezer.notify'`.

- [ ] **Step 3: Implementa `freezer/notify.py`**

```python
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
```

- [ ] **Step 4: Verifica che passino**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git add freezer/notify.py tests/test_notify.py
git commit -m "feat: avviso Telegram delle scadenze"
```

---

### Task 5: Backup notturno

**Files:**
- Create: `freezer/backup.py`
- Test: `tests/test_backup.py`

**Interfaces:**
- Consumes: `load_config` (Task 1); in test `connect`, `init_db`, `apply_ops`.
- Produces: `backup_db(db_path: str, backup_dir: str, keep: int, now: datetime) -> Path`; `main(env=None, now: datetime | None = None) -> int`; `python -m freezer.backup`.

- [ ] **Step 1: Scrivi i test che falliscono**

`tests/test_backup.py`:
```python
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
```

- [ ] **Step 2: Verifica che falliscano**

Run: `.venv/Scripts/python -m pytest tests/test_backup.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'freezer.backup'`.

- [ ] **Step 3: Implementa `freezer/backup.py`**

```python
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
```

- [ ] **Step 4: Verifica che passino**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tutti PASS.

- [ ] **Step 5: Commit**

```bash
git add freezer/backup.py tests/test_backup.py
git commit -m "feat: backup notturno del database con rotazione"
```

---

### Task 6: Moduli JS puri e test nel browser

**Files:**
- Create: `web/expiry.js`, `web/format.js`, `web/persist.js`, `web/store.js`
- Create: `tools/serve_tests.py`
- Test: `tests/js/test.html`, `tests/js/harness.js`, `tests/js/catalog.fixture.js`, `tests/js/expiry.test.js`, `tests/js/format.test.js`, `tests/js/persist.test.js`, `tests/js/store.test.js`

**Interfaces:**
- Consumes: il formato dell'istantanea e delle operazioni (Task 2/3): lotto `{id, description, category, quantity, unit, expiry}`; catalogo `{categories: [{code, label}], units: [{code, singular, plural}]}`.
- Produces:
  - `web/expiry.js`: `todayIso(now?: Date) -> string`, `daysLeft(expiryIso, todayIso) -> number`, `expiryStatus(expiryIso, todayIso, warnDays) -> 'expired'|'expiring'|'ok'`, `expiryText(expiryIso, todayIso) -> string`, `countAlerts(lots, todayIso, warnDays) -> {expired, expiring}`, `formatDayMonth(iso) -> 'gg/mm'`, `formatDate(iso) -> 'gg/mm/aaaa'`, `addMonths(iso, months) -> iso`.
  - `web/format.js`: `formatQuantity(quantity, unitCode, catalog) -> string`, `categoryLabel(code, catalog) -> string`, `normalizeText(text) -> string`, `escapeHtml(text) -> string`, `MAX_QUANTITY = 99999`, `parseQuantity(text, max = MAX_QUANTITY) -> number | null`.
  - `web/persist.js`: `createPersist(storage) -> {load(key, fallback), save(key, value) -> boolean}`, `persist` (istanza su `localStorage`).
  - `web/store.js`: `applyOp(lots, op) -> lots`, `compareLots(a, b)`, `viewLots(lots, queue) -> lots` (ordinati, input non modificato), `removeSent(queue, sentIds: Set) -> queue`, `makeOp(type, payload, {uuid, now}?) -> op`, `changedFields(original, updated) -> object`.
  - `tests/js/harness.js`: `test(name, fn)`, `assert(cond, msg)`, `assertEqual(actual, expected, msg)`, `run()`.
  - Esecuzione dei test JS (usata anche dal Task 7):
    1. in background: `.venv/Scripts/python tools/serve_tests.py`
    2. `"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --no-first-run --user-data-dir="$TEMP/freezer-chrome-test" --virtual-time-budget=10000 --dump-dom http://127.0.0.1:8766/tests/js/test.html 2>/dev/null | grep -o 'data-summary="[^"]*"'`
    3. per vedere i dettagli di un fallimento: stesso comando con `| grep -o 'class="fail">[^<]*'`.

- [ ] **Step 1: Server statico e harness dei test**

`tools/serve_tests.py`:
```python
"""Serve il repository su http://127.0.0.1:8766 per i test JS nel browser."""

import functools
import http.server
import mimetypes
from pathlib import Path

# Su Windows il registro può associare .js a text/plain e i moduli ES non partirebbero.
mimetypes.add_type("text/javascript", ".js")

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    print("Test JS: http://127.0.0.1:8766/tests/js/test.html")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8766), handler).serve_forever()
```

`tests/js/harness.js`:
```js
// Mini harness: nessuna dipendenza, gira in qualunque browser.
const tests = [];

export function test(name, fn) {
  tests.push({ name, fn });
}

function deepEqual(a, b) {
  if (Object.is(a, b)) return true;
  if (typeof a !== 'object' || typeof b !== 'object' || a === null || b === null) return false;
  if (Array.isArray(a) !== Array.isArray(b)) return false;
  const keysA = Object.keys(a);
  const keysB = Object.keys(b);
  if (keysA.length !== keysB.length) return false;
  return keysA.every((key) => Object.prototype.hasOwnProperty.call(b, key) && deepEqual(a[key], b[key]));
}

export function assert(condition, message = 'condizione falsa') {
  if (!condition) throw new Error(message);
}

export function assertEqual(actual, expected, message = '') {
  if (!deepEqual(actual, expected)) {
    throw new Error(`${message} atteso ${JSON.stringify(expected)}, ottenuto ${JSON.stringify(actual)}`);
  }
}

export async function run() {
  const list = document.getElementById('results');
  let failed = 0;
  for (const { name, fn } of tests) {
    const item = document.createElement('li');
    try {
      await fn();
      item.className = 'pass';
      item.textContent = `✓ ${name}`;
    } catch (error) {
      failed += 1;
      item.className = 'fail';
      item.textContent = `✗ ${name}: ${error.message}`;
      console.error(name, error);
    }
    list.appendChild(item);
  }
  const status = failed ? 'FAIL' : 'PASS';
  const summary = document.getElementById('summary');
  summary.textContent = `${status}: ${tests.length - failed}/${tests.length} test passati`;
  summary.dataset.summary = `${status} ${tests.length - failed}/${tests.length}`;
  document.title = summary.textContent;
}
```

`tests/js/test.html`:
```html
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <title>Test JS Freezer</title>
  <style>.pass { color: #1a7f37; } .fail { color: #b3261e; font-weight: bold; }</style>
</head>
<body>
  <h1 id="summary" data-summary="RUNNING">In esecuzione…</h1>
  <ul id="results"></ul>
  <script type="module">
    import { run } from './harness.js';
    import './expiry.test.js';
    import './format.test.js';
    import './persist.test.js';
    import './store.test.js';
    run();
  </script>
</body>
</html>
```

`tests/js/catalog.fixture.js`:
```js
export const CATALOG = {
  categories: [
    { code: 'carne', label: 'Carne' },
    { code: 'sughi', label: 'Sughi' },
  ],
  units: [
    { code: 'pezzi', singular: 'pezzo', plural: 'pezzi' },
    { code: 'buste', singular: 'busta', plural: 'buste' },
    { code: 'barattoli_grandi', singular: 'barattolo grande', plural: 'barattoli grandi' },
    { code: 'grammi', singular: 'g', plural: 'g' },
  ],
};
```

- [ ] **Step 2: Scrivi i test che falliscono**

`tests/js/expiry.test.js`:
```js
import { test, assertEqual } from './harness.js';
import {
  addMonths, countAlerts, daysLeft, expiryStatus, expiryText, formatDate, formatDayMonth, todayIso,
} from '../../web/expiry.js';

test('todayIso usa la data locale anche vicino a mezzanotte', () => {
  assertEqual(todayIso(new Date(2026, 8, 27, 23, 59)), '2026-09-27');
  assertEqual(todayIso(new Date(2026, 8, 28, 0, 1)), '2026-09-28');
  assertEqual(todayIso(new Date(2027, 0, 5, 12, 0)), '2027-01-05');
});

test('daysLeft attraversa mesi e cambio ora legale', () => {
  assertEqual(daysLeft('2026-10-02', '2026-09-27'), 5);
  assertEqual(daysLeft('2026-10-26', '2026-10-24'), 2);
  assertEqual(daysLeft('2026-09-26', '2026-09-27'), -1);
});

test('expiryStatus ai confini', () => {
  const today = '2026-09-27';
  assertEqual(expiryStatus('2026-09-26', today, 7), 'expired');
  assertEqual(expiryStatus('2026-09-27', today, 7), 'expiring');
  assertEqual(expiryStatus('2026-10-04', today, 7), 'expiring');
  assertEqual(expiryStatus('2026-10-05', today, 7), 'ok');
  assertEqual(expiryStatus('2026-09-28', today, 0), 'ok');
});

test('expiryText', () => {
  const today = '2026-09-27';
  assertEqual(expiryText('2026-09-20', today), 'scaduto da 7 giorni');
  assertEqual(expiryText('2026-09-26', today), 'scaduto ieri');
  assertEqual(expiryText('2026-09-27', today), 'oggi');
  assertEqual(expiryText('2026-09-28', today), 'domani');
  assertEqual(expiryText('2026-10-02', today), 'tra 5 giorni');
});

test('countAlerts conta scaduti e in scadenza', () => {
  const lots = [{ expiry: '2026-09-01' }, { expiry: '2026-09-27' }, { expiry: '2026-09-30' }, { expiry: '2027-01-01' }];
  assertEqual(countAlerts(lots, '2026-09-27', 7), { expired: 1, expiring: 2 });
});

test('formattazione date', () => {
  assertEqual(formatDayMonth('2026-09-07'), '07/09');
  assertEqual(formatDate('2026-09-07'), '07/09/2026');
});

test('addMonths gestisce fine mese e anni bisestili', () => {
  assertEqual(addMonths('2026-09-27', 1), '2026-10-27');
  assertEqual(addMonths('2026-09-27', 6), '2027-03-27');
  assertEqual(addMonths('2026-11-15', 3), '2027-02-15');
  assertEqual(addMonths('2026-01-31', 1), '2026-02-28');
  assertEqual(addMonths('2028-01-31', 1), '2028-02-29');
  assertEqual(addMonths('2026-08-31', 3), '2026-11-30');
});
```

`tests/js/format.test.js`:
```js
import { test, assertEqual } from './harness.js';
import { CATALOG } from './catalog.fixture.js';
import { categoryLabel, escapeHtml, formatQuantity, normalizeText, parseQuantity } from '../../web/format.js';

test('formatQuantity usa singolare e plurale', () => {
  assertEqual(formatQuantity(1, 'buste', CATALOG), '1 busta');
  assertEqual(formatQuantity(3, 'buste', CATALOG), '3 buste');
  assertEqual(formatQuantity(2, 'barattoli_grandi', CATALOG), '2 barattoli grandi');
  assertEqual(formatQuantity(500, 'grammi', CATALOG), '500 g');
  assertEqual(formatQuantity(4, 'sconosciuta', CATALOG), '4');
});

test('categoryLabel', () => {
  assertEqual(categoryLabel('sughi', CATALOG), 'Sughi');
  assertEqual(categoryLabel('boh', CATALOG), 'boh');
});

test('normalizeText ignora maiuscole e accenti', () => {
  assertEqual(normalizeText('  Ragù ÀBC '), 'ragu abc');
});

test('escapeHtml neutralizza i caratteri HTML e lascia il resto', () => {
  assertEqual(
    escapeHtml(`Pollo <arrosto> & "patate" l'altro 🍝`),
    'Pollo &lt;arrosto&gt; &amp; &quot;patate&quot; l&#39;altro 🍝',
  );
});

test('parseQuantity accetta solo interi nel limite', () => {
  assertEqual(parseQuantity(' 12 '), 12);
  assertEqual(parseQuantity('007'), 7);
  assertEqual(parseQuantity('99999'), 99999);
  assertEqual(parseQuantity('100000'), null);
  assertEqual(parseQuantity('1,5'), null);
  assertEqual(parseQuantity('1.5'), null);
  assertEqual(parseQuantity('0'), null);
  assertEqual(parseQuantity('-3'), null);
  assertEqual(parseQuantity(''), null);
  assertEqual(parseQuantity('abc'), null);
  assertEqual(parseQuantity(undefined), null);
  assertEqual(parseQuantity('5', 3), null);
  assertEqual(parseQuantity('3', 3), 3);
});
```

`tests/js/persist.test.js`:
```js
import { test, assertEqual } from './harness.js';
import { createPersist } from '../../web/persist.js';

function memoryStorage() {
  const data = new Map();
  return {
    getItem: (key) => (data.has(key) ? data.get(key) : null),
    setItem: (key, value) => data.set(key, String(value)),
  };
}

test('salva e rilegge', () => {
  const persist = createPersist(memoryStorage());
  assertEqual(persist.save('k', { a: [1, 2] }), true);
  assertEqual(persist.load('k', null), { a: [1, 2] });
});

test('chiave assente restituisce il valore di default', () => {
  assertEqual(createPersist(memoryStorage()).load('manca', []), []);
});

test('JSON corrotto restituisce il valore di default', () => {
  const storage = memoryStorage();
  storage.setItem('k', '{rotto');
  assertEqual(createPersist(storage).load('k', 'default'), 'default');
});

test('storage che lancia eccezioni non blocca l\'app', () => {
  const broken = {
    getItem: () => { throw new Error('SecurityError'); },
    setItem: () => { throw new Error('QuotaExceededError'); },
  };
  const persist = createPersist(broken);
  assertEqual(persist.load('k', 1), 1);
  assertEqual(persist.save('k', 2), false);
});

test('storage assente', () => {
  const persist = createPersist(null);
  assertEqual(persist.load('k', 'x'), 'x');
  assertEqual(persist.save('k', 'y'), false);
});
```

`tests/js/store.test.js`:
```js
import { test, assert, assertEqual } from './harness.js';
import { applyOp, changedFields, makeOp, removeSent, viewLots } from '../../web/store.js';

const lot = (id, extra = {}) => ({
  id, description: 'Piselli', category: 'verdure', quantity: 5, unit: 'buste', expiry: '2027-01-31', ...extra,
});
const add = (l) => ({ op_id: `add-${l.id}`, type: 'add', lot: l });
const take = (id, amount, opId = `take-${id}-${amount}`) => ({ op_id: opId, type: 'take', lot_id: id, amount });

test('add aggiunge, add con id esistente è ignorata', () => {
  assertEqual(applyOp([], add(lot('a'))), [lot('a')]);
  assertEqual(applyOp([lot('a')], add(lot('a', { description: 'Altro' }))), [lot('a')]);
});

test('take riduce, e a zero o sotto toglie il lotto', () => {
  assertEqual(applyOp([lot('a')], take('a', 2)), [lot('a', { quantity: 3 })]);
  assertEqual(applyOp([lot('a')], take('a', 5)), []);
  assertEqual(applyOp([lot('a')], take('a', 9)), []);
  assertEqual(applyOp([lot('a')], take('manca', 1)), [lot('a')]);
});

test('aggiungi e poi prendi offline sullo stesso lotto', () => {
  assertEqual(viewLots([], [add(lot('a')), take('a', 2)]), [lot('a', { quantity: 3 })]);
});

test('edit unisce i campi, delete toglie', () => {
  const edited = applyOp([lot('a')], { op_id: 'e', type: 'edit', lot_id: 'a', fields: { quantity: 8 } });
  assertEqual(edited, [lot('a', { quantity: 8 })]);
  assertEqual(applyOp([lot('a')], { op_id: 'd', type: 'delete', lot_id: 'a' }), []);
  assertEqual(applyOp([lot('a')], { op_id: 'e2', type: 'edit', lot_id: 'manca', fields: { quantity: 1 } }), [lot('a')]);
});

test('viewLots non modifica l\'istantanea e ordina per scadenza e descrizione', () => {
  const snapshot = [
    lot('z', { description: 'zucchine', expiry: '2027-01-10' }),
    lot('b', { description: 'Burro', expiry: '2026-12-01' }),
    lot('a', { description: 'Àrista', expiry: '2027-01-10' }),
  ];
  const copy = JSON.parse(JSON.stringify(snapshot));
  const view = viewLots(snapshot, [take('b', 1)]);
  assertEqual(view.map((l) => l.id), ['b', 'a', 'z']);
  assertEqual(view[0].quantity, 4);
  assertEqual(snapshot, copy);
});

test('removeSent toglie solo le operazioni inviate', () => {
  const queue = [take('a', 1, 'op1'), take('a', 1, 'op2'), take('a', 1, 'op3')];
  assertEqual(removeSent(queue, new Set(['op1', 'op3'])).map((op) => op.op_id), ['op2']);
});

test('makeOp aggiunge op_id, tipo e ora', () => {
  const op = makeOp('take', { lot_id: 'a', amount: 2 }, { uuid: () => 'u1', now: () => 'T' });
  assertEqual(op, { op_id: 'u1', type: 'take', at: 'T', lot_id: 'a', amount: 2 });
  assert(typeof makeOp('delete', { lot_id: 'a' }).op_id === 'string', 'uuid di default');
});

test('changedFields restituisce solo i campi cambiati', () => {
  assertEqual(changedFields(lot('a'), { ...lot('a'), quantity: 3, expiry: '2027-02-01' }), {
    quantity: 3, expiry: '2027-02-01',
  });
  assertEqual(changedFields(lot('a'), lot('a')), {});
});
```

- [ ] **Step 3: Verifica che falliscano**

Esegui i test JS come descritto in **Interfaces** (server in background + Chrome headless).
Expected: `data-summary="RUNNING"` (i moduli di `web/` mancano, l'import fallisce e `run()` non parte).

- [ ] **Step 4: Implementa i moduli**

`web/expiry.js`:
```js
// Date come stringhe 'YYYY-MM-DD' nel calendario locale. Stessa regola di freezer/expiry.py.
// Mai new Date('YYYY-MM-DD'): verrebbe letta come UTC e la scadenza potrebbe slittare di un giorno.

const pad = (n) => String(n).padStart(2, '0');

export function todayIso(now = new Date()) {
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
}

function dayNumber(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return Date.UTC(y, m - 1, d) / 86400000;
}

export function daysLeft(expiryIso, today) {
  return dayNumber(expiryIso) - dayNumber(today);
}

export function expiryStatus(expiryIso, today, warnDays) {
  const days = daysLeft(expiryIso, today);
  if (days < 0) return 'expired';
  if (days <= warnDays) return 'expiring';
  return 'ok';
}

export function expiryText(expiryIso, today) {
  const days = daysLeft(expiryIso, today);
  if (days < -1) return `scaduto da ${-days} giorni`;
  if (days === -1) return 'scaduto ieri';
  if (days === 0) return 'oggi';
  if (days === 1) return 'domani';
  return `tra ${days} giorni`;
}

export function countAlerts(lots, today, warnDays) {
  const counts = { expired: 0, expiring: 0 };
  for (const lot of lots) {
    const status = expiryStatus(lot.expiry, today, warnDays);
    if (status !== 'ok') counts[status] += 1;
  }
  return counts;
}

export function formatDayMonth(iso) {
  const [, m, d] = iso.split('-');
  return `${d}/${m}`;
}

export function formatDate(iso) {
  const [y, m, d] = iso.split('-');
  return `${d}/${m}/${y}`;
}

export function addMonths(iso, months) {
  const [y, m, d] = iso.split('-').map(Number);
  const first = new Date(Date.UTC(y, m - 1 + months, 1));
  const year = first.getUTCFullYear();
  const month = first.getUTCMonth();
  const lastDay = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  return `${year}-${pad(month + 1)}-${pad(Math.min(d, lastDay))}`;
}
```

`web/format.js`:
```js
export const MAX_QUANTITY = 99999;

export function formatQuantity(quantity, unitCode, catalog) {
  const unit = catalog?.units?.find((u) => u.code === unitCode);
  if (!unit) return String(quantity);
  return `${quantity} ${quantity === 1 ? unit.singular : unit.plural}`;
}

export function categoryLabel(code, catalog) {
  return catalog?.categories?.find((c) => c.code === code)?.label ?? code;
}

export function normalizeText(text) {
  return String(text).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
}

const HTML_ESCAPES = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };

export function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => HTML_ESCAPES[ch]);
}

// Testo di un campo quantità → intero tra 1 e max, oppure null.
export function parseQuantity(text, max = MAX_QUANTITY) {
  const trimmed = String(text ?? '').trim();
  if (!/^\d+$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return value >= 1 && value <= max ? value : null;
}
```

`web/persist.js`:
```js
// localStorage protetto: in navigazione privata o a memoria piena può lanciare eccezioni.
export function createPersist(storage) {
  return {
    load(key, fallback) {
      try {
        const raw = storage ? storage.getItem(key) : null;
        return raw == null ? fallback : JSON.parse(raw);
      } catch {
        return fallback;
      }
    },
    save(key, value) {
      try {
        if (!storage) return false;
        storage.setItem(key, JSON.stringify(value));
        return true;
      } catch {
        return false;
      }
    },
  };
}

function browserStorage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export const persist = createPersist(browserStorage());
```

`web/store.js`:
```js
// Applicazione locale delle operazioni: stesse regole di freezer/ops.py, sui soli lotti attivi.

const EDITABLE_FIELDS = ['description', 'category', 'quantity', 'unit', 'expiry'];

export function applyOp(lots, op) {
  switch (op.type) {
    case 'add':
      if (lots.some((lot) => lot.id === op.lot.id)) return lots;
      return [...lots, { ...op.lot }];
    case 'take':
      return lots.flatMap((lot) => {
        if (lot.id !== op.lot_id) return [lot];
        const quantity = Math.max(0, lot.quantity - op.amount);
        return quantity > 0 ? [{ ...lot, quantity }] : [];
      });
    case 'edit':
      return lots.map((lot) => (lot.id === op.lot_id ? { ...lot, ...op.fields } : lot));
    case 'delete':
      return lots.filter((lot) => lot.id !== op.lot_id);
    default:
      return lots;
  }
}

export function compareLots(a, b) {
  if (a.expiry !== b.expiry) return a.expiry < b.expiry ? -1 : 1;
  return a.description.localeCompare(b.description, 'it', { sensitivity: 'base' });
}

export function viewLots(lots, queue) {
  return queue.reduce((current, op) => applyOp(current, op), lots).slice().sort(compareLots);
}

export function removeSent(queue, sentIds) {
  return queue.filter((op) => !sentIds.has(op.op_id));
}

export function makeOp(type, payload, { uuid = () => crypto.randomUUID(), now = () => new Date().toISOString() } = {}) {
  return { op_id: uuid(), type, at: now(), ...payload };
}

export function changedFields(original, updated) {
  const fields = {};
  for (const key of EDITABLE_FIELDS) {
    if (updated[key] !== original[key]) fields[key] = updated[key];
  }
  return fields;
}
```

- [ ] **Step 5: Verifica che passino**

Esegui i test JS come descritto in **Interfaces**.
Expected: `data-summary="PASS 25/25"` (il numero deve coincidere con i test definiti; nessun `FAIL`). Ferma il server dei test.

- [ ] **Step 6: Commit**

```bash
git add web/expiry.js web/format.js web/persist.js web/store.js tools/serve_tests.py tests/js
git commit -m "feat: logica client pura (scadenze, formati, coda) con test nel browser"
```

---

### Task 7: Ciclo di sincronizzazione (client)

**Files:**
- Create: `web/sync.js`
- Modify: `tests/js/test.html` (aggiungi l'import di `./sync.test.js`)
- Test: `tests/js/sync.test.js`

**Interfaces:**
- Consumes: `removeSent` (Task 6, solo nei test); API del Task 3 (`GET /api/inventory`, `POST /api/sync`).
- Produces: `web/sync.js`: `MAX_BATCH = 500`; `createSyncer({getQueue, onSuccess, onFailure, fetchImpl?, timeoutMs = 5000}) -> {syncNow(): Promise<void>}`.
  - Coda vuota → `GET /api/inventory`; altrimenti `POST /api/sync` con le prime 500 operazioni.
  - Successo → `onSuccess(snapshot, sentIds: Set<string>)`, e **chi chiama** rimuove le operazioni inviate dalla coda. Se dopo un invio la coda non è vuota, fa subito un altro giro.
  - Errore di rete, HTTP non 2xx o timeout → `onFailure(error)`, la coda non viene toccata.
  - Una sola sincronizzazione alla volta: una chiamata durante un invio in corso fa fare un giro in più alla fine.

- [ ] **Step 1: Scrivi i test che falliscono**

`tests/js/sync.test.js`:
```js
import { test, assert, assertEqual } from './harness.js';
import { removeSent } from '../../web/store.js';
import { createSyncer } from '../../web/sync.js';

const op = (id) => ({ op_id: id, type: 'delete', lot_id: 'x' });
const tick = () => new Promise((resolve) => setTimeout(resolve, 0));
const okResponse = (data = { lots: [] }) => ({ ok: true, status: 200, json: async () => data });

function setup(initialQueue, fetchImpl, timeoutMs = 5000) {
  const state = { queue: initialQueue, successes: [], failures: [] };
  const syncer = createSyncer({
    getQueue: () => state.queue,
    onSuccess: (data, sentIds) => {
      state.successes.push({ data, sentIds });
      state.queue = removeSent(state.queue, sentIds);
    },
    onFailure: (error) => state.failures.push(error),
    fetchImpl,
    timeoutMs,
  });
  return { state, syncer };
}

function recordingFetch(respond = () => okResponse()) {
  const calls = [];
  const fetchImpl = async (url, options = {}) => {
    calls.push({ url, method: options.method ?? 'GET', body: options.body ? JSON.parse(options.body) : null });
    return respond(url, options);
  };
  return { calls, fetchImpl };
}

test('coda vuota: chiede solo l\'istantanea', async () => {
  const { calls, fetchImpl } = recordingFetch(() => okResponse({ lots: ['L'] }));
  const { state, syncer } = setup([], fetchImpl);
  await syncer.syncNow();
  assertEqual(calls.map((c) => `${c.method} ${c.url}`), ['GET /api/inventory']);
  assertEqual(state.successes[0].data, { lots: ['L'] });
  assertEqual(state.successes[0].sentIds.size, 0);
});

test('coda piena: invia le operazioni e le toglie dalla coda', async () => {
  const { calls, fetchImpl } = recordingFetch();
  const { state, syncer } = setup([op('a'), op('b')], fetchImpl);
  await syncer.syncNow();
  assertEqual(calls.map((c) => `${c.method} ${c.url}`), ['POST /api/sync']);
  assertEqual(calls[0].body.ops.map((o) => o.op_id), ['a', 'b']);
  assertEqual(state.queue, []);
  assertEqual(state.failures, []);
});

test('rete assente: la coda resta intatta', async () => {
  const { state, syncer } = setup([op('a')], async () => { throw new TypeError('Failed to fetch'); });
  await syncer.syncNow();
  assertEqual(state.queue.map((o) => o.op_id), ['a']);
  assertEqual(state.successes.length, 0);
  assertEqual(state.failures.length, 1);
});

test('errore HTTP: fallimento, coda intatta', async () => {
  const { state, syncer } = setup([op('a')], async () => ({ ok: false, status: 502, json: async () => ({}) }));
  await syncer.syncNow();
  assertEqual(state.failures[0].message, 'HTTP 502');
  assertEqual(state.queue.length, 1);
});

test('timeout: la richiesta viene annullata', async () => {
  const hanging = (url, { signal }) => new Promise((resolve, reject) => {
    signal.addEventListener('abort', () => reject(new DOMException('Annullata', 'AbortError')));
  });
  const { state, syncer } = setup([op('a')], hanging, 20);
  await syncer.syncNow();
  assertEqual(state.failures.length, 1);
  assertEqual(state.queue.length, 1);
});

test('una sola sincronizzazione alla volta, con un giro in più se richiesto', async () => {
  let inFlight = 0;
  let maxInFlight = 0;
  let count = 0;
  let release = null;
  const fetchImpl = () => {
    count += 1;
    inFlight += 1;
    maxInFlight = Math.max(maxInFlight, inFlight);
    return new Promise((resolve) => {
      release = () => { inFlight -= 1; resolve(okResponse()); };
    });
  };
  const { syncer } = setup([op('a')], fetchImpl);
  const first = syncer.syncNow();
  syncer.syncNow();
  await tick();
  release();
  await tick();
  release();
  await first;
  assertEqual(count, 2);
  assertEqual(maxInFlight, 1);
});

test('coda più lunga di 500: invio a blocchi', async () => {
  const { calls, fetchImpl } = recordingFetch();
  const queue = Array.from({ length: 1200 }, (_, i) => op(`op${i}`));
  const { state, syncer } = setup(queue, fetchImpl);
  await syncer.syncNow();
  assertEqual(calls.map((c) => c.body.ops.length), [500, 500, 200]);
  assertEqual(calls[1].body.ops[0].op_id, 'op500');
  assertEqual(state.queue, []);
});

test('operazione aggiunta durante l\'invio: resta in coda e parte al giro dopo', async () => {
  const bodies = [];
  let release = null;
  const fetchImpl = (url, options) => {
    bodies.push(JSON.parse(options.body));
    return new Promise((resolve) => { release = () => resolve(okResponse()); });
  };
  const { state, syncer } = setup([op('a')], fetchImpl);
  const done = syncer.syncNow();
  state.queue = [...state.queue, op('nuova')];
  release();
  await tick();
  release();
  await done;
  assertEqual(bodies.map((b) => b.ops.map((o) => o.op_id)), [['a'], ['nuova']]);
  assert(state.queue.length === 0, 'coda vuota alla fine');
});
```

In `tests/js/test.html` aggiungi dopo `import './store.test.js';`:
```js
    import './sync.test.js';
```

- [ ] **Step 2: Verifica che falliscano**

Esegui i test JS (comandi nel Task 6, **Interfaces**).
Expected: `data-summary="RUNNING"` (manca `web/sync.js`).

- [ ] **Step 3: Implementa `web/sync.js`**

```js
// Ciclo di sincronizzazione: invia la coda a blocchi, oppure chiede solo l'istantanea.
export const MAX_BATCH = 500;

export function createSyncer({
  getQueue,
  onSuccess,
  onFailure,
  fetchImpl = (...args) => fetch(...args),
  timeoutMs = 5000,
}) {
  let running = false;
  let again = false;

  async function exchange(ops) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const request = ops.length
        ? {
            url: '/api/sync',
            options: {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ ops }),
            },
          }
        : { url: '/api/inventory', options: {} };
      const response = await fetchImpl(request.url, {
        ...request.options,
        cache: 'no-store',
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      onSuccess(await response.json(), new Set(ops.map((op) => op.op_id)));
    } finally {
      clearTimeout(timer);
    }
  }

  async function syncNow() {
    if (running) {
      again = true;
      return;
    }
    running = true;
    try {
      do {
        again = false;
        const ops = getQueue().slice(0, MAX_BATCH);
        await exchange(ops);
        if (ops.length > 0 && getQueue().length > 0) again = true;
      } while (again);
    } catch (error) {
      onFailure(error);
    } finally {
      running = false;
    }
  }

  return { syncNow };
}
```

- [ ] **Step 4: Verifica che passino**

Esegui i test JS.
Expected: `data-summary="PASS 33/33"`.

- [ ] **Step 5: Commit**

```bash
git add web/sync.js tests/js/sync.test.js tests/js/test.html
git commit -m "feat: ciclo di sincronizzazione con coda a blocchi e timeout"
```

---

### Task 8: Interfaccia

**Files:**
- Create: `web/style.css`, `web/app.js`
- Modify: `web/index.html` (sostituisce il segnaposto del Task 3), `web/store.js` (aggiunge `validateLot`)
- Test: `tests/js/store.test.js` (test di `validateLot`); prova end-to-end in Chrome

**Interfaces:**
- Consumes: tutti i moduli dei Task 6–7; API del Task 3.
- Produces: `validateLot({description, category, unit, quantity, expiry}) -> string | null` in `web/store.js`; interfaccia completa della spec §5.1–5.4. Nel Task 9 `app.js` riceve la registrazione del service worker e la variabile `registration` qui dichiarata.

- [ ] **Step 1: Test di `validateLot`**

Aggiungi a `tests/js/store.test.js` (e aggiungi `validateLot` all'import da `../../web/store.js`):
```js
test('validateLot restituisce il primo errore in italiano', () => {
  const ok = { description: 'Ragù', category: 'sughi', unit: 'barattoli_grandi', quantity: 2, expiry: '2027-03-27' };
  assertEqual(validateLot(ok), null);
  assertEqual(validateLot({ ...ok, description: '' }), 'Scrivi una descrizione.');
  assertEqual(validateLot({ ...ok, description: 'x'.repeat(101) }), 'La descrizione può avere al massimo 100 caratteri.');
  assertEqual(validateLot({ ...ok, category: '' }), 'Scegli il tipo.');
  assertEqual(validateLot({ ...ok, unit: '' }), 'Scegli l\'unità.');
  assertEqual(validateLot({ ...ok, quantity: null }), 'La quantità deve essere un numero intero tra 1 e 99999.');
  assertEqual(validateLot({ ...ok, expiry: '' }), 'Scegli la data di scadenza.');
});
```
Esegui i test JS. Expected: FAIL su questo test (`validateLot` non esportata: l'import fallisce e il riepilogo resta `RUNNING`).

- [ ] **Step 2: Implementa `validateLot`**

Aggiungi in fondo a `web/store.js`:
```js
export function validateLot({ description, category, unit, quantity, expiry }) {
  if (!description) return 'Scrivi una descrizione.';
  if (description.length > 100) return 'La descrizione può avere al massimo 100 caratteri.';
  if (!category) return 'Scegli il tipo.';
  if (!unit) return 'Scegli l\'unità.';
  if (quantity === null) return 'La quantità deve essere un numero intero tra 1 e 99999.';
  if (!/^\d{4}-\d{2}-\d{2}$/.test(expiry)) return 'Scegli la data di scadenza.';
  return null;
}
```
Esegui i test JS. Expected: `data-summary="PASS 34/34"`.

- [ ] **Step 3: `web/index.html`**

```html
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
  <meta name="theme-color" content="#0b4f6c">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="Freezer">
  <link rel="stylesheet" href="style.css">
  <title>Freezer</title>
</head>
<body>
  <header class="top">
    <h1 class="top__title">❄️ Freezer</h1>
    <p id="sync-status" class="top__status" role="status" aria-live="polite"></p>
  </header>

  <main class="content">
    <button id="alert-banner" type="button" class="alerts" aria-pressed="false" hidden></button>
    <input id="search" class="search" type="search" placeholder="Cerca…" autocomplete="off" aria-label="Cerca per descrizione">
    <nav id="category-filters" class="chips" aria-label="Filtra per tipo"></nav>
    <ul id="lot-list" class="lots"></ul>
    <p id="empty" class="empty" hidden></p>
  </main>

  <button id="add-button" type="button" class="add">＋ Aggiungi</button>

  <dialog id="take-dialog" class="sheet">
    <form id="take-form" novalidate>
      <h2 id="take-title" class="sheet__title"></h2>
      <p id="take-available" class="sheet__hint"></p>
      <label class="field__label" for="take-amount">Quanti ne prendi?</label>
      <div id="take-stepper" class="stepper">
        <button type="button" class="stepper__btn" data-step="-1" data-target="take-amount" aria-label="Meno">−</button>
        <input id="take-amount" class="stepper__input" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off">
        <button type="button" class="stepper__btn" data-step="1" data-target="take-amount" aria-label="Più">+</button>
      </div>
      <p id="take-error" class="error" role="alert" hidden></p>
      <div class="actions">
        <button type="button" class="btn" data-close>Annulla</button>
        <button type="button" id="take-all" class="btn">Tutto</button>
        <button type="submit" class="btn btn--primary">Prendi</button>
      </div>
    </form>
  </dialog>

  <dialog id="detail-dialog" class="sheet">
    <h2 id="detail-title" class="sheet__title"></h2>
    <dl id="detail-info" class="details"></dl>
    <div class="actions">
      <button type="button" class="btn" data-close>Chiudi</button>
      <button type="button" id="detail-delete" class="btn btn--danger">Elimina</button>
      <button type="button" id="detail-edit" class="btn btn--primary">Modifica</button>
    </div>
  </dialog>

  <dialog id="form-dialog" class="sheet">
    <form id="lot-form" novalidate>
      <h2 id="form-title" class="sheet__title">Aggiungi</h2>
      <label class="field__label" for="f-description">Descrizione</label>
      <input id="f-description" class="field" list="suggestions" maxlength="100" autocomplete="off" autocapitalize="sentences">
      <datalist id="suggestions"></datalist>
      <div class="row">
        <div>
          <label class="field__label" for="f-category">Tipo</label>
          <select id="f-category" class="field"></select>
        </div>
        <div>
          <label class="field__label" for="f-unit">Unità</label>
          <select id="f-unit" class="field"></select>
        </div>
      </div>
      <label class="field__label" for="f-quantity">Quantità</label>
      <div id="f-stepper" class="stepper">
        <button type="button" class="stepper__btn" data-step="-1" data-target="f-quantity" aria-label="Meno">−</button>
        <input id="f-quantity" class="stepper__input" type="text" inputmode="numeric" pattern="[0-9]*" autocomplete="off">
        <button type="button" class="stepper__btn" data-step="1" data-target="f-quantity" aria-label="Più">+</button>
      </div>
      <label class="field__label" for="f-expiry">Scadenza</label>
      <input id="f-expiry" class="field" type="date">
      <div id="quick-expiry" class="quick">
        <button type="button" class="chip" data-months="1">+1 mese</button>
        <button type="button" class="chip" data-months="3">+3 mesi</button>
        <button type="button" class="chip" data-months="6">+6 mesi</button>
      </div>
      <p id="form-error" class="error" role="alert" hidden></p>
      <div class="actions">
        <button type="button" class="btn" data-close>Annulla</button>
        <button type="submit" class="btn btn--primary">Salva</button>
      </div>
    </form>
  </dialog>

  <script type="module" src="app.js"></script>
</body>
</html>
```

- [ ] **Step 4: `web/style.css`**

```css
:root {
  --bg: #f4f7f9;
  --surface: #ffffff;
  --text: #16212b;
  --muted: #5b6b78;
  --border: #d7e0e6;
  --primary: #0b4f6c;
  --primary-text: #ffffff;
  --danger: #b3261e;
  --expired: #c62828;
  --expired-bg: #fdecea;
  --expiring: #e07b00;
  --expiring-bg: #fff3e0;
  --radius: 14px;
  color-scheme: light dark;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #0f171e;
    --surface: #18232d;
    --text: #e8eef2;
    --muted: #9aabb8;
    --border: #2a3a47;
    --primary: #4fb3d9;
    --primary-text: #0b1a22;
    --danger: #ff8a80;
    --expired: #ff6b6b;
    --expired-bg: #3a1d1d;
    --expiring: #ffb74d;
    --expiring-bg: #3a2c16;
  }
}

* { box-sizing: border-box; }
[hidden] { display: none !important; }
html { -webkit-text-size-adjust: 100%; }

body {
  margin: 0;
  font: 17px/1.4 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  background: var(--bg);
  color: var(--text);
  padding-bottom: calc(96px + env(safe-area-inset-bottom));
}

button, input, select { font: inherit; color: inherit; }

.top {
  position: sticky;
  top: 0;
  z-index: 1;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: calc(env(safe-area-inset-top) + 10px) 16px 10px;
}
.top__title { margin: 0; font-size: 22px; }
.top__status { margin: 2px 0 0; min-height: 1.4em; font-size: 14px; color: var(--muted); }

.content { max-width: 640px; margin: 0 auto; padding: 12px 16px; }

.alerts {
  display: block;
  width: 100%;
  margin-bottom: 12px;
  padding: 12px 14px;
  text-align: left;
  font-weight: 600;
  border: 1px solid var(--expiring);
  border-radius: var(--radius);
  background: var(--expiring-bg);
  cursor: pointer;
}
.alerts[aria-pressed="true"] { outline: 3px solid var(--expiring); }

.search {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
}

.chips { display: flex; gap: 8px; overflow-x: auto; padding: 12px 0 4px; }
.chip {
  flex: none;
  padding: 8px 14px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface);
  cursor: pointer;
}
.chip[aria-pressed="true"] { background: var(--primary); border-color: var(--primary); color: var(--primary-text); }

.lots { display: grid; gap: 8px; margin: 8px 0 0; padding: 0; list-style: none; }
.lot {
  display: flex;
  overflow: hidden;
  background: var(--surface);
  border: 1px solid var(--border);
  border-left: 6px solid var(--border);
  border-radius: var(--radius);
}
.lot--expired { border-left-color: var(--expired); background: var(--expired-bg); }
.lot--expiring { border-left-color: var(--expiring); background: var(--expiring-bg); }
.lot__main {
  flex: 1;
  min-width: 0;
  padding: 12px 14px;
  text-align: left;
  background: none;
  border: 0;
  cursor: pointer;
}
.lot__desc { display: block; font-weight: 600; overflow-wrap: anywhere; }
.lot__meta { display: block; margin-top: 2px; font-size: 15px; color: var(--muted); }
.lot--expired .lot__meta { color: var(--expired); }
.lot__take {
  flex: none;
  min-width: 84px;
  border: 0;
  border-left: 1px solid var(--border);
  background: transparent;
  color: var(--primary);
  font-weight: 600;
  cursor: pointer;
}

.empty { padding: 32px 8px; text-align: center; color: var(--muted); }

.add {
  position: fixed;
  right: 16px;
  bottom: calc(16px + env(safe-area-inset-bottom));
  left: 16px;
  max-width: 608px;
  margin: 0 auto;
  padding: 16px;
  border: 0;
  border-radius: 999px;
  background: var(--primary);
  color: var(--primary-text);
  font-size: 18px;
  font-weight: 700;
  box-shadow: 0 6px 20px rgb(0 0 0 / 0.25);
  cursor: pointer;
}
.add:disabled { opacity: 0.5; }

.sheet {
  width: min(100% - 24px, 520px);
  padding: 20px;
  border: 0;
  border-radius: 20px;
  background: var(--surface);
  color: var(--text);
}
.sheet::backdrop { background: rgb(0 0 0 / 0.45); }
.sheet__title { margin: 0 0 4px; font-size: 20px; overflow-wrap: anywhere; }
.sheet__hint { margin: 0 0 12px; color: var(--muted); }

.field__label { display: block; margin: 12px 0 6px; font-size: 15px; color: var(--muted); }
.field {
  width: 100%;
  min-height: 48px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
}
.row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }

.stepper { display: flex; gap: 8px; }
.stepper__btn {
  width: 56px;
  min-height: 48px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
  font-size: 22px;
  cursor: pointer;
}
.stepper__input {
  flex: 1;
  min-width: 0;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg);
  font-size: 20px;
  text-align: center;
}
.stepper.is-grams .stepper__btn { display: none; }

.quick { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.error { margin: 12px 0 0; color: var(--danger); font-weight: 600; }

.actions { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 8px; margin-top: 20px; }
.btn {
  min-height: 48px;
  padding: 0 18px;
  border: 1px solid var(--border);
  border-radius: 12px;
  background: var(--bg);
  cursor: pointer;
}
.btn--primary { background: var(--primary); border-color: var(--primary); color: var(--primary-text); font-weight: 700; }
.btn--danger { border-color: var(--danger); color: var(--danger); }

.details { display: grid; grid-template-columns: auto 1fr; gap: 6px 16px; margin: 12px 0 0; }
.details dt { color: var(--muted); }
.details dd { margin: 0; overflow-wrap: anywhere; }
```

- [ ] **Step 5: `web/app.js`**

```js
import { changedFields, makeOp, removeSent, validateLot, viewLots } from './store.js';
import { createSyncer } from './sync.js';
import {
  addMonths, countAlerts, expiryStatus, expiryText, formatDate, formatDayMonth, todayIso,
} from './expiry.js';
import {
  MAX_QUANTITY, categoryLabel, escapeHtml, formatQuantity, normalizeText, parseQuantity,
} from './format.js';
import { persist } from './persist.js';

const KEYS = { snapshot: 'freezer.snapshot', queue: 'freezer.queue', lastSync: 'freezer.lastSync' };
const RETRY_MS = 30000;

const state = {
  snapshot: persist.load(KEYS.snapshot, null),
  queue: persist.load(KEYS.queue, []),
  lastSync: persist.load(KEYS.lastSync, null),
  failed: false,
  search: '',
  category: 'all',
  onlyAlerts: false,
};
if (!Array.isArray(state.queue)) state.queue = [];
if (!state.snapshot || !Array.isArray(state.snapshot.lots)) state.snapshot = null;

let registration = null; // service worker, impostato nel Task 9
let takeLotId = null;
let detailLotId = null;
let editingLot = null;

const $ = (id) => document.getElementById(id);
const catalog = () => state.snapshot?.catalog ?? { categories: [], units: [] };
const warnDays = () => state.snapshot?.warn_days ?? 7;
const currentLots = () => viewLots(state.snapshot?.lots ?? [], state.queue);
const findLot = (id) => currentLots().find((lot) => lot.id === id);
const pad = (n) => String(n).padStart(2, '0');

// ---- Rendering -----------------------------------------------------------

function stamp(iso) {
  const d = new Date(iso);
  return { day: `${pad(d.getDate())}/${pad(d.getMonth() + 1)}`, time: `${pad(d.getHours())}:${pad(d.getMinutes())}` };
}

function syncStatusText() {
  const pending = state.queue.length;
  if (pending) {
    const text = pending === 1 ? '⏳ 1 modifica da inviare' : `⏳ ${pending} modifiche da inviare`;
    return state.failed ? `${text} · PC non raggiungibile` : text;
  }
  if (state.failed) {
    if (!state.lastSync) return '⚠ PC non raggiungibile';
    const { day, time } = stamp(state.lastSync);
    return `⚠ PC non raggiungibile · dati del ${day} ${time}`;
  }
  if (state.lastSync) return `✓ Aggiornato alle ${stamp(state.lastSync).time}`;
  return 'Connessione al PC…';
}

function renderBanner(lots, today) {
  const banner = $('alert-banner');
  const { expired, expiring } = countAlerts(lots, today, warnDays());
  if (!expired && !expiring) {
    banner.hidden = true;
    state.onlyAlerts = false;
    return;
  }
  const parts = [];
  if (expired) parts.push(`🔴 ${expired} ${expired === 1 ? 'scaduto' : 'scaduti'}`);
  if (expiring) parts.push(`🟠 ${expiring} in scadenza`);
  banner.hidden = false;
  banner.textContent = parts.join(' · ') + (state.onlyAlerts ? ' — mostra tutto' : '');
  banner.setAttribute('aria-pressed', String(state.onlyAlerts));
}

function renderChips(lots) {
  const present = new Set(lots.map((lot) => lot.category));
  if (state.category !== 'all' && !present.has(state.category)) state.category = 'all';
  const chips = [{ code: 'all', label: 'Tutti' }, ...catalog().categories.filter((c) => present.has(c.code))];
  const nav = $('category-filters');
  nav.hidden = present.size < 2;
  nav.innerHTML = chips
    .map((chip) => `<button type="button" class="chip" data-category="${escapeHtml(chip.code)}" aria-pressed="${chip.code === state.category}">${escapeHtml(chip.label)}</button>`)
    .join('');
}

function lotItem(lot, today) {
  const status = expiryStatus(lot.expiry, today, warnDays());
  const id = escapeHtml(lot.id);
  const meta = [
    formatQuantity(lot.quantity, lot.unit, catalog()),
    expiryText(lot.expiry, today),
    formatDayMonth(lot.expiry),
  ].map(escapeHtml).join(' · ');
  return `<li class="lot lot--${status}">
    <button type="button" class="lot__main" data-action="open" data-id="${id}">
      <span class="lot__desc">${escapeHtml(lot.description)}</span>
      <span class="lot__meta">${meta}</span>
    </button>
    <button type="button" class="lot__take" data-action="take" data-id="${id}">Prendi</button>
  </li>`;
}

function renderList(lots, today) {
  const query = normalizeText(state.search);
  const visible = lots.filter((lot) =>
    (state.category === 'all' || lot.category === state.category)
    && (!state.onlyAlerts || expiryStatus(lot.expiry, today, warnDays()) !== 'ok')
    && (!query || normalizeText(lot.description).includes(query)));
  $('lot-list').innerHTML = visible.map((lot) => lotItem(lot, today)).join('');
  const empty = $('empty');
  empty.hidden = visible.length > 0;
  if (!state.snapshot) empty.textContent = 'Connettiti al Wi-Fi di casa per caricare l\'inventario.';
  else if (!lots.length) empty.textContent = 'Il freezer è vuoto. Tocca «＋ Aggiungi» per registrare qualcosa.';
  else empty.textContent = 'Nessun risultato.';
}

function render() {
  const today = todayIso();
  const lots = currentLots();
  $('sync-status').textContent = syncStatusText();
  $('add-button').disabled = !state.snapshot;
  renderBanner(lots, today);
  renderChips(lots);
  renderList(lots, today);
}

// ---- Coda e sincronizzazione ---------------------------------------------

const syncer = createSyncer({
  getQueue: () => state.queue,
  onSuccess(snapshot, sentIds) {
    state.snapshot = snapshot;
    state.queue = removeSent(state.queue, sentIds);
    state.lastSync = new Date().toISOString();
    state.failed = false;
    persist.save(KEYS.snapshot, state.snapshot);
    persist.save(KEYS.queue, state.queue);
    persist.save(KEYS.lastSync, state.lastSync);
    render();
    registration?.update().catch(() => {});
  },
  onFailure() {
    state.failed = true;
    render();
  },
});

function enqueue(op) {
  state.queue = [...state.queue, op];
  persist.save(KEYS.queue, state.queue);
  render();
  syncer.syncNow();
}

// ---- Dialoghi --------------------------------------------------------------

function showError(id, message) {
  $(id).textContent = message;
  $(id).hidden = false;
}

function hideError(id) {
  $(id).hidden = true;
}

function openTake(id) {
  const lot = findLot(id);
  if (!lot) return;
  takeLotId = id;
  const grams = lot.unit === 'grammi';
  $('take-title').textContent = lot.description;
  $('take-available').textContent = `Disponibili: ${formatQuantity(lot.quantity, lot.unit, catalog())}`;
  $('take-amount').value = grams ? '' : '1';
  $('take-amount').dataset.max = String(lot.quantity);
  $('take-stepper').classList.toggle('is-grams', grams);
  hideError('take-error');
  $('take-dialog').showModal();
  if (grams) $('take-amount').focus();
}

function resetDeleteButton() {
  const button = $('detail-delete');
  delete button.dataset.confirm;
  button.textContent = 'Elimina';
}

function openDetail(id) {
  const lot = findLot(id);
  if (!lot) return;
  detailLotId = id;
  $('detail-title').textContent = lot.description;
  $('detail-info').innerHTML = `
    <dt>Tipo</dt><dd>${escapeHtml(categoryLabel(lot.category, catalog()))}</dd>
    <dt>Quantità</dt><dd>${escapeHtml(formatQuantity(lot.quantity, lot.unit, catalog()))}</dd>
    <dt>Scadenza</dt><dd>${escapeHtml(formatDate(lot.expiry))} (${escapeHtml(expiryText(lot.expiry, todayIso()))})</dd>`;
  resetDeleteButton();
  $('detail-dialog').showModal();
}

function fillSelect(select, options, placeholder) {
  select.innerHTML = `<option value="">${escapeHtml(placeholder)}</option>`
    + options.map((o) => `<option value="${escapeHtml(o.code)}">${escapeHtml(o.label)}</option>`).join('');
}

function updateQuantityMode() {
  $('f-stepper').classList.toggle('is-grams', $('f-unit').value === 'grammi');
}

function openForm(lot = null) {
  editingLot = lot;
  const { categories, units } = catalog();
  $('form-title').textContent = lot ? 'Modifica' : 'Aggiungi';
  fillSelect($('f-category'), categories, 'Scegli il tipo…');
  fillSelect($('f-unit'), units.map((u) => ({ code: u.code, label: u.plural })), 'Scegli l\'unità…');
  $('suggestions').innerHTML = (state.snapshot?.suggestions ?? [])
    .map((s) => `<option value="${escapeHtml(s.description)}"></option>`).join('');
  $('f-description').value = lot?.description ?? '';
  $('f-category').value = lot?.category ?? '';
  $('f-unit').value = lot?.unit ?? '';
  $('f-quantity').value = lot ? String(lot.quantity) : '1';
  $('f-quantity').dataset.max = String(MAX_QUANTITY);
  $('f-expiry').value = lot?.expiry ?? '';
  updateQuantityMode();
  hideError('form-error');
  $('form-dialog').showModal();
}

// ---- Eventi ----------------------------------------------------------------

$('lot-list').addEventListener('click', (event) => {
  const button = event.target.closest('button[data-action]');
  if (!button) return;
  if (button.dataset.action === 'take') openTake(button.dataset.id);
  else openDetail(button.dataset.id);
});

$('category-filters').addEventListener('click', (event) => {
  const chip = event.target.closest('[data-category]');
  if (!chip) return;
  state.category = chip.dataset.category;
  render();
});

$('alert-banner').addEventListener('click', () => {
  state.onlyAlerts = !state.onlyAlerts;
  render();
});

$('search').addEventListener('input', (event) => {
  state.search = event.target.value;
  render();
});

$('add-button').addEventListener('click', () => openForm());

document.querySelectorAll('[data-close]').forEach((button) => {
  button.addEventListener('click', () => button.closest('dialog').close());
});

document.addEventListener('click', (event) => {
  const button = event.target.closest('[data-step]');
  if (!button) return;
  const input = $(button.dataset.target);
  const max = Number(input.dataset.max) || MAX_QUANTITY;
  const current = parseQuantity(input.value, MAX_QUANTITY) ?? 0;
  input.value = String(Math.min(max, Math.max(1, current + Number(button.dataset.step))));
});

$('take-all').addEventListener('click', () => {
  const lot = findLot(takeLotId);
  if (lot) $('take-amount').value = String(lot.quantity);
});

$('take-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const lot = findLot(takeLotId);
  if (!lot) {
    $('take-dialog').close();
    return;
  }
  const amount = parseQuantity($('take-amount').value, lot.quantity);
  if (amount === null) {
    showError('take-error', `Scrivi un numero intero tra 1 e ${lot.quantity}.`);
    return;
  }
  $('take-dialog').close();
  enqueue(makeOp('take', { lot_id: lot.id, amount }));
});

$('detail-edit').addEventListener('click', () => {
  const lot = findLot(detailLotId);
  $('detail-dialog').close();
  if (lot) openForm(lot);
});

$('detail-delete').addEventListener('click', () => {
  const button = $('detail-delete');
  if (button.dataset.confirm !== 'yes') {
    button.dataset.confirm = 'yes';
    button.textContent = 'Conferma eliminazione';
    return;
  }
  $('detail-dialog').close();
  if (findLot(detailLotId)) enqueue(makeOp('delete', { lot_id: detailLotId }));
});

$('f-description').addEventListener('input', () => {
  if (editingLot) return;
  const key = normalizeText($('f-description').value);
  const match = (state.snapshot?.suggestions ?? []).find((s) => normalizeText(s.description) === key);
  if (!match) return;
  $('f-category').value = match.category;
  $('f-unit').value = match.unit;
  updateQuantityMode();
});

$('f-unit').addEventListener('change', updateQuantityMode);

$('quick-expiry').addEventListener('click', (event) => {
  const button = event.target.closest('[data-months]');
  if (button) $('f-expiry').value = addMonths(todayIso(), Number(button.dataset.months));
});

$('lot-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const values = {
    description: $('f-description').value.trim(),
    category: $('f-category').value,
    unit: $('f-unit').value,
    quantity: parseQuantity($('f-quantity').value),
    expiry: $('f-expiry').value,
  };
  const error = validateLot(values);
  if (error) {
    showError('form-error', error);
    return;
  }
  $('form-dialog').close();
  if (!editingLot) {
    enqueue(makeOp('add', { lot: { id: crypto.randomUUID(), ...values } }));
    return;
  }
  const current = findLot(editingLot.id);
  if (!current) return;
  const fields = changedFields(current, values);
  if (Object.keys(fields).length) enqueue(makeOp('edit', { lot_id: current.id, fields }));
});

// ---- Avvio -----------------------------------------------------------------

window.addEventListener('online', () => syncer.syncNow());
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState !== 'visible') return;
  render(); // "oggi"/"domani" possono essere cambiati mentre l'app era in background
  syncer.syncNow();
});
setInterval(() => {
  if (state.queue.length) syncer.syncNow();
}, RETRY_MS);

render();
syncer.syncNow();
```

- [ ] **Step 6: Prova di caricamento senza errori (headless)**

Avvia il server in background con un database di prova:
`FREEZER_DB_PATH="$TEMP/freezer-e2e.db" .venv/Scripts/python -m uvicorn --factory freezer.api:create_app --host 127.0.0.1 --port 8765`

Run: `"/c/Program Files/Google/Chrome/Application/chrome.exe" --headless=new --disable-gpu --no-first-run --user-data-dir="$TEMP/freezer-chrome-test" --virtual-time-budget=10000 --dump-dom http://127.0.0.1:8765/ 2>/dev/null | grep -o 'id="sync-status"[^<]*<'`
Expected: contiene `✓ Aggiornato alle`. Se contiene `Connessione al PC…`, `app.js` non è partito: aprilo in Chrome e leggi la console.

- [ ] **Step 7: Prova end-to-end in Chrome**

Con il server del passo 6 acceso, apri `http://127.0.0.1:8765/` in Chrome (strumenti claude-in-chrome o a mano), a finestra stretta (~400 px), e verifica **tutto** questo:
1. Inventario vuoto: messaggio "Il freezer è vuoto…" e stato `✓ Aggiornato alle hh:mm`.
2. **Aggiungi** con descrizione `Pollo <arrosto> & "patate"`, tipo Carne, unità buste, quantità 3, `+3 mesi`: compare nella lista con il testo esatto, senza HTML interpretato.
3. Aggiungi `Ragù` (Sughi, barattoli grandi, 2) con scadenza di domani: compare **per primo**, con fondo arancione, e la fascia mostra `🟠 1 in scadenza`. Tocca la fascia: resta solo il ragù. Toccala di nuovo: torna tutto.
4. Aggiungi di nuovo: scrivi `rag` e scegli `Ragù` dal suggerimento; tipo e unità si compilano da soli. Annulla.
5. Nel modulo, quantità `1,5` → errore "La quantità deve essere un numero intero tra 1 e 99999."; senza scadenza → "Scegli la data di scadenza.".
6. **Prendi** 1 dal pollo → 2 buste. Prendi → **Tutto** → Prendi: il pollo sparisce.
7. Tocca il ragù → **Modifica** → quantità 5 → Salva: mostra 5 barattoli grandi.
8. Tocca il ragù → **Elimina** (il testo diventa "Conferma eliminazione") → tocca ancora: sparisce.
9. Ricerca: aggiungi `Pàsta` e cerca `pasta` → trovata. Filtri per tipo: visibili solo con almeno 2 tipi presenti.
10. **Offline:** ferma il server. Prendi 1 da un lotto: la lista si aggiorna subito e lo stato mostra `⏳ 1 modifica da inviare · PC non raggiungibile`. Con lo strumento JavaScript controlla che `localStorage.getItem('freezer.queue')` contenga l'operazione. *(Non ricaricare: senza service worker la pagina offline non si apre; la ricarica offline si verifica nel Task 9.)* Riaccendi il server e aspetta al massimo 30 s: stato `✓ Aggiornato alle …`, e `curl -s http://127.0.0.1:8765/api/inventory` conferma la quantità.
11. **Due telefoni:** apri anche `http://localhost:8765/` (origine diversa = memoria separata, come un secondo telefono). Ferma il server; prendi 1 dallo stesso lotto (quantità 5) in entrambe le schede; riaccendi. Dopo la sincronizzazione di entrambe la quantità è 3 in tutte e due (ricarica per vedere l'ultima istantanea).

Ferma il server e cancella il database di prova.

- [ ] **Step 8: Commit**

```bash
git add web/index.html web/style.css web/app.js web/store.js tests/js/store.test.js
git commit -m "feat: interfaccia per iPhone (inventario, prendi, aggiungi, modifica, elimina)"
```

---

### Task 9: PWA offline — service worker, manifest, icone

**Files:**
- Create: `web/sw.js`, `web/manifest.webmanifest`, `tools/make_icons.py`, `web/icons/icon-180.png`, `web/icons/icon-192.png`, `web/icons/icon-512.png` (generate)
- Modify: `freezer/api.py` (route `/sw.js` versionata), `web/index.html` (link a manifest e icone), `web/app.js` (registrazione del service worker)
- Test: `tests/test_pwa.py`; prova offline in Chrome

**Interfaces:**
- Consumes: `create_app(config, web_dir)` e `WEB_DIR` (Task 3); `registration` e `render`/`syncer` in `web/app.js` (Task 8).
- Produces: `GET /sw.js` con `__VERSION__` sostituito dall'impronta (12 caratteri esadecimali) dei file di `web/` escluso `sw.js`, `Content-Type: text/javascript`, `Cache-Control: no-cache`. Il service worker mette in cache i file dell'elenco `ASSETS` e non tocca mai `/api/*`.

- [ ] **Step 1: Scrivi i test che falliscono**

`tests/test_pwa.py`:
```python
import json
import re
import struct

import pytest
from fastapi.testclient import TestClient

from freezer.api import WEB_DIR, create_app
from freezer.config import load_config


@pytest.fixture
def web(tmp_path):
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<h1>Freezer</h1>", encoding="utf-8")
    (web / "sw.js").write_text("const CACHE = 'freezer-__VERSION__';", encoding="utf-8")
    return web


def make_client(tmp_path, web):
    cfg = load_config({"FREEZER_DB_PATH": str(tmp_path / "pwa.db")})
    return TestClient(create_app(cfg, web_dir=web))


def sw_version(client):
    return re.search(r"freezer-([0-9a-f]{12})", client.get("/sw.js").text).group(1)


def test_sw_is_served_with_version(tmp_path, web):
    with make_client(tmp_path, web) as client:
        response = client.get("/sw.js")
    assert response.status_code == 200
    assert re.fullmatch(r"const CACHE = 'freezer-[0-9a-f]{12}';", response.text)
    assert response.headers["content-type"].startswith("text/javascript")
    assert response.headers["cache-control"] == "no-cache"


def test_version_changes_when_a_web_file_changes(tmp_path, web):
    with make_client(tmp_path, web) as client:
        before = sw_version(client)
    (web / "index.html").write_text("<h1>Freezer 2</h1>", encoding="utf-8")
    with make_client(tmp_path, web) as client:
        after = sw_version(client)
    assert before != after


def test_real_sw_precaches_every_asset():
    source = (WEB_DIR / "sw.js").read_text(encoding="utf-8")
    array = re.search(r"const ASSETS = \[(.*?)\];", source, re.S).group(1)
    assets = re.findall(r"'([^']+)'", array)
    for asset in assets:
        if asset != "./":
            assert (WEB_DIR / asset).is_file(), asset
    served = {
        p.name for p in WEB_DIR.iterdir()
        if p.suffix in {".js", ".css", ".html", ".webmanifest"} and p.name != "sw.js"
    }
    assert served <= set(assets), served - set(assets)


def test_manifest():
    manifest = json.loads((WEB_DIR / "manifest.webmanifest").read_text(encoding="utf-8"))
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == "/"
    assert manifest["lang"] == "it"
    for icon in manifest["icons"]:
        assert (WEB_DIR / icon["src"]).is_file(), icon["src"]


@pytest.mark.parametrize("size", [180, 192, 512])
def test_icons_are_pngs_of_the_right_size(size):
    data = (WEB_DIR / "icons" / f"icon-{size}.png").read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", data[16:24]) == (size, size)
```

- [ ] **Step 2: Verifica che falliscano**

Run: `.venv/Scripts/python -m pytest tests/test_pwa.py -q`
Expected: FAIL (`/sw.js` restituisce 404; `web/sw.js`, manifest e icone non esistono).

- [ ] **Step 3: Route `/sw.js` in `freezer/api.py`**

Aggiungi `import hashlib` e `from fastapi.responses import JSONResponse, Response` agli import. Poi aggiungi questa funzione prima di `create_app`:
```python
def _assets_version(web_dir: Path) -> str:
    """Impronta dei file dell'interfaccia: cambia a ogni modifica, e con lei la cache del service worker."""
    digest = hashlib.sha256()
    for path in sorted(p for p in web_dir.rglob("*") if p.is_file() and p.name != "sw.js"):
        digest.update(path.relative_to(web_dir).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()[:12]
```
In `create_app`, subito prima di `app.mount(...)`:
```python
    sw_path = web_dir / "sw.js"
    if sw_path.is_file():
        sw_source = sw_path.read_text(encoding="utf-8").replace("__VERSION__", _assets_version(web_dir))

        @app.get("/sw.js", include_in_schema=False)
        def service_worker() -> Response:
            return Response(sw_source, media_type="text/javascript", headers={"Cache-Control": "no-cache"})
```

- [ ] **Step 4: `web/sw.js` e `web/manifest.webmanifest`**

`web/sw.js`:
```js
// Service worker: interfaccia disponibile anche senza rete.
// Il server sostituisce __VERSION__ con l'impronta dei file di web/: ogni modifica crea una cache nuova.
const CACHE = 'freezer-__VERSION__';
const ASSETS = [
  './',
  'index.html',
  'style.css',
  'app.js',
  'store.js',
  'sync.js',
  'expiry.js',
  'format.js',
  'persist.js',
  'manifest.webmanifest',
  'icons/icon-180.png',
  'icons/icon-192.png',
  'icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      .then((cache) => cache.addAll(ASSETS.map((url) => new Request(url, { cache: 'reload' }))))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((key) => key !== CACHE).map((key) => caches.delete(key))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) {
    return; // l'API va sempre in rete
  }
  event.respondWith(
    caches.match(event.request, { ignoreSearch: true }).then((cached) => cached || fetch(event.request)),
  );
});
```

`web/manifest.webmanifest`:
```json
{
  "name": "Freezer di cantina",
  "short_name": "Freezer",
  "lang": "it",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "background_color": "#f4f7f9",
  "theme_color": "#0b4f6c",
  "icons": [
    { "src": "icons/icon-192.png", "sizes": "192x192", "type": "image/png" },
    { "src": "icons/icon-512.png", "sizes": "512x512", "type": "image/png" }
  ]
}
```

- [ ] **Step 5: Icone**

`tools/make_icons.py`:
```python
"""Genera le icone PNG dell'app (fiocco di neve bianco su blu). Solo libreria standard."""

import math
import struct
import zlib
from pathlib import Path

BACKGROUND = (0x0B, 0x4F, 0x6C)
FOREGROUND = (0xFF, 0xFF, 0xFF)
SIZES = (180, 192, 512)
OUT_DIR = Path(__file__).resolve().parent.parent / "web" / "icons"


def _segments(size: int) -> list[tuple[float, float, float, float]]:
    center = size / 2
    arm = size * 0.36
    branch = size * 0.13
    segments = []
    for k in range(6):
        angle = math.pi / 3 * k
        dx, dy = math.cos(angle), math.sin(angle)
        segments.append((center, center, center + dx * arm, center + dy * arm))
        bx, by = center + dx * arm * 0.6, center + dy * arm * 0.6
        for side in (-1, 1):
            a = angle + side * math.pi / 4
            segments.append((bx, by, bx + math.cos(a) * branch, by + math.sin(a) * branch))
    return segments


def _distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
    vx, vy = x2 - x1, y2 - y1
    t = max(0.0, min(1.0, ((px - x1) * vx + (py - y1) * vy) / (vx * vx + vy * vy)))
    return math.hypot(px - (x1 + t * vx), py - (y1 + t * vy))


def render(size: int) -> bytes:
    half_width = size * 0.03
    segments = _segments(size)
    rows = []
    for y in range(size):
        row = bytearray([0])  # filtro PNG "None"
        for x in range(size):
            d = min(_distance(x + 0.5, y + 0.5, *segment) for segment in segments)
            coverage = max(0.0, min(1.0, half_width + 0.5 - d))
            row.extend(round(b + (f - b) * coverage) for b, f in zip(BACKGROUND, FOREGROUND))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int, raw: bytes) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    header = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8 bit, RGB
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", header) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


if __name__ == "__main__":
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        (OUT_DIR / f"icon-{size}.png").write_bytes(png(size, render(size)))
        print(f"web/icons/icon-{size}.png")
```

Run: `.venv/Scripts/python tools/make_icons.py`
Expected: stampa i tre file. Apri `web/icons/icon-512.png` con lo strumento Read per controllare a occhio il fiocco bianco su blu.

- [ ] **Step 6: Collega manifest, icone e service worker**

In `web/index.html`, subito dopo `<link rel="stylesheet" href="style.css">`:
```html
  <link rel="manifest" href="manifest.webmanifest">
  <link rel="apple-touch-icon" href="icons/icon-180.png">
  <link rel="icon" type="image/png" href="icons/icon-192.png">
```

In `web/app.js` sostituisci la riga `let registration = null; // service worker, impostato nel Task 9` con:
```js
let registration = null; // service worker: dopo ogni sync controlla se c'è una versione nuova
```
e aggiungi in fondo al file, dopo `syncer.syncNow();`:
```js
async function registerServiceWorker() {
  if (!('serviceWorker' in navigator)) return;
  const hadController = Boolean(navigator.serviceWorker.controller);
  navigator.serviceWorker.addEventListener('controllerchange', () => {
    if (hadController) window.location.reload(); // nuova versione installata
  });
  try {
    registration = await navigator.serviceWorker.register('sw.js');
  } catch {
    // Senza HTTPS non c'è modalità offline, ma l'app funziona lo stesso.
  }
}

registerServiceWorker();
```

- [ ] **Step 7: Verifica che i test passino**

Run: `.venv/Scripts/python -m pytest -q`
Expected: tutti PASS. Esegui anche i test JS: `data-summary="PASS 34/34"`.

- [ ] **Step 8: Prova offline in Chrome**

1. Avvia il server (comando del Task 8, passo 6) e apri `http://127.0.0.1:8765/` in Chrome. Ricarica una volta. Con lo strumento JavaScript verifica che `navigator.serviceWorker.controller` non sia `null` e che `await caches.keys()` restituisca `['freezer-<12 caratteri>']`.
2. Aggiungi un lotto. **Ferma il server** e ricarica la pagina: l'app si apre lo stesso, mostra il lotto e lo stato `⚠ PC non raggiungibile · dati del …`.
3. Offline, prendi 1: stato `⏳ 1 modifica da inviare · PC non raggiungibile`. Riaccendi il server: entro 30 s lo stato torna `✓ Aggiornato alle …`.
4. Aggiornamento: aggiungi una riga di commento in fondo a `web/style.css`, riavvia il server e riporta in primo piano la pagina (o ricaricala). La pagina si ricarica da sola e `caches.keys()` mostra una sola cache con un nome nuovo. Togli il commento.

Ferma il server e cancella il database di prova.

- [ ] **Step 9: Commit**

```bash
git add freezer/api.py web/sw.js web/manifest.webmanifest web/icons web/index.html web/app.js tools/make_icons.py tests/test_pwa.py
git commit -m "feat: PWA offline con service worker versionato, manifest e icone"
```

---

### Task 10: Installazione sul PC Linux

**Files:**
- Create: `deploy/install.sh`, `deploy/Caddyfile.template`, `deploy/cert.html`, `deploy/freezer.env.example`
- Create: `deploy/systemd/freezer.service`, `deploy/systemd/freezer-notify.service`, `deploy/systemd/freezer-notify.timer`, `deploy/systemd/freezer-backup.service`, `deploy/systemd/freezer-backup.timer`
- Test: `tests/test_deploy.py`

**Interfaces:**
- Consumes: `uvicorn --factory freezer.api:create_app` (Task 3), `python -m freezer.notify` (Task 4), `python -m freezer.backup` (Task 5), variabili di `load_config` (Task 1).
- Produces: `sudo ./deploy/install.sh [--host NOME.local] [--https-port N] [--http-port N] [--notify-time HH:MM]`, idempotente. Segnaposto sostituiti dallo script: `__HOST__`, `__HTTPS_PORT__`, `__HTTP_PORT__`, `__APP_PORT__`, `__HTTPS_SUFFIX__` (Caddyfile), `__APP_URL__` (cert.html), `__NOTIFY_TIME__` (timer).

- [ ] **Step 1: Scrivi i test che falliscono**

`tests/test_deploy.py`:
```python
import re
from pathlib import Path

from freezer.config import load_config

DEPLOY = Path(__file__).resolve().parent.parent / "deploy"


def read(name: str) -> str:
    return (DEPLOY / name).read_text(encoding="utf-8")


def test_install_script_fills_every_placeholder():
    install = read("install.sh")
    for name in ["Caddyfile.template", "cert.html", "systemd/freezer-notify.timer"]:
        for placeholder in set(re.findall(r"__[A-Z_]+__", read(name))):
            assert f"s|{placeholder}|" in install, (name, placeholder)


def test_install_script_is_a_unix_bash_script():
    raw = (DEPLOY / "install.sh").read_bytes()
    assert raw.startswith(b"#!/usr/bin/env bash\n")
    assert b"\r\n" not in raw


def test_env_example_is_a_valid_config():
    env = {}
    for line in read("freezer.env.example").splitlines():
        if line and not line.startswith("#"):
            key, _, value = line.partition("=")
            env[key] = value
    cfg = load_config(env)
    assert cfg.port == 8765
    assert cfg.db_path == "/var/lib/freezer/freezer.db"
    assert cfg.backup_keep == 14


def test_units_run_as_freezer_with_env_file():
    for unit in ["freezer.service", "freezer-notify.service", "freezer-backup.service"]:
        text = read(f"systemd/{unit}")
        assert "User=freezer" in text
        assert "EnvironmentFile=/etc/freezer/freezer.env" in text
        assert "WorkingDirectory=/opt/freezer" in text
    service = read("systemd/freezer.service")
    assert "--host 127.0.0.1" in service
    assert "--port ${FREEZER_PORT}" in service


def test_caddy_serves_only_the_root_certificate():
    caddyfile = read("Caddyfile.template")
    assert caddyfile.startswith("# freezer")
    assert "rewrite * /root.crt" in caddyfile
    assert "tls internal" in caddyfile
    assert "reverse_proxy 127.0.0.1:__APP_PORT__" in caddyfile
```

Run: `.venv/Scripts/python -m pytest tests/test_deploy.py -q`
Expected: FAIL con `FileNotFoundError` (la cartella `deploy/` non esiste).

- [ ] **Step 2: Configurazione e unità systemd**

`deploy/freezer.env.example`:
```
# Configurazione di Freezer. Dopo una modifica: sudo systemctl restart freezer
FREEZER_DB_PATH=/var/lib/freezer/freezer.db
FREEZER_PORT=8765
FREEZER_WARN_DAYS=7
FREEZER_TZ=Europe/Rome
FREEZER_BACKUP_DIR=/var/lib/freezer/backups
FREEZER_BACKUP_KEEP=14
# Telegram: token dato da @BotFather e id del gruppo di famiglia (vedi README)
TELEGRAM_BOT_TOKEN=
TELEGRAM_CHAT_ID=
```

`deploy/systemd/freezer.service`:
```ini
[Unit]
Description=Freezer di cantina (webapp)
After=network.target

[Service]
Type=simple
User=freezer
Group=freezer
EnvironmentFile=/etc/freezer/freezer.env
WorkingDirectory=/opt/freezer
ExecStart=/opt/freezer/.venv/bin/uvicorn --factory freezer.api:create_app --host 127.0.0.1 --port ${FREEZER_PORT}
Restart=on-failure
RestartSec=5
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/freezer

[Install]
WantedBy=multi-user.target
```

`deploy/systemd/freezer-notify.service`:
```ini
[Unit]
Description=Freezer: avviso scadenze su Telegram
Wants=network-online.target
After=network-online.target

[Service]
Type=oneshot
User=freezer
Group=freezer
EnvironmentFile=/etc/freezer/freezer.env
WorkingDirectory=/opt/freezer
ExecStart=/opt/freezer/.venv/bin/python -m freezer.notify
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/freezer
```

`deploy/systemd/freezer-notify.timer`:
```ini
[Unit]
Description=Freezer: avviso scadenze ogni mattina

[Timer]
OnCalendar=*-*-* __NOTIFY_TIME__:00
Persistent=true

[Install]
WantedBy=timers.target
```

`deploy/systemd/freezer-backup.service`:
```ini
[Unit]
Description=Freezer: backup del database

[Service]
Type=oneshot
User=freezer
Group=freezer
EnvironmentFile=/etc/freezer/freezer.env
WorkingDirectory=/opt/freezer
ExecStart=/opt/freezer/.venv/bin/python -m freezer.backup
NoNewPrivileges=yes
PrivateTmp=yes
ProtectHome=yes
ProtectSystem=strict
ReadWritePaths=/var/lib/freezer
```

`deploy/systemd/freezer-backup.timer`:
```ini
[Unit]
Description=Freezer: backup notturno

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

- [ ] **Step 3: Caddy e pagina del certificato**

`deploy/Caddyfile.template`:
```
# freezer: generato da deploy/install.sh, le modifiche fatte qui verranno sovrascritte.
{
	skip_install_trust
	auto_https disable_redirects
	pki {
		ca local {
			name "Freezer di casa"
			root_cn "Freezer di casa"
		}
	}
}

https://__HOST__:__HTTPS_PORT__ {
	tls internal
	encode gzip
	reverse_proxy 127.0.0.1:__APP_PORT__
}

http://__HOST__:__HTTP_PORT__ {
	@certfile path /cert/root.crt
	handle @certfile {
		root * /var/lib/caddy/.local/share/caddy/pki/authorities/local
		rewrite * /root.crt
		header Content-Type application/x-x509-ca-cert
		file_server
	}

	@certpage path /cert /cert/
	handle @certpage {
		root * /etc/caddy
		rewrite * /freezer-cert.html
		file_server
	}

	handle {
		redir https://{host}__HTTPS_SUFFIX__{uri}
	}
}
```

`deploy/cert.html`:
```html
<!doctype html>
<html lang="it">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Freezer · prima installazione</title>
  <style>
    body { max-width: 560px; margin: 0 auto; padding: 16px; font: 17px/1.5 -apple-system, sans-serif; color: #16212b; background: #f4f7f9; }
    h1 { font-size: 24px; }
    ol { padding-left: 1.2em; }
    li { margin-bottom: 12px; }
    .btn { display: block; margin: 16px 0; padding: 16px; border-radius: 999px; background: #0b4f6c; color: #fff; font-weight: 700; text-align: center; text-decoration: none; }
  </style>
</head>
<body>
  <h1>❄️ Freezer: prima installazione</h1>
  <p>Da fare <b>una volta sola</b> su ogni iPhone, collegato al Wi-Fi di casa, usando <b>Safari</b>.</p>

  <h2>1. Certificato</h2>
  <a class="btn" href="/cert/root.crt">Scarica il certificato</a>
  <ol>
    <li>Tocca il pulsante qui sopra e poi <b>Consenti</b>.</li>
    <li>Apri <b>Impostazioni</b>: in alto compare <b>Profilo scaricato</b> (oppure in Generali → VPN e gestione dispositivi). Toccalo, poi <b>Installa</b> e inserisci il codice del telefono.</li>
    <li>Vai in <b>Impostazioni → Generali → Info → Impostazioni attendibilità certificati</b> (in fondo alla pagina) e attiva <b>Freezer di casa</b>.</li>
  </ol>

  <h2>2. App</h2>
  <a class="btn" href="__APP_URL__">Apri Freezer</a>
  <ol>
    <li>Freezer si apre in Safari. Se compare un avviso di sicurezza, ricontrolla il punto 3 qui sopra.</li>
    <li>Tocca <b>Condividi</b> (il quadrato con la freccia) → <b>Aggiungi alla schermata Home</b> → <b>Aggiungi</b>.</li>
    <li>D'ora in poi apri Freezer dall'icona: funziona anche in cantina, senza rete.</li>
  </ol>
</body>
</html>
```

- [ ] **Step 4: `deploy/install.sh`**

```bash
#!/usr/bin/env bash
# Installa o aggiorna Freezer su Linux Mint / Ubuntu. Si può rilanciare quante volte si vuole.
#   sudo ./deploy/install.sh [--host NOME.local] [--https-port 443] [--http-port 80] [--notify-time 08:30]
set -euo pipefail

APP_DIR=/opt/freezer
ENV_FILE=/etc/freezer/freezer.env
DATA_DIR=/var/lib/freezer
CADDY_ROOT_CRT=/var/lib/caddy/.local/share/caddy/pki/authorities/local/root.crt

HOST="$(hostname).local"
HTTPS_PORT=443
HTTP_PORT=80
NOTIFY_TIME="08:30"

die() { echo "ERRORE: $*" >&2; exit 1; }
info() { echo "==> $*"; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) HOST="${2:?manca il valore di --host}"; shift 2 ;;
    --https-port) HTTPS_PORT="${2:?manca il valore di --https-port}"; shift 2 ;;
    --http-port) HTTP_PORT="${2:?manca il valore di --http-port}"; shift 2 ;;
    --notify-time) NOTIFY_TIME="${2:?manca il valore di --notify-time}"; shift 2 ;;
    *) die "opzione sconosciuta: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "lancia lo script con sudo"
[[ "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)" == "$APP_DIR" ]] || die "il repository deve stare in $APP_DIR"
[[ $HTTPS_PORT =~ ^[0-9]+$ && $HTTP_PORT =~ ^[0-9]+$ ]] || die "le porte devono essere numeri"
[[ $NOTIFY_TIME =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "orario non valido: $NOTIFY_TIME (formato HH:MM)"
cd "$APP_DIR"

# ---- Controlli prima di toccare qualcosa -----------------------------------

if [[ $HOST == *.local ]]; then
  systemctl is-active --quiet avahi-daemon || die "avahi-daemon non è attivo: senza, gli iPhone non trovano $HOST"
fi

CONFIG_SOURCE="$ENV_FILE"
[[ -f $CONFIG_SOURCE ]] || CONFIG_SOURCE=deploy/freezer.env.example
APP_PORT="$(sed -n 's/^FREEZER_PORT=\([0-9][0-9]*\).*/\1/p' "$CONFIG_SOURCE" | tail -n1)"
APP_PORT="${APP_PORT:-8765}"

port_owner() {
  ss -Htlnp "sport = :$1" | grep -o 'users:(("[^"]*"' | head -n1 | cut -d'"' -f2 || true
}

check_port() {
  local port=$1 owner allowed
  shift
  owner="$(port_owner "$port")"
  [[ -z $owner ]] && return 0
  for allowed in "$@"; do
    [[ $owner == "$allowed" ]] && return 0
  done
  die "la porta $port è già usata da '$owner'. Vedi nel README come usare porte diverse."
}

check_port "$APP_PORT" uvicorn python3
check_port "$HTTPS_PORT" caddy
check_port "$HTTP_PORT" caddy

# ---- Pacchetti ---------------------------------------------------------------

info "Pacchetti"
if ! command -v caddy >/dev/null; then
  apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl gnupg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
    | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
  curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
    > /etc/apt/sources.list.d/caddy-stable.list
  chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list
  apt-get update
  apt-get install -y caddy
fi
dpkg -s python3-venv >/dev/null 2>&1 || apt-get install -y python3-venv

# ---- Utente, cartelle, configurazione ---------------------------------------

info "Utente e cartelle"
id -u freezer >/dev/null 2>&1 || useradd --system --home-dir "$DATA_DIR" --shell /usr/sbin/nologin freezer
install -d -o freezer -g freezer -m 750 "$DATA_DIR" "$DATA_DIR/backups"
install -d -m 755 /etc/freezer
if [[ ! -f $ENV_FILE ]]; then
  install -m 640 -o root -g freezer deploy/freezer.env.example "$ENV_FILE"
  info "Creato $ENV_FILE: qui si configura Telegram"
fi

# ---- App Python ---------------------------------------------------------------

info "Ambiente Python"
[[ -x .venv/bin/python ]] || python3 -m venv .venv
.venv/bin/pip install --quiet --upgrade pip
.venv/bin/pip install --quiet -r requirements.txt

info "Servizi systemd"
install -m 644 deploy/systemd/freezer.service deploy/systemd/freezer-notify.service \
  deploy/systemd/freezer-backup.service deploy/systemd/freezer-backup.timer /etc/systemd/system/
sed "s|__NOTIFY_TIME__|$NOTIFY_TIME|g" deploy/systemd/freezer-notify.timer > /etc/systemd/system/freezer-notify.timer
chmod 644 /etc/systemd/system/freezer-notify.timer
systemctl daemon-reload
systemctl enable --quiet freezer.service freezer-notify.timer freezer-backup.timer
systemctl restart freezer.service
systemctl restart freezer-notify.timer freezer-backup.timer

for _ in $(seq 1 20); do
  curl -fsS "http://127.0.0.1:$APP_PORT/api/inventory" >/dev/null 2>&1 && break
  sleep 0.5
done
curl -fsS "http://127.0.0.1:$APP_PORT/api/inventory" >/dev/null \
  || die "l'app non risponde: guarda 'journalctl -u freezer -n 50'"

# ---- Caddy (HTTPS) --------------------------------------------------------------

info "Caddy"
if [[ $HTTPS_PORT == 443 ]]; then HTTPS_SUFFIX=""; else HTTPS_SUFFIX=":$HTTPS_PORT"; fi
if [[ $HTTP_PORT == 80 ]]; then HTTP_SUFFIX=""; else HTTP_SUFFIX=":$HTTP_PORT"; fi
APP_URL="https://$HOST$HTTPS_SUFFIX"
CERT_URL="http://$HOST$HTTP_SUFFIX/cert"

if [[ -f /etc/caddy/Caddyfile && ! -f /etc/caddy/Caddyfile.orig ]] && ! grep -q '^# freezer' /etc/caddy/Caddyfile; then
  cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.orig
fi
sed -e "s|__HOST__|$HOST|g" \
    -e "s|__HTTPS_PORT__|$HTTPS_PORT|g" \
    -e "s|__HTTP_PORT__|$HTTP_PORT|g" \
    -e "s|__APP_PORT__|$APP_PORT|g" \
    -e "s|__HTTPS_SUFFIX__|$HTTPS_SUFFIX|g" \
    deploy/Caddyfile.template > /etc/caddy/Caddyfile
sed "s|__APP_URL__|$APP_URL|g" deploy/cert.html > /etc/caddy/freezer-cert.html
chmod 644 /etc/caddy/Caddyfile /etc/caddy/freezer-cert.html
caddy adapt --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null || die "Caddyfile non valido"
systemctl enable --quiet caddy
systemctl reload-or-restart caddy

ok=""
for _ in $(seq 1 30); do
  if [[ -f $CADDY_ROOT_CRT ]] && curl -fsS --cacert "$CADDY_ROOT_CRT" \
      --resolve "$HOST:$HTTPS_PORT:127.0.0.1" "$APP_URL/api/inventory" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 1
done
[[ -n $ok ]] || die "HTTPS non risponde su $APP_URL: guarda 'journalctl -u caddy -n 50'"

cat <<EOF

Fatto! Freezer è attivo.

Su ogni iPhone (collegato al Wi-Fi di casa), in Safari:
  1. apri  $CERT_URL  e segui i passaggi per il certificato
  2. apri  $APP_URL  →  Condividi  →  "Aggiungi alla schermata Home"

Telegram: inserisci TELEGRAM_BOT_TOKEN e TELEGRAM_CHAT_ID in $ENV_FILE, poi prova con
  sudo -u freezer bash -c 'set -a; . $ENV_FILE; cd $APP_DIR && .venv/bin/python -m freezer.notify --prova'
Avviso giornaliero alle $NOTIFY_TIME (controlla con: systemctl list-timers 'freezer-*').
EOF
```

- [ ] **Step 5: Verifica**

Run: `.venv/Scripts/python -m pytest -q && bash -n deploy/install.sh && echo SINTASSI-OK`
Expected: tutti PASS e `SINTASSI-OK`.

- [ ] **Step 6: Commit (con bit di esecuzione)**

```bash
git add deploy tests/test_deploy.py
git update-index --chmod=+x deploy/install.sh
git commit -m "feat: installazione su Linux con Caddy, systemd e pagina del certificato"
git ls-files -s deploy/install.sh
```
Expected: l'ultima riga inizia con `100755`.

---

### Task 11: README e pubblicazione su GitHub

**Files:**
- Create: `README.md`

**Interfaces:**
- Consumes: tutto il resto; nessun codice nuovo.
- Produces: istruzioni complete per sviluppo, installazione, Telegram, iPhone, aggiornamento, backup; repository privato su GitHub con `main` pubblicato.

- [ ] **Step 1: `README.md`**

````markdown
# ❄️ Freezer di cantina

Webapp per l'inventario del freezer di casa, pensata per iPhone e usabile anche **senza rete**
davanti al freezer. Le modifiche si sincronizzano col PC Linux quando si torna sotto Wi-Fi, e
ogni mattina un bot Telegram avvisa di ciò che è scaduto o sta per scadere.

- Server: Python + FastAPI + SQLite, dietro Caddy (HTTPS con certificato di casa).
- Telefono: PWA installata nella schermata Home, con coda offline.
- Design: `docs/superpowers/specs/2026-09-27-freezer-inventario-design.md`.

## Sviluppo (Windows o Linux)

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt   # Linux: .venv/bin/python
.venv/Scripts/python -m pytest                                # test del server
.venv/Scripts/python -m uvicorn --factory freezer.api:create_app --port 8765
```
Apri http://127.0.0.1:8765. Test JavaScript: `python tools/serve_tests.py` e apri
http://127.0.0.1:8766/tests/js/test.html. Le icone si rigenerano con `python tools/make_icons.py`.

## Installazione sul PC Linux

1. **Chiave per GitHub** (una volta): `ssh-keygen -t ed25519 -C freezer-pc`, poi copia
   `~/.ssh/id_ed25519.pub` in GitHub → repository `freezer` → Settings → Deploy keys → Add
   (lascia *Allow write access* spento).
2. **Scarica e installa:**
   ```bash
   sudo install -d -o "$USER" -g "$USER" /opt/freezer
   git clone git@github.com:<utente>/freezer.git /opt/freezer
   cd /opt/freezer && sudo ./deploy/install.sh
   ```
   Lo script installa Caddy, crea l'utente `freezer`, i servizi e stampa gli indirizzi da aprire
   sugli iPhone. Porte usate: 8765 (solo interna), 443 e 80. Se 443/80 fossero occupate:
   `sudo ./deploy/install.sh --https-port 8443 --http-port 8080`.
3. **Aggiornare** dopo nuove modifiche: `cd /opt/freezer && git pull && sudo ./deploy/install.sh`.

## iPhone (una volta per telefono)

In Safari, sotto il Wi-Fi di casa, apri `http://<nome-pc>.local/cert` e segui la pagina:
certificato → Impostazioni → Profilo scaricato → Installa → Generali → Info → Impostazioni
attendibilità certificati → attiva **Freezer di casa**. Poi apri `https://<nome-pc>.local` →
Condividi → **Aggiungi alla schermata Home**.

## Telegram

1. Su Telegram scrivi a **@BotFather** → `/newbot` → scegli nome e username. Copia il **token**.
2. Crea un gruppo con la famiglia, aggiungi il bot e scrivi `/start` nel gruppo.
3. Apri `https://api.telegram.org/bot<TOKEN>/getUpdates` nel browser e cerca
   `"chat":{"id":-100…`: quel numero (col meno) è il **chat id**.
4. `sudo nano /etc/freezer/freezer.env` → compila `TELEGRAM_BOT_TOKEN` e `TELEGRAM_CHAT_ID`.
5. Prova:
   `sudo -u freezer bash -c 'set -a; . /etc/freezer/freezer.env; cd /opt/freezer && .venv/bin/python -m freezer.notify --prova'`

L'avviso parte ogni giorno alle 08:30, solo se c'è qualcosa di scaduto o in scadenza entro 7
giorni (`FREEZER_WARN_DAYS`). Per cambiare orario: `sudo ./deploy/install.sh --notify-time 07:45`.

## Backup

Ogni notte alle 03:00 in `/var/lib/freezer/backups` (ultimi 14). Per ripristinarne uno:
```bash
sudo systemctl stop freezer
sudo -u freezer cp /var/lib/freezer/backups/freezer-AAAAMMGG-HHMMSS.db /var/lib/freezer/freezer.db
sudo rm -f /var/lib/freezer/freezer.db-wal /var/lib/freezer/freezer.db-shm
sudo systemctl start freezer
```

## Problemi comuni

| Sintomo | Cosa fare |
|---|---|
| L'app dice "PC non raggiungibile" in casa | `systemctl status freezer caddy`; il telefono è sul Wi-Fi di casa? |
| Safari avvisa che la connessione non è privata | Ripeti il passo "attendibilità certificati" sull'iPhone |
| L'iPhone non trova `<nome-pc>.local` | Prenota un IP fisso per il PC sul router e rilancia `sudo ./deploy/install.sh --host 192.168.1.50` (col tuo IP). Poi sugli iPhone apri il nuovo indirizzo e rimetti l'app nella Home: con un indirizzo nuovo la coda offline riparte da zero, quindi fallo sotto Wi-Fi a coda vuota. |
| Nessun messaggio Telegram | `journalctl -u freezer-notify -n 20`; il messaggio parte solo se c'è qualcosa in scadenza |
| Log dell'app | `journalctl -u freezer -n 50` |
````

- [ ] **Step 2: Verifica finale completa**

Run: `.venv/Scripts/python -m pytest -q` → tutti PASS.
Esegui i test JS (Task 6, **Interfaces**) → `data-summary="PASS 34/34"`.
Run: `git status --short` → vuoto dopo il commit del passo 3.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: README con installazione, iPhone, Telegram e backup"
```

- [ ] **Step 4: Pubblicazione su GitHub (serve Riccardo)**

`gh` non è installato, quindi il repository lo crea Riccardo: su github.com → **New repository** → nome `freezer`, **Private**, senza README/licenza/.gitignore. Chiedi a Riccardo l'URL SSH o HTTPS e **conferma prima di pubblicare**. Poi:
```bash
git remote add origin <URL>
git push -u origin main
```
Git Credential Manager apre il browser per l'accesso a GitHub. Expected: `branch 'main' set up to track 'origin/main'`.
