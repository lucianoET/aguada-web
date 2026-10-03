# tests/test_alarms.py — alarmes com histerese, falha de sensor, eventos insert-only, hidrômetro incremental
import time

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from backend.alarms import AlarmEngine, duration, level_band
from backend.db import get_active_alarms, get_events, init_db, upsert_state


def test_level_band_hysteresis():
    assert level_band(30, None) == "baixo"
    assert level_band(37, "baixo") == "baixo"      # dentro da histerese: não normaliza
    assert level_band(39, "baixo") is None
    assert level_band(20, "baixo") == "critico"
    assert level_band(22, "critico") == "critico"
    assert level_band(24, "critico") == "baixo"    # sai do crítico, ainda baixo
    assert level_band(98, None) == "alto"
    assert level_band(96, "alto") == "alto"
    assert level_band(94, "alto") is None
    assert level_band(None, "baixo") == "baixo"    # sem leitura válida mantém o estado


def test_duration():
    assert duration(5) == "5 min"
    assert duration(538) == "8 h 58 min"
    assert duration(3000) == "2 dias"


async def _engine(tmp_path):
    path = str(tmp_path / "a.db")
    async with aiosqlite.connect(path) as conn:
        await init_db(conn)
    eng = AlarmEngine(path)
    await eng.load()
    return path, eng


async def _events(path):
    async with aiosqlite.connect(path) as conn:
        conn.row_factory = aiosqlite.Row
        return list(reversed(await get_events(conn))), await get_active_alarms(conn)


def _rec(pct, ts=None, level=None, **kw):
    return {"alias": "CIE2", "name": "Cisterna IE-2", "pct": pct, "level_cm": level if level is not None else pct * 2,
            "ts": ts or int(time.time()), **kw}


@pytest.mark.asyncio
async def test_level_alarm_opens_once_and_normalizes(tmp_path):
    path, eng = await _engine(tmp_path)
    for pct in (50, 30, 31, 37, 39):
        await eng.on_reading(_rec(pct))
    events, active = await _events(path)
    assert [e["codigo"] for e in events] == ["nivel_baixo", "normalizado"]
    assert events[1]["ref_id"] == events[0]["id"]
    assert active == []


@pytest.mark.asyncio
async def test_active_alarm_survives_restart(tmp_path):
    path, eng = await _engine(tmp_path)
    await eng.on_reading(_rec(10))
    eng2 = AlarmEngine(path)
    await eng2.load()
    await eng2.on_reading(_rec(12))          # mesmo alarme: não duplica
    events, active = await _events(path)
    assert [e["codigo"] for e in events] == ["nivel_critico"]
    assert len(active) == 1


@pytest.mark.asyncio
async def test_offline_and_back(tmp_path):
    path, eng = await _engine(tmp_path)
    async with aiosqlite.connect(path) as conn:
        await upsert_state(conn, {"alias": "CIE2", "node_id": "n", "sensor_id": 1, "name": "Cisterna IE-2",
                                  "ts": int(time.time()) - 3600, "level_cm": 100, "volume_l": 1, "pct": 50,
                                  "level_max_cm": 200, "volume_max_l": 2, "rssi": None})
    await eng.check_offline()
    await eng.check_offline()                # não duplica
    await eng.on_reading(_rec(50))
    events, active = await _events(path)
    assert [e["codigo"] for e in events] == ["sensor_offline", "normalizado"]
    assert active == []


@pytest.mark.asyncio
async def test_jump_is_logged(tmp_path):
    path, eng = await _engine(tmp_path)
    now = int(time.time())
    await eng.on_reading(_rec(50, ts=now - 60, level=100))
    await eng.on_reading(_rec(50, ts=now, level=170))
    events, active = await _events(path)
    assert [e["codigo"] for e in events] == ["sensor_salto"]
    assert active == []                      # pontual, não fica ativo


@pytest.mark.asyncio
async def test_events_are_insert_only(tmp_path):
    path, eng = await _engine(tmp_path)
    await eng.on_reading(_rec(10))
    async with aiosqlite.connect(path) as conn:
        with pytest.raises(aiosqlite.Error, match="insert-only"):
            await conn.execute("UPDATE events SET descricao = 'x'")
        with pytest.raises(aiosqlite.Error, match="insert-only"):
            await conn.execute("DELETE FROM events")


@pytest.fixture
def api_db(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.main.DB_PATH", str(tmp_path / "api.db"))
    return str(tmp_path / "api.db")


@pytest.mark.asyncio
async def test_hydrometer_reading_must_increase(api_db):
    import backend.main as m
    async with aiosqlite.connect(api_db) as conn:
        await init_db(conn)
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        ok = await client.post("/api/manual/hydrometers", json={"meter_name": "HID-AV", "reading": 100, "ts": 1000})
        low = await client.post("/api/manual/hydrometers", json={"meter_name": "HID-AV", "reading": 90, "ts": 2000})
        no_note = await client.post("/api/manual/hydrometers", json={"meter_name": "HID-AV", "reading": 5, "ts": 2000, "substituicao": True})
        swap = await client.post("/api/manual/hydrometers", json={"meter_name": "HID-AV", "reading": 5, "ts": 2000,
                                                                  "substituicao": True, "note": "hidrômetro trocado"})
        back = await client.post("/api/manual/hydrometers", json={"meter_name": "HID-AV", "reading": 150, "ts": 1500})
        events = await client.get("/api/events")
    assert ok.status_code == 200
    assert low.status_code == 409 and "100.000" in low.json()["detail"]
    assert no_note.status_code == 400
    assert swap.status_code == 200
    assert back.status_code == 409           # retroativa maior que a posterior também é recusada
    assert [e["codigo"] for e in events.json()["items"]] == ["hidrometro_substituido"]


@pytest.mark.asyncio
async def test_pump_command_logs_before_and_after(api_db):
    import backend.main as m
    async with aiosqlite.connect(api_db) as conn:
        await init_db(conn)
    async with AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test") as client:
        await client.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "desligada"})
        await client.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "ligada", "note": "teste"})
        items = (await client.get("/api/events")).json()["items"]
        ack = await client.post(f"/api/events/{items[0]['id']}/ack")
        items = (await client.get("/api/events")).json()["items"]
    assert items[0]["descricao"] == "B02-E: desligada → ligada — teste"
    assert items[0]["usuario"] == "Teste" and items[0]["ack_usuario"] == "Teste"   # quem vem da sessão
    assert items[1]["descricao"] == "B02-E: sem registro → desligada"
    assert ack.status_code == 200
