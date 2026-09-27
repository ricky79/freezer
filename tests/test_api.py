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
