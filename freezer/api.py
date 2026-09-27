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
