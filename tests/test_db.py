# tests/test_db.py
import time
import pytest
from backend.db import init_db, insert_reading, upsert_state, get_all_states, get_history, get_readings_for_date

@pytest.mark.asyncio
async def test_init_db_creates_tables(db):
    async with db.execute("SELECT name FROM sqlite_master WHERE type='table'") as cur:
        tables = {row[0] async for row in cur}
    assert "readings" in tables
    assert "reservoir_state" in tables

@pytest.mark.asyncio
async def test_insert_reading(db):
    now = int(time.time())
    await insert_reading(db, {
        "ts": now, "node_id": "0x7758", "sensor_id": 1, "alias": "CON",
        "distance_cm": 215, "level_cm": 255, "volume_l": 45333, "pct": 56.7,
        "rssi": -62, "vbat": 3.3, "seq": 1
    })
    async with db.execute("SELECT alias FROM readings") as cur:
        rows = [row async for row in cur]
    assert len(rows) == 1
    assert rows[0][0] == "CON"

@pytest.mark.asyncio
async def test_upsert_state_creates_and_updates(db):
    now = int(time.time())
    state = {
        "alias": "CON", "node_id": "0x7758", "sensor_id": 1,
        "name": "Castelo de Consumo", "ts": now,
        "level_cm": 255, "volume_l": 45333, "pct": 56.7,
        "level_max_cm": 450, "volume_max_l": 80000, "rssi": -62,
    }
    await upsert_state(db, state)
    async with db.execute("SELECT pct FROM reservoir_state WHERE alias='CON'") as cur:
        row = await cur.fetchone()
    assert abs(row[0] - 56.7) < 0.01

    state["pct"] = 80.0
    await upsert_state(db, state)
    async with db.execute("SELECT pct FROM reservoir_state WHERE alias='CON'") as cur:
        row = await cur.fetchone()
    assert abs(row[0] - 80.0) < 0.01

@pytest.mark.asyncio
async def test_get_all_states_returns_online_flag(db):
    now = int(time.time())
    await upsert_state(db, {
        "alias": "CON", "node_id": "0x7758", "sensor_id": 1,
        "name": "Castelo de Consumo", "ts": now,
        "level_cm": 255, "volume_l": 45333, "pct": 56.7,
        "level_max_cm": 450, "volume_max_l": 80000, "rssi": -62,
    })
    states = await get_all_states(db)
    assert len(states) == 1
    assert states[0]["online"] is True

@pytest.mark.asyncio
async def test_get_all_states_offline_if_stale(db):
    old_ts = int(time.time()) - 700  # > 600s atrás
    await upsert_state(db, {
        "alias": "CON", "node_id": "0x7758", "sensor_id": 1,
        "name": "Castelo de Consumo", "ts": old_ts,
        "level_cm": 255, "volume_l": 45333, "pct": 56.7,
        "level_max_cm": 450, "volume_max_l": 80000, "rssi": -62,
    })
    states = await get_all_states(db)
    assert states[0]["online"] is False

@pytest.mark.asyncio
async def test_get_history_returns_readings(db):
    now = int(time.time())
    for i in range(5):
        await insert_reading(db, {
            "ts": now - i * 100, "node_id": "0x7758", "sensor_id": 1, "alias": "CON",
            "distance_cm": 215 + i, "level_cm": 255 - i, "volume_l": 45000 - i * 100,
            "pct": 56.0, "rssi": -62, "vbat": 3.3, "seq": i
        })
    rows = await get_history(db, alias="CON", since_ts=now - 600)
    assert len(rows) == 5
    assert rows[0]["distance_cm"] is not None
    assert rows[0]["rssi"] == -62
    assert rows[0]["vbat"] == 3.3
    assert rows[0]["seq"] == 4

@pytest.mark.asyncio
async def test_get_readings_for_date(db):
    import datetime
    today = datetime.date.today()
    ts_noon = int(datetime.datetime(today.year, today.month, today.day, 12, 0, 0).timestamp())
    await insert_reading(db, {
        "ts": ts_noon, "node_id": "0x7758", "sensor_id": 1, "alias": "CON",
        "distance_cm": 215, "level_cm": 255, "volume_l": 45000,
        "pct": 56.0, "rssi": -62, "vbat": 3.3, "seq": 1
    })
    rows = await get_readings_for_date(db, alias="CON", date_str=today.isoformat())
    assert len(rows) == 1
    assert rows[0]["distance_cm"] == 215
    assert rows[0]["rssi"] == -62
    assert rows[0]["vbat"] == 3.3
    assert rows[0]["seq"] == 1
