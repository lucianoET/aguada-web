# tests/test_api.py
import time
import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from backend.db import init_db, insert_reading, upsert_state, insert_manual_pump_log, insert_manual_valve_log


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


@pytest.mark.asyncio
async def test_history_accepts_explicit_range(set_test_db):
    import backend.main as m
    now = int(time.time())
    earlier = now - 7200
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        await insert_reading(conn, {
            "ts": earlier, "node_id": "0x7758", "sensor_id": 1, "alias": "CON",
            "distance_cm": 220, "level_cm": 250, "volume_l": 44000, "pct": 55.0,
            "rssi": -63, "vbat": 3.2, "seq": 6
        })
        await insert_reading(conn, {
            "ts": now, "node_id": "0x7758", "sensor_id": 1, "alias": "CON",
            "distance_cm": 215, "level_cm": 255, "volume_l": 45333, "pct": 56.7,
            "rssi": -62, "vbat": 3.3, "seq": 7
        })
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get(f"/api/history/CON?since_ts={now - 300}&until_ts={now + 300}")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["seq"] == 7


@pytest.mark.asyncio
async def test_consumption_counts_cross_hour_recovery_in_balance(set_test_db):
    import backend.main as m
    day_start = int(time.time() // 86400 * 86400)
    readings = [
        (day_start + 10 * 60, 10000),
        (day_start + 20 * 60, 7000),
        (day_start + 30 * 60, 10000),
        (day_start + 65 * 60, 7000),
        (day_start + 75 * 60, 10000),
        (day_start + 85 * 60, 10000),
    ]
    target_date = time.strftime("%Y-%m-%d", time.localtime(day_start))

    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        for seq, (ts, volume_l) in enumerate(readings, start=1):
            await insert_reading(conn, {
                "ts": ts,
                "node_id": "0x7758",
                "sensor_id": 1,
                "alias": "CIE1",
                "distance_cm": 0,
                "level_cm": 0,
                "volume_l": volume_l,
                "pct": 0,
                "rssi": -62,
                "vbat": 3.3,
                "seq": seq,
            })

    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get(f"/api/consumption?alias=CIE1&date={target_date}")

    assert r.status_code == 200
    payload = r.json()
    assert payload["summary"]["consumed_l"] == pytest.approx(0)
    assert payload["summary"]["supplied_l"] == pytest.approx(0)
    assert payload["summary"]["balance_l"] == pytest.approx(0)


@pytest.mark.asyncio
async def test_report_equipment_states_returns_last_state_for_date(set_test_db):
    import backend.main as m
    now = int(time.time())
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)
        await insert_manual_pump_log(conn, {"ts": now - 100, "pump_name": "Bomba A", "state": "ligada", "operational_status": "OR", "mode": "manual", "note": None})
        await insert_manual_valve_log(conn, {"ts": now - 50, "valve_name": "Valvula X", "state": "aberta", "note": None})

    date = time.strftime("%Y-%m-%d", time.localtime(now))
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.get(f"/api/report/equipment-states?date={date}")

    assert r.status_code == 200
    payload = r.json()
    assert payload["pumps"][0]["pump_name"] == "Bomba A"
    assert payload["pumps"][0]["state"] == "ligada"
    assert payload["pumps"][0]["operational_status"] == "OR"
    assert payload["valves"][0]["valve_name"] == "Valvula X"
    assert payload["valves"][0]["state"] == "aberta"


@pytest.mark.asyncio
async def test_post_manual_pump_accepts_operational_status(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)

    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        r = await client.post("/api/manual/pumps", json={
            "pump_name": "B03-E",
            "state": "ligada",
            "operational_status": "OP",
            "mode": "manual"
        })

    assert r.status_code == 200
    payload = r.json()
    assert payload["pump_name"] == "B03-E"
    assert payload["operational_status"] == "OP"


@pytest.mark.asyncio
async def test_report_notes_can_be_created_and_archived(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)

    date = time.strftime("%Y-%m-%d", time.localtime(time.time()))
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        created = await client.post("/api/report/notes", json={"date": date, "note": "Primeira observação"})
        assert created.status_code == 200
        item = created.json()["item"]
        listed = await client.get(f"/api/report/notes?date={date}")
        assert listed.status_code == 200
        assert len(listed.json()["items"]) == 1

        archived = await client.post(f"/api/report/notes/{item['id']}/archive")
        assert archived.status_code == 200

        listed_after = await client.get(f"/api/report/notes?date={date}")
        assert listed_after.status_code == 200
        assert listed_after.json()["items"] == []


@pytest.mark.asyncio
async def test_report_data_round_trip_persists_by_date(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)

    payload = {
        "date": "2026-04-08",
        "electrician": "Joao Silva",
        "ose": "Equipe Norte",
        "volume_rows": [
            {"label": "07h", "values": {"CON": 1.2, "CAV": 2.3, "CB3": None, "CIE1": 3.4, "CIE2": 4.5, "CBIF": 5.6}},
        ],
        "hydrometer_rows": [
            {"meterName": "H1", "previous": 10.0, "current": 11.5, "diff": 1.5},
        ],
        "pump_rows": [
            {"label": "CB1", "ELE": "OP", "DIE": "OR"},
        ],
        "valve_rows": [
            {"label": "AZ", "CON": "AB", "CAV": "FC"},
        ],
    }

    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        saved = await client.put("/api/report/data", json=payload)
        assert saved.status_code == 200

        loaded = await client.get(f"/api/report/data?date={payload['date']}")
        assert loaded.status_code == 200
        item = loaded.json()

    assert item["date"] == payload["date"]
    assert item["electrician"] == "Joao Silva"
    assert item["ose"] == "Equipe Norte"
    assert item["volume_rows"] == payload["volume_rows"]
    assert item["hydrometer_rows"] == payload["hydrometer_rows"]
    assert item["pump_rows"] == payload["pump_rows"]
    assert item["valve_rows"] == payload["valve_rows"]
    assert isinstance(item["updated_ts"], int)


@pytest.mark.asyncio
async def test_report_data_save_invalidates_cached_pdf(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)

    date = "2026-04-09"
    cached_pdf = m.REPORTS_DIR / f"{date}.pdf"
    cached_pdf.write_bytes(b"stale-pdf")

    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        response = await client.put("/api/report/data", json={
            "date": date,
            "electrician": "",
            "ose": "",
            "volume_rows": [],
            "hydrometer_rows": [],
            "pump_rows": [],
            "valve_rows": [],
        })

    assert response.status_code == 200
    assert not cached_pdf.exists()


@pytest.mark.asyncio
async def test_report_notes_invalidate_cached_pdf(set_test_db):
    import backend.main as m
    async with aiosqlite.connect(m.DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await init_db(conn)

    date = "2026-04-10"
    cached_pdf = m.REPORTS_DIR / f"{date}.pdf"
    cached_pdf.write_bytes(b"stale-pdf")

    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        created = await client.post("/api/report/notes", json={"date": date, "note": "Atualizar relatorio"})
        assert created.status_code == 200
        assert not cached_pdf.exists()

        cached_pdf.write_bytes(b"stale-pdf-again")
        note_id = created.json()["item"]["id"]
        archived = await client.post(f"/api/report/notes/{note_id}/archive")

    assert archived.status_code == 200
    assert not cached_pdf.exists()
