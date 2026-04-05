# tests/test_api.py
import time
import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from backend.db import init_db, insert_reading, upsert_state


@pytest.fixture(autouse=True)
def set_test_db(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr("backend.main.DB_PATH", db_path)
    monkeypatch.setattr("backend.main.DATA_DIR", tmp_path)
    reports_dir = tmp_path / "reports"
    reports_dir.mkdir()
    monkeypatch.setattr("backend.main.REPORTS_DIR", reports_dir)


@pytest.mark.asyncio
async def test_get_reservoirs_empty(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get("/api/reservoirs")
    assert r.status_code == 200
    assert r.json() == []


@pytest.mark.asyncio
async def test_get_history_bad_period(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get("/api/history/CON?period=99d")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_consumption_missing_params(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get("/api/consumption?alias=CON")
    assert r.status_code == 400


def test_ws_snapshot(set_test_db):
    import asyncio
    import backend.main as m
    from starlette.testclient import TestClient

    asyncio.get_event_loop().run_until_complete(
        _init_db_for_ws(m.DB_PATH)
    )
    with TestClient(m.app) as client:
        with client.websocket_connect("/ws") as ws:
            msg = ws.receive_json()
    assert msg["type"] == "snapshot"
    assert isinstance(msg["data"], list)


async def _init_db_for_ws(db_path):
    async with aiosqlite.connect(db_path) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)


@pytest.mark.asyncio
async def test_get_reservoirs_with_data(set_test_db):
    import backend.main as m
    now = int(time.time())
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        await upsert_state(conn, {
            "alias": "CON", "node_id": "0x7758", "sensor_id": 1,
            "name": "Castelo de Consumo", "ts": now,
            "level_cm": 255, "volume_l": 45333, "pct": 56.7,
            "level_max_cm": 450, "volume_max_l": 80000, "rssi": -62,
        })
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get("/api/reservoirs")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["alias"] == "CON"
    assert data[0]["online"] is True


@pytest.mark.asyncio
async def test_history_returns_raw_fields_for_data_page(set_test_db):
    import backend.main as m
    now = int(time.time())
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        await insert_reading(conn, {
            "ts": now, "node_id": "0x7758", "sensor_id": 1, "alias": "CON",
            "distance_cm": 215, "level_cm": 255, "volume_l": 45333, "pct": 56.7,
            "rssi": -62, "vbat": 3.3, "seq": 7
        })
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get("/api/history/CON?period=24h")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["distance_cm"] == 215
    assert data[0]["rssi"] == -62
    assert data[0]["vbat"] == 3.3
    assert data[0]["seq"] == 7
