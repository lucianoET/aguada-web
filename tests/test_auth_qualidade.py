# tests/test_auth_qualidade.py — login/papéis, limites por reservatório, laudos, conciliação
import base64
import datetime
import time

import aiosqlite
import pytest
from httpx import ASGITransport, AsyncClient

from backend import auth
from backend.db import init_db
from backend.indicadores import meter_day_m3


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.main.DB_PATH", str(tmp_path / "t.db"))
    monkeypatch.setattr("backend.main.DATA_DIR", tmp_path)
    auth._fails.clear()
    return str(tmp_path / "t.db")


async def _client(path):
    import backend.main as m
    async with aiosqlite.connect(path) as conn:
        await init_db(conn)
    return AsyncClient(transport=ASGITransport(app=m.app), base_url="http://test")


def test_password_hash_roundtrip():
    h = auth.hash_password("segredo123")
    assert auth.check_password("segredo123", h)
    assert not auth.check_password("errada123", h)
    assert h != auth.hash_password("segredo123")   # sal aleatório


@pytest.mark.no_login
async def test_login_flow_and_roles(api):
    async with await _client(api) as c:
        assert (await c.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "ligada"})).status_code == 401
        assert (await c.get("/api/auth/me")).json() == {"user": None, "setup_needed": True}
        r = await c.post("/api/auth/setup", json={"username": "admin", "name": "Admin", "password": "curta"})
        assert r.status_code == 400                                    # senha curta
        r = await c.post("/api/auth/setup", json={"username": "admin", "name": "Admin", "password": "admin12345"})
        assert r.status_code == 200 and r.json()["user"]["role"] == "admin"
        assert (await c.post("/api/auth/setup", json={"username": "x", "name": "X", "password": "x12345678"})).status_code == 409
        r = await c.post("/api/users", json={"username": "op", "name": "Operador", "role": "operador", "password": "op123456"})
        assert r.status_code == 200
        await c.post("/api/auth/logout")
        assert (await c.get("/api/auth/me")).json()["user"] is None

        assert (await c.post("/api/auth/login", json={"username": "op", "password": "errada99"})).status_code == 401
        assert (await c.post("/api/auth/login", json={"username": "OP", "password": "op123456"})).status_code == 200
        assert (await c.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "ligada"})).status_code == 200
        assert (await c.put("/api/limits/CON", json={"critico": 10, "baixo": 30, "alto": 95})).status_code == 403
        assert (await c.get("/api/users")).status_code == 403
        ev = (await c.get("/api/events")).json()["items"]
        assert any(e["codigo"] == "estado_manual" and e["usuario"] == "Operador" for e in ev)
        assert any(e["codigo"] == "login_falhou" for e in ev)


@pytest.mark.no_login
async def test_login_lockout(api):
    async with await _client(api) as c:
        await c.post("/api/auth/setup", json={"username": "admin", "name": "Admin", "password": "admin12345"})
        for _ in range(auth.MAX_FAILS):
            await c.post("/api/auth/login", json={"username": "admin", "password": "nao-e-essa"})
        r = await c.post("/api/auth/login", json={"username": "admin", "password": "admin12345"})
        assert r.status_code == 429


async def test_limits_per_reservoir(api):
    import backend.main as m
    from backend.alarms import AlarmEngine
    m.alarms = AlarmEngine(api)
    async with await _client(api) as c:
        assert (await c.put("/api/limits/con", json={"critico": 30, "baixo": 20, "alto": 95})).status_code == 400
        assert (await c.put("/api/limits/con", json={"critico": 10, "baixo": 30, "alto": 95})).status_code == 200
    assert m.alarms.limits_for("CON") == {"critico": 10, "baixo": 30, "alto": 95}
    await m.alarms.on_reading({"alias": "CON", "name": "Castelo", "pct": 15, "level_cm": 60, "ts": int(time.time())})
    assert m.alarms.active[("CON", "nivel")]["codigo"] == "nivel_baixo"   # com o padrão (20 %) seria crítico
    m.alarms = None


async def test_laudo_conformidade_e_alerta(api):
    import backend.main as m
    from backend.alarms import AlarmEngine
    m.alarms = AlarmEngine(api)
    pdf = base64.b64encode(b"%PDF-1.4 teste").decode()
    async with await _client(api) as c:
        await m.seed_pontos(await aiosqlite.connect(api))
        pontos = (await c.get("/api/qualidade/pontos")).json()["items"]
        con = next(p for p in pontos if p["reservatorio"] == "CON")
        r = await c.post("/api/qualidade/laudos", json={
            "ponto_id": con["id"], "data_coleta": "2026-10-01", "laboratorio": "Lab X", "pdf_base64": pdf,
            "parametros": [{"parametro": "ph", "valor": 7.1}, {"parametro": "cloro_livre", "valor": 0.1},
                           {"parametro": "e_coli", "valor": 0}]})
        assert r.status_code == 200 and r.json()["conforme"] is False
        laudo = (await c.get("/api/qualidade/laudos")).json()["items"][0]
        assert [p["conforme"] for p in laudo["parametros"]] == [1, 0, 1]
        assert (await c.get(f"/api/qualidade/laudos/{laudo['id']}/pdf")).content.startswith(b"%PDF")
        active = (await c.get("/api/events/active")).json()["items"]
        assert [a["codigo"] for a in active] == ["laudo_nao_conforme"]
        await c.post("/api/qualidade/laudos", json={"ponto_id": con["id"], "data_coleta": "2026-10-02", "laboratorio": "Lab X",
                                                    "parametros": [{"parametro": "cloro_livre", "valor": 0.8}]})
        assert (await c.get("/api/events/active")).json()["items"] == []
        bad = await c.post("/api/qualidade/laudos", json={"ponto_id": con["id"], "data_coleta": "2026-10-02", "laboratorio": "Lab",
                                                          "pdf_base64": base64.b64encode(b"nao e pdf").decode(),
                                                          "parametros": [{"parametro": "ph", "valor": 7}]})
        assert bad.status_code == 400
    async with aiosqlite.connect(api) as conn:
        with pytest.raises(aiosqlite.Error, match="insert-only"):
            await conn.execute("UPDATE laudo_parametros SET conforme = 1")
    m.alarms = None


def test_meter_day_delta():
    day = datetime.date(2026, 10, 1)
    start = int(datetime.datetime(2026, 10, 1).timestamp())
    rows = [(start - 3600, 100.0), (start + 3600, 104.0), (start + 80000, 112.5)]
    assert meter_day_m3(rows, day) == 12.5
    assert meter_day_m3(rows[:1], day) is None             # nada lido no dia
    assert meter_day_m3(rows[1:], day) is None             # falta a leitura de antes do dia


async def test_indicadores_endpoint(api):
    async with await _client(api) as c:
        await c.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "ligada"})
        await c.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "ligada"})
        await c.post("/api/manual/pumps", json={"pump_name": "B02-E", "state": "desligada"})
        r = await c.get("/api/indicadores?days=7")
    data = r.json()
    assert r.status_code == 200
    assert data["acionamentos_bomba"] == 1                 # ligada → ligada não conta duas vezes
    assert data["intervencoes_manuais"] == 3
    assert len(data["conciliacao"]["dias"]) == 7
