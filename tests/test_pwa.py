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
