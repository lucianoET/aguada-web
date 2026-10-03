# backend/main.py
import asyncio
import base64
import datetime
import json
import uuid
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import Depends, FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

try:
    from dotenv import dotenv_values
except ImportError:  # pragma: no cover - optional dependency via uvicorn[standard]
    dotenv_values = None

if dotenv_values is not None:
    env_path = Path(__file__).resolve().parents[1] / ".env"
    if env_path.exists():
        env_values = dotenv_values(env_path)
        for key in (
            "SERIAL_PORT", "MQTT_HOST", "MQTT_PORT", "MQTT_USER", "MQTT_PASS", "TZ",
            "GATEWAY_TRANSPORT", "GW_MQTT_HOST", "GW_MQTT_PORT", "GW_MQTT_USER", "GW_MQTT_PASS", "GW_MQTT_TOPIC",
        ):
            value = env_values.get(key)
            if value and key not in os.environ:
                os.environ[key] = value

from .bridge import Bridge, RESERVOIR_INDEX, reload_reservoirs
from .db import (
    init_db,
    get_all_states,
    get_history,
    get_readings_for_date,
    insert_reading,
    upsert_state,
    insert_manual_hydrometer_reading,
    insert_manual_pump_log,
    insert_manual_valve_log,
    insert_manual_reservoir_log,
    get_manual_hydrometer_history,
    get_manual_pump_logs,
    get_manual_valve_logs,
    get_manual_reservoir_logs,
    get_latest_pump_states,
    get_latest_valve_states,
    get_latest_hydrometer_readings,
    get_pump_states_for_date,
    get_valve_states_for_date,
    insert_report_note,
    get_report_notes,
    archive_report_note,
    get_report_daily_data,
    upsert_report_daily_data,
    get_all_nodes,
    get_node,
    patch_node,
    is_supported_valve_name,
    insert_event,
    get_events,
    get_active_alarms,
    ack_event,
    get_hydrometer_neighbors,
)
from .calc import calc_consumption_events, decimate_readings
from .dashboard import build_data as build_dashboard_data
from .alarms import LIMITS, AlarmEngine
from . import auth
from .db import get_reservoir_limits, set_reservoir_limits
from .indicadores import conciliacao, kpis as calc_kpis
from .qualidade import PARAMETROS, conforme, get_laudo_arquivo, insert_laudo, list_laudos, list_pontos, seed_pontos
from .report import generate_daily_report_pdf

logger = logging.getLogger("main")
logging.basicConfig(level=logging.INFO)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = PROJECT_ROOT / "data"
DATA_DIR = Path(os.getenv("DATA_DIR", str(DEFAULT_DATA_DIR)))
DB_PATH = str(DATA_DIR / "aguada.db")
REPORTS_DIR = DATA_DIR / "reports"


class WSManager:
    def __init__(self):
        self._clients: list[WebSocket] = []
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.append(ws)

    def disconnect(self, ws: WebSocket):
        if ws in self._clients:
            self._clients.remove(ws)

    def broadcast_event(self, event: dict):
        """Evento novo (alarme, normalização, comando) para as páginas abertas."""
        if self._loop is None:
            return
        msg = json.dumps({"type": "event", "data": event})
        try:
            self._loop.call_soon_threadsafe(lambda: asyncio.ensure_future(self._send_all(msg), loop=self._loop))
        except RuntimeError:
            pass  # loop já encerrado (shutdown, testes): evento já está gravado

    def broadcast(self, data: dict):
        """Chamado pela bridge thread — agenda envio no loop asyncio principal."""
        if self._loop is None:
            return
        # Leitura acabou de chegar: online por definição (o record do bridge não traz o campo)
        msg = json.dumps({"type": "reading", "data": {**data, "online": True}})
        self._loop.call_soon_threadsafe(
            lambda: asyncio.ensure_future(self._send_all(msg), loop=self._loop)
        )

    async def _send_all(self, msg: str):
        dead = []
        for ws in list(self._clients):
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def send_snapshot(self, ws: WebSocket):
        async with aiosqlite.connect(DB_PATH) as conn:
            conn.row_factory = aiosqlite.Row
            states = await get_all_states(conn)
        await ws.send_text(json.dumps({"type": "snapshot", "data": _with_meta(states)}))


ws_manager = WSManager()
bridge: Optional[Bridge] = None
scheduler: Optional[AsyncIOScheduler] = None
alarms: Optional[AlarmEngine] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, scheduler, alarms, DATA_DIR, DB_PATH, REPORTS_DIR
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except PermissionError:
        if DATA_DIR != DEFAULT_DATA_DIR:
            logger.warning("DATA_DIR=%s sem permissão no host; usando fallback %s", DATA_DIR, DEFAULT_DATA_DIR)
            DATA_DIR = DEFAULT_DATA_DIR
            DB_PATH = str(DATA_DIR / "aguada.db")
            REPORTS_DIR = DATA_DIR / "reports"
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        else:
            raise

    async with aiosqlite.connect(DB_PATH) as conn:
        await init_db(conn)
        await seed_pontos(conn)

    loop = asyncio.get_running_loop()
    ws_manager.set_loop(loop)

    alarms = AlarmEngine(DB_PATH, notify=ws_manager.broadcast_event)
    await alarms.load()

    bridge = Bridge(db_path=DB_PATH, notify_cb=ws_manager.broadcast, after_save=alarms.on_reading)
    bridge.start(loop)

    scheduler = AsyncIOScheduler(timezone=os.getenv("TZ", "America/Sao_Paulo"))
    scheduler.add_job(_daily_report_job, "cron", hour=6, minute=0)
    scheduler.add_job(alarms.check_offline, "interval", minutes=1)
    scheduler.add_job(_conciliacao_job, "cron", hour=0, minute=15)
    scheduler.start()

    yield

    scheduler.shutdown()


async def _conciliacao_job():
    """Dia anterior: diferença acima de DISCREP_PCT entre o que saiu e o que foi medido vira alerta (§8.3, §10.3)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        dia = (await conciliacao(conn, days=1))[0]
        for par in dia["pares"]:
            if par["status"] != "inconsistente":
                continue
            ev = await insert_event(conn, {
                "ts": int(time.time()), "tipo": "informativo", "severidade": "alerta", "entidade": "hidrometro",
                "entidade_id": par["id"], "codigo": "hidrometro_inconsistente", "valor": par["diff_pct"],
                "descricao": f"{par['nome']} em {dia['data']}: {par['a_m3']:.1f} m³ × {par['b_m3']:.1f} m³ "
                             f"(diferença {par['diff_m3']:+.1f} m³, {par['diff_pct']:+.1f} %)"})
            ws_manager.broadcast_event(ev)


async def _daily_report_job():
    import datetime
    date_str = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()
    out_path = REPORTS_DIR / f"{date_str}.pdf"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await generate_daily_report_pdf(conn, date_str, str(out_path))
    logger.info("Relatório diário gerado: %s", out_path)


def _invalidate_report_pdf(date_str: str) -> None:
    out_path = REPORTS_DIR / f"{date_str}.pdf"
    try:
        out_path.unlink(missing_ok=True)
    except TypeError:
        if out_path.exists():
            out_path.unlink()


app = FastAPI(title="Aguada Web", lifespan=lifespan)


# ── Autenticação (Normas §12.4): leitura aberta na rede local; escrita exige sessão ──

async def current_user(request: Request) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as conn:
        return await auth.session_user(conn, request.cookies.get(auth.COOKIE))


def _need(minimum: str):
    async def dependency(request: Request) -> dict:
        user = await current_user(request)
        if not user:
            raise HTTPException(401, "Entre com usuário e senha para registrar")
        if not auth.role_at_least(user["role"], minimum):
            raise HTTPException(403, f"Ação restrita ao perfil {minimum} ou acima")
        return user
    return dependency


require_operador = _need("operador")
require_supervisor = _need("supervisor")
require_admin = _need("admin")


class ReportDailyDataRequest(BaseModel):
    date: str
    electrician: Optional[str] = ""
    ose: Optional[str] = ""
    volume_rows: list[dict] = Field(default_factory=list)
    hydrometer_rows: list[dict] = Field(default_factory=list)
    pump_rows: list[dict] = Field(default_factory=list)
    valve_rows: list[dict] = Field(default_factory=list)


def _with_meta(states: list[dict]) -> list[dict]:
    """Enriquece estados com lat/lng e capacity_l do reservoirs.yaml.
    Usado por /api/reservoirs e pelo snapshot do WebSocket (mesmo formato nos dois)."""
    reload_reservoirs()
    alias_to_meta: dict[str, dict] = {}
    for params in list(RESERVOIR_INDEX.values()):
        alias = params.get("alias")
        if not alias:
            continue
        meta: dict = {}
        if "lat" in params and "lng" in params:
            meta["lat"] = params["lat"]
            meta["lng"] = params["lng"]
        if "volume_max_l" in params:
            meta["capacity_l"] = params["volume_max_l"]
        alias_to_meta[alias] = meta
    for s in states:
        meta = alias_to_meta.get(s.get("alias", ""), {})
        s.update(meta)
    return states


@app.get("/api/reservoirs")
async def get_reservoirs():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        states = await get_all_states(conn)
    return _with_meta(states)


@app.get("/api/history/{alias}")
async def get_history_route(
    alias: str,
    period: str = "24h",
    since_ts: Optional[int] = Query(None),
    until_ts: Optional[int] = Query(None),
):
    periods = {"24h": 86400, "7d": 7 * 86400, "30d": 30 * 86400}
    if since_ts is None:
        seconds = periods.get(period)
        if seconds is None:
            raise HTTPException(400, "period deve ser 24h, 7d ou 30d")
        since_ts = int(time.time()) - seconds
    if until_ts is not None and until_ts <= since_ts:
        raise HTTPException(400, "until_ts deve ser maior que since_ts")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_history(conn, alias=alias.upper(), since_ts=since_ts, until_ts=until_ts)
    return decimate_readings(rows, max_points=500)


@app.get("/api/consumption")
async def get_consumption(
    alias: Optional[str] = Query(None),
    date: Optional[str] = Query(None),
):
    if alias is None or date is None:
        raise HTTPException(400, "alias e date são obrigatórios")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        readings = await get_readings_for_date(conn, alias=alias.upper(), date_str=date)
    if not readings:
        return {"date": date, "alias": alias.upper(), "summary": {}, "events": []}

    events = calc_consumption_events(readings, date=date)
    consumed = sum(abs(e["delta_l"]) for e in events if e["type"] == "consumption")
    supplied = sum(e["delta_l"] for e in events if e["type"] == "supply")
    return {
        "date": date,
        "alias": alias.upper(),
        "summary": {
            "consumed_l": round(consumed, 1),
            "supplied_l": round(supplied, 1),
            "balance_l": round(supplied - consumed, 1),
        },
        "events": events,
    }


_dashboard_cache: tuple[float, dict] | None = None


@app.get("/api/dashboard")
def get_dashboard():
    """Série horária e resumo diário de todos os reservatórios (página Análise)."""
    # def síncrono: FastAPI roda em threadpool. Cache de 2 min porque o cálculo varre a tabela toda.
    global _dashboard_cache
    if _dashboard_cache is None or time.time() - _dashboard_cache[0] > 120:
        _dashboard_cache = (time.time(), build_dashboard_data(DB_PATH))
    return _dashboard_cache[1]


@app.get("/api/report/daily")
async def get_report_data(date: str = Query(...)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        states = await get_all_states(conn)
        report_data = []
        for s in states:
            alias = s["alias"]
            readings = await get_readings_for_date(conn, alias=alias, date_str=date)
            events = calc_consumption_events(readings, date=date) if readings else []
            report_data.append({**s, "events": events, "readings_count": len(readings)})
    return {"date": date, "reservoirs": report_data}


@app.get("/api/report/equipment-states")
async def get_report_equipment_states(date: str = Query(...)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        pumps = await get_pump_states_for_date(conn, date)
        valves = await get_valve_states_for_date(conn, date)
    return {"date": date, "pumps": pumps, "valves": valves}


@app.get("/api/report/data")
async def get_report_data_route(date: str = Query(...)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        item = await get_report_daily_data(conn, date)
    return {
        "date": date,
        "electrician": item.get("electrician", "") if item else "",
        "ose": item.get("ose", "") if item else "",
        "volume_rows": item.get("volume_rows", []) if item else [],
        "hydrometer_rows": item.get("hydrometer_rows", []) if item else [],
        "pump_rows": item.get("pump_rows", []) if item else [],
        "valve_rows": item.get("valve_rows", []) if item else [],
        "updated_ts": item.get("updated_ts") if item else None,
    }


@app.put("/api/report/data")
async def put_report_data_route(body: ReportDailyDataRequest, user: dict = Depends(require_operador)):
    payload = body.model_dump() if hasattr(body, "model_dump") else body.dict()
    payload["updated_ts"] = int(time.time())
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await upsert_report_daily_data(conn, payload)
        item = await get_report_daily_data(conn, body.date)
    _invalidate_report_pdf(body.date)
    return {"ok": True, "item": item}


@app.get("/api/report/notes")
async def get_report_notes_route(date: str = Query(...), active_only: bool = Query(True)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        items = await get_report_notes(conn, date, active_only=active_only)
    return {"date": date, "items": items}


@app.get("/api/report/daily.pdf")
async def get_report_pdf(date: str = Query(...)):
    out_path = REPORTS_DIR / f"{date}.pdf"
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await generate_daily_report_pdf(conn, date, str(out_path))
    if not out_path.exists():
        raise HTTPException(404, "Relatório não disponível para esta data")
    return FileResponse(
        str(out_path),
        media_type="application/pdf",
        filename=f"aguada-{date}.pdf",
        headers={
            "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


class ManualReadingRequest(BaseModel):
    alias: str
    volume_l: Optional[float] = None
    pct: Optional[float] = None
    note: Optional[str] = None


class ManualHydrometerRequest(BaseModel):
    meter_name: str
    reading: float
    unit: str = "m3"
    ts: Optional[int] = None
    note: Optional[str] = None
    substituicao: bool = False  # hidrômetro trocado/zerado: aceita leitura menor (exige note)


class ManualPumpRequest(BaseModel):
    pump_name: str
    state: str  # ligada | desligada | falha | manutencao
    operational_status: Optional[str] = None  # OP | INOP | OR | MNT
    mode: str = "manual"
    ts: Optional[int] = None
    note: Optional[str] = None


class ManualValveRequest(BaseModel):
    valve_name: str
    state: str  # aberta | fechada | parcial | falha
    ts: Optional[int] = None
    note: Optional[str] = None


class ManualReservoirRequest(BaseModel):
    reservoir_name: str
    has_sensor: bool = False
    level_cm: Optional[float] = None
    volume_l: Optional[float] = None
    pct: Optional[float] = None
    ts: Optional[int] = None
    note: Optional[str] = None


class ReportNoteRequest(BaseModel):
    date: str
    note: str


@app.post("/api/readings/manual")
async def post_manual_reading(body: ManualReadingRequest, user: dict = Depends(require_operador)):
    alias = body.alias.upper()
    reload_reservoirs()
    found = next(((k, p) for k, p in list(RESERVOIR_INDEX.items()) if p["alias"] == alias), None)
    if found is None:
        raise HTTPException(400, f"Alias '{alias}' não encontrado")
    (node_id, sensor_id), params = found

    volume_max = params["volume_max_l"]
    level_max = params["level_max_cm"]

    if body.volume_l is not None:
        volume_l = max(0.0, min(float(body.volume_l), volume_max))
        pct = round(volume_l / volume_max * 100, 1)
        level_cm = round(volume_l / volume_max * level_max, 1)
    elif body.pct is not None:
        pct = max(0.0, min(float(body.pct), 100.0))
        volume_l = round(pct / 100 * volume_max, 1)
        level_cm = round(pct / 100 * level_max, 1)
    else:
        raise HTTPException(400, "Forneça volume_l ou pct")

    # distance_cm inverso (para manter consistência — sensor_offset não altera volume manual)
    distance_cm = round(level_max - level_cm + params["sensor_offset_cm"], 1)

    record = {
        "ts": int(time.time()),
        "node_id": node_id,
        "sensor_id": sensor_id,
        "alias": alias,
        "distance_cm": distance_cm,
        "level_cm": level_cm,
        "volume_l": volume_l,
        "pct": pct,
        "rssi": None,
        "vbat": None,
        "seq": None,
        "name": params["name"],
        "level_max_cm": level_max,
        "volume_max_l": volume_max,
    }

    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        await insert_reading(conn, record)
        await upsert_state(conn, record)

    # Notifica WebSocket em tempo real
    ws_manager.broadcast(record)
    if alarms:
        await alarms.on_reading(record)

    return {"ok": True, "alias": alias, "volume_l": volume_l, "pct": pct, "level_cm": level_cm}


@app.post("/api/manual/hydrometers")
async def post_manual_hydrometer(body: ManualHydrometerRequest, user: dict = Depends(require_operador)):
    meter_name = body.meter_name.strip()
    if not meter_name:
        raise HTTPException(400, "meter_name é obrigatório")
    item = {
        "ts": int(body.ts or time.time()),
        "meter_name": meter_name,
        "reading": float(body.reading),
        "unit": (body.unit or "m3").strip() or "m3",
        "note": body.note,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        # Normas §8.2: leitura acumulada só cresce. Encaixa entre a anterior e a posterior (lançamento retroativo).
        prev, nxt = await get_hydrometer_neighbors(conn, meter_name, item["ts"])
        regressiva = (prev and item["reading"] < prev["reading"]) or (nxt and item["reading"] > nxt["reading"])
        if regressiva and not body.substituicao:
            ref = prev if prev and item["reading"] < prev["reading"] else nxt
            raise HTTPException(409, f"Leitura fora de ordem: {meter_name} tem {ref['reading']:.3f} {item['unit']} em "
                                     f"{time.strftime('%d/%m/%Y %H:%M', time.localtime(ref['ts']))}. "
                                     "Se o hidrômetro foi trocado ou zerado, marque substituição e informe o motivo.")
        if regressiva and not (body.note or "").strip():
            raise HTTPException(400, "Substituição de hidrômetro exige o motivo em note")
        await insert_manual_hydrometer_reading(conn, item)
        if regressiva:
            ev = await insert_event(conn, {"ts": item["ts"], "tipo": "informativo", "severidade": "alerta",
                                           "entidade": "hidrometro", "entidade_id": meter_name, "codigo": "hidrometro_substituido",
                                           "descricao": f"{meter_name}: leitura reiniciada em {item['reading']:.3f} {item['unit']} — {body.note}",
                                           "valor": item["reading"], "usuario": user["name"]})
            ws_manager.broadcast_event(ev)
    return {"ok": True, **item}


@app.get("/api/manual/hydrometers")
async def get_manual_hydrometers(meter_name: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_hydrometer_history(conn, meter_name=meter_name, limit=limit)
    return {"items": rows}


@app.post("/api/manual/pumps")
async def post_manual_pump(body: ManualPumpRequest, user: dict = Depends(require_operador)):
    pump_name = body.pump_name.strip()
    if not pump_name:
        raise HTTPException(400, "pump_name é obrigatório")
    state = body.state.strip().lower()
    if state not in {"ligada", "desligada", "falha", "manutencao"}:
        raise HTTPException(400, "state inválido")
    operational_status = (body.operational_status or "").strip().upper() or None
    if operational_status is not None and operational_status not in {"OP", "INOP", "OR", "MNT"}:
        raise HTTPException(400, "operational_status inválido")
    item = {
        "ts": int(body.ts or time.time()),
        "pump_name": pump_name,
        "state": state,
        "operational_status": operational_status,
        "mode": (body.mode or "manual").strip() or "manual",
        "note": body.note,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        before = next((p["state"] for p in await get_latest_pump_states(conn) if p["pump_name"] == pump_name), None)
        await insert_manual_pump_log(conn, item)
        await _command_event(conn, "bomba", pump_name, before, state, body.note, user["name"], item["ts"])
    return {"ok": True, **item}


@app.get("/api/manual/pumps")
async def get_manual_pumps(limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_pump_logs(conn, limit=limit)
    return {"items": rows}


@app.post("/api/manual/valves")
async def post_manual_valve(body: ManualValveRequest, user: dict = Depends(require_operador)):
    valve_name = body.valve_name.strip()
    if not valve_name:
        raise HTTPException(400, "valve_name é obrigatório")
    if not is_supported_valve_name(valve_name):
        raise HTTPException(400, "valve_name inválido")
    state = body.state.strip().lower()
    if state not in {"aberta", "fechada", "parcial", "falha"}:
        raise HTTPException(400, "state inválido")
    item = {
        "ts": int(body.ts or time.time()),
        "valve_name": valve_name,
        "state": state,
        "note": body.note,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        before = next((v["state"] for v in await get_latest_valve_states(conn) if v["valve_name"] == valve_name), None)
        await insert_manual_valve_log(conn, item)
        await _command_event(conn, "valvula", valve_name, before, state, body.note, user["name"], item["ts"])
    return {"ok": True, **item}


async def _command_event(conn, entidade: str, nome: str, antes: Optional[str], depois: str,
                         motivo: Optional[str], usuario: Optional[str], ts: int) -> None:
    desc = f"{nome}: {antes or 'sem registro'} → {depois}" + (f" — {motivo}" if motivo else "")
    ev = await insert_event(conn, {"ts": ts, "tipo": "comando", "severidade": "info", "entidade": entidade,
                                   "entidade_id": nome, "codigo": "estado_manual", "descricao": desc, "usuario": usuario})
    ws_manager.broadcast_event(ev)


@app.get("/api/events")
async def list_events(limit: int = Query(200, ge=1, le=2000), since_ts: Optional[int] = Query(None)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return {"items": await get_events(conn, limit=limit, since_ts=since_ts)}


@app.get("/api/events/active")
async def list_active_alarms():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return {"items": await get_active_alarms(conn)}


@app.post("/api/events/{event_id}/ack")
async def ack_alarm(event_id: int, user: dict = Depends(require_operador)):
    async with aiosqlite.connect(DB_PATH) as conn:
        if not await ack_event(conn, event_id, user["name"], int(time.time())):
            raise HTTPException(404, "Evento não encontrado")
    ws_manager.broadcast_event({"id": event_id, "ack": True})
    return {"ok": True}


@app.get("/api/manual/valves")
async def get_manual_valves(limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_valve_logs(conn, limit=limit)
    return {"items": rows}


@app.post("/api/manual/reservoirs")
async def post_manual_reservoir(body: ManualReservoirRequest, user: dict = Depends(require_operador)):
    reservoir_name = body.reservoir_name.strip()
    if not reservoir_name:
        raise HTTPException(400, "reservoir_name é obrigatório")
    item = {
        "ts": int(body.ts or time.time()),
        "reservoir_name": reservoir_name,
        "has_sensor": 1 if body.has_sensor else 0,
        "level_cm": body.level_cm,
        "volume_l": body.volume_l,
        "pct": body.pct,
        "note": body.note,
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        await insert_manual_reservoir_log(conn, item)
    return {"ok": True, **item}


@app.get("/api/manual/reservoirs")
async def get_manual_reservoirs(limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_reservoir_logs(conn, limit=limit)
    return {"items": rows}


@app.post("/api/report/notes")
async def post_report_note(body: ReportNoteRequest, user: dict = Depends(require_operador)):
    note = body.note.strip()
    if not note:
        raise HTTPException(400, "note é obrigatório")
    item = {
        "date": body.date,
        "note": note,
        "created_ts": int(time.time()),
    }
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        note_id = await insert_report_note(conn, item)
        items = await get_report_notes(conn, body.date, active_only=True)
    created = next((entry for entry in items if entry["id"] == note_id), None)
    _invalidate_report_pdf(body.date)
    return {"ok": True, "item": created}


@app.post("/api/report/notes/{note_id}/archive")
async def archive_report_note_route(note_id: int, user: dict = Depends(require_operador)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        async with conn.execute("SELECT date FROM report_notes WHERE id=?", (note_id,)) as cur:
            row = await cur.fetchone()
        ok = await archive_report_note(conn, note_id, int(time.time()))
    if not ok:
        raise HTTPException(404, "Observação não encontrada ou já arquivada")
    if row and row["date"]:
        _invalidate_report_pdf(row["date"])
    return {"ok": True, "id": note_id}


@app.get("/api/equip/current")
async def get_equip_current():
    """Retorna estado atual (mais recente) de bombas, válvulas e hidrômetros."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        pumps = await get_latest_pump_states(conn)
        valves = await get_latest_valve_states(conn)
        hydrometers = await get_latest_hydrometer_readings(conn)
    return {"pumps": pumps, "valves": valves, "hydrometers": hydrometers}


@app.get("/api/gateway")
async def get_gateway_status():
    """Retorna status atual do gateway USB (porta serial, MAC, firmware, conectado)."""
    if bridge is None:
        return {"connected": False, "port": None, "mac": None, "fw": None, "sim_mode": False, "last_seen": None}
    return bridge.get_status()


@app.get("/api/nodes")
async def get_nodes():
    """Lista todos os nodes já vistos (HELLO), com estado online/offline."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        return await get_all_nodes(conn)


@app.get("/api/nodes/{node_id}")
async def get_node_detail(node_id: str):
    """Retorna detalhes de um node pelo node_id (ex: 0x7758)."""
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        node = await get_node(conn, node_id.lower())
    if node is None:
        raise HTTPException(404, f"Node '{node_id}' não encontrado")
    return node


@app.patch("/api/nodes/{node_id}")
async def patch_node_meta(node_id: str, body: dict, user: dict = Depends(require_supervisor)):
    """Atualiza alias, nome e nota de um node. Campos permitidos: alias, name, note."""
    allowed = {"alias", "name", "note"}
    if not any(k in body for k in allowed):
        raise HTTPException(400, f"Nenhum campo editável. Use: {allowed}")
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        ok = await patch_node(conn, node_id.lower(), body)
    if not ok:
        raise HTTPException(404, f"Node '{node_id}' não encontrado")
    return {"ok": True}


@app.post("/api/nodes/{node_id}/cmd")
async def post_node_cmd(node_id: str, body: dict, user: dict = Depends(require_supervisor)):
    """Envia um comando JSON ao nó via gateway serial (ex: RESTART, CMD_CONFIG)."""
    if bridge is None:
        raise HTTPException(503, "Bridge não inicializada")
    allowed = {"RESTART", "CMD_CONFIG"}
    cmd = body.get("cmd", "").upper()
    if cmd not in allowed:
        raise HTTPException(400, f"Comando '{cmd}' não permitido. Use: {allowed}")
    payload = {**body, "cmd": cmd, "node_id": node_id}
    bridge.send_cmd(payload)
    return {"ok": True, "queued": payload}


# ── Usuários e sessão ────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str


class SetupRequest(BaseModel):
    username: str
    name: str
    password: str


class UserCreateRequest(BaseModel):
    username: str
    name: str
    role: str = "operador"
    password: str


class UserUpdateRequest(BaseModel):
    name: Optional[str] = None
    role: Optional[str] = None
    active: Optional[bool] = None
    password: Optional[str] = None


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(auth.COOKIE, token, max_age=auth.SESSION_S, httponly=True, samesite="strict", path="/")


async def _audit(conn, entidade: str, entidade_id: str, codigo: str, descricao: str, usuario: Optional[str],
                 tipo: str = "comando", severidade: str = "info") -> None:
    ev = await insert_event(conn, {"ts": int(time.time()), "tipo": tipo, "severidade": severidade, "entidade": entidade,
                                   "entidade_id": entidade_id, "codigo": codigo, "descricao": descricao, "usuario": usuario})
    ws_manager.broadcast_event(ev)


@app.get("/api/auth/me")
async def auth_me(request: Request):
    async with aiosqlite.connect(DB_PATH) as conn:
        user = await auth.session_user(conn, request.cookies.get(auth.COOKIE))
        setup = await auth.count_users(conn) == 0
    return {"user": user, "setup_needed": setup}


@app.post("/api/auth/setup")
async def auth_setup(body: SetupRequest, response: Response):
    """Cria o primeiro administrador; só funciona com a tabela de usuários vazia."""
    if err := auth.validate_password(body.password):
        raise HTTPException(400, err)
    if not body.username.strip() or not body.name.strip():
        raise HTTPException(400, "Informe usuário e nome")
    async with aiosqlite.connect(DB_PATH) as conn:
        if await auth.count_users(conn):
            raise HTTPException(409, "Já existe administrador; entre com ele para criar usuários")
        user = await auth.create_user(conn, body.username, body.name, "admin", body.password)
        _set_session_cookie(response, await auth.create_session(conn, user["id"]))
        await _audit(conn, "usuario", user["username"], "usuario_criado", f"Primeiro administrador: {user['name']}", user["name"])
    return {"user": user}


@app.post("/api/auth/login")
async def auth_login(body: LoginRequest, response: Response):
    username = body.username.strip()
    if auth.locked(username):
        raise HTTPException(429, "Muitas tentativas erradas; espere 10 minutos")
    async with aiosqlite.connect(DB_PATH) as conn:
        user = await auth.get_user_by_username(conn, username)
        if not user or not user["active"] or not auth.check_password(body.password, user["pw_hash"]):
            auth.register_fail(username)
            await _audit(conn, "usuario", username or "?", "login_falhou", f"Login recusado para '{username}'", None,
                         tipo="informativo", severidade="alerta")
            raise HTTPException(401, "Usuário ou senha incorretos")
        auth.clear_fails(username)
        _set_session_cookie(response, await auth.create_session(conn, user["id"]))
    return {"user": {k: user[k] for k in ("id", "username", "name", "role")}}


@app.post("/api/auth/logout")
async def auth_logout(request: Request, response: Response):
    async with aiosqlite.connect(DB_PATH) as conn:
        await auth.delete_session(conn, request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}


@app.get("/api/users")
async def users_list(user: dict = Depends(require_admin)):
    async with aiosqlite.connect(DB_PATH) as conn:
        return {"items": await auth.list_users(conn)}


@app.post("/api/users")
async def users_create(body: UserCreateRequest, user: dict = Depends(require_admin)):
    if body.role not in auth.ROLES:
        raise HTTPException(400, "Perfil inválido")
    if err := auth.validate_password(body.password):
        raise HTTPException(400, err)
    if not body.username.strip() or not body.name.strip():
        raise HTTPException(400, "Informe usuário e nome")
    async with aiosqlite.connect(DB_PATH) as conn:
        if await auth.get_user_by_username(conn, body.username):
            raise HTTPException(409, "Usuário já existe")
        created = await auth.create_user(conn, body.username, body.name, body.role, body.password)
        await _audit(conn, "usuario", created["username"], "usuario_criado", f"{created['name']} criado como {created['role']}", user["name"])
    return {"user": created}


@app.patch("/api/users/{user_id}")
async def users_update(user_id: int, body: UserUpdateRequest, user: dict = Depends(require_admin)):
    if body.role is not None and body.role not in auth.ROLES:
        raise HTTPException(400, "Perfil inválido")
    if body.password and (err := auth.validate_password(body.password)):
        raise HTTPException(400, err)
    if user_id == user["id"] and (body.active is False or (body.role and body.role != "admin")):
        raise HTTPException(400, "Você não pode desativar nem rebaixar o próprio usuário")
    fields = {"name": body.name, "role": body.role, "password": body.password,
              "active": None if body.active is None else int(body.active)}
    async with aiosqlite.connect(DB_PATH) as conn:
        if not await auth.update_user(conn, user_id, fields):
            raise HTTPException(404, "Usuário não encontrado ou nada a alterar")
        changes = ", ".join(k if k != "password" else "senha" for k, v in fields.items() if v is not None)
        await _audit(conn, "usuario", str(user_id), "usuario_alterado", f"Usuário {user_id}: {changes}", user["name"])
    return {"ok": True}


# ── Limites de alarme por reservatório ───────────────────────────

class LimitsRequest(BaseModel):
    critico: float
    baixo: float
    alto: float


@app.get("/api/limits")
async def limits_list():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        own = await get_reservoir_limits(conn)
        states = await get_all_states(conn)
    return {"padrao": LIMITS, "items": [
        {"alias": st["alias"], "nome": st["name"] or st["alias"], **(alarms.limits_for(st["alias"]) if alarms else LIMITS),
         "proprio": st["alias"] in own, "updated_by": own.get(st["alias"], {}).get("updated_by"),
         "updated_ts": own.get(st["alias"], {}).get("updated_ts")}
        for st in sorted(states, key=lambda x: x["alias"])]}


@app.put("/api/limits/{alias}")
async def limits_set(alias: str, body: LimitsRequest, user: dict = Depends(require_supervisor)):
    if not (0 <= body.critico < body.baixo < body.alto <= 100):
        raise HTTPException(400, "Use 0 ≤ crítico < baixo < alto ≤ 100 (%)")
    alias = alias.upper()
    before = alarms.limits_for(alias) if alarms else LIMITS
    async with aiosqlite.connect(DB_PATH) as conn:
        await set_reservoir_limits(conn, alias, body.critico, body.baixo, body.alto, user["name"])
        await _audit(conn, "reservatorio", alias, "limites_alterados",
                     f"{alias}: limites {before['critico']:g}/{before['baixo']:g}/{before['alto']:g} % → "
                     f"{body.critico:g}/{body.baixo:g}/{body.alto:g} % (crítico/baixo/alto)", user["name"])
        if alarms:
            alarms.limits = await get_reservoir_limits(conn)
    return {"ok": True}


# ── Qualidade da água (laudos) ───────────────────────────────────

class LaudoParametro(BaseModel):
    parametro: str
    valor: float


class LaudoRequest(BaseModel):
    ponto_id: int
    data_coleta: str
    laboratorio: str
    numero: Optional[str] = None
    obs: Optional[str] = None
    parametros: list[LaudoParametro]
    pdf_base64: Optional[str] = None


class PontoRequest(BaseModel):
    nome: str
    reservatorio: Optional[str] = None


MAX_PDF_BYTES = 10 * 1024 * 1024


@app.get("/api/qualidade/parametros")
async def qualidade_parametros():
    return {"items": [{"id": k, **v} for k, v in PARAMETROS.items()],
            "referencia": "Portaria GM/MS nº 888/2021 (substituiu a 2.914/2011)"}


@app.get("/api/qualidade/pontos")
async def qualidade_pontos():
    async with aiosqlite.connect(DB_PATH) as conn:
        return {"items": await list_pontos(conn)}


@app.post("/api/qualidade/pontos")
async def qualidade_ponto_novo(body: PontoRequest, user: dict = Depends(require_supervisor)):
    nome = body.nome.strip()
    if not nome:
        raise HTTPException(400, "Informe o nome do ponto")
    async with aiosqlite.connect(DB_PATH) as conn:
        try:
            cur = await conn.execute("INSERT INTO pontos_coleta (nome, reservatorio) VALUES (?, ?)", (nome, body.reservatorio))
            await conn.commit()
        except aiosqlite.IntegrityError:
            raise HTTPException(409, "Já existe ponto com esse nome")
        await _audit(conn, "ponto_coleta", nome, "ponto_criado", f"Ponto de coleta criado: {nome}", user["name"])
    return {"id": cur.lastrowid}


@app.get("/api/qualidade/laudos")
async def qualidade_laudos(ponto_id: Optional[int] = Query(None), limit: int = Query(100, ge=1, le=500)):
    async with aiosqlite.connect(DB_PATH) as conn:
        return {"items": await list_laudos(conn, ponto_id=ponto_id, limit=limit)}


@app.post("/api/qualidade/laudos")
async def qualidade_laudo_novo(body: LaudoRequest, user: dict = Depends(require_supervisor)):
    try:
        datetime.date.fromisoformat(body.data_coleta)
    except ValueError:
        raise HTTPException(400, "data_coleta deve ser AAAA-MM-DD")
    if not body.laboratorio.strip():
        raise HTTPException(400, "Informe o laboratório")
    if not body.parametros:
        raise HTTPException(400, "Informe ao menos um parâmetro")
    unknown = [p.parametro for p in body.parametros if p.parametro not in PARAMETROS]
    if unknown:
        raise HTTPException(400, f"Parâmetro desconhecido: {', '.join(unknown)}")
    arquivo = None
    if body.pdf_base64:
        try:
            pdf = base64.b64decode(body.pdf_base64.split(",")[-1], validate=True)
        except ValueError:
            raise HTTPException(400, "PDF inválido")
        if not pdf.startswith(b"%PDF") or len(pdf) > MAX_PDF_BYTES:
            raise HTTPException(400, "Envie um PDF de até 10 MB")
        laudos_dir = DATA_DIR / "laudos"
        laudos_dir.mkdir(parents=True, exist_ok=True)
        arquivo = f"{uuid.uuid4().hex}.pdf"
        (laudos_dir / arquivo).write_bytes(pdf)
    resultados = []
    for p in body.parametros:
        ref = PARAMETROS[p.parametro]
        resultados.append({"parametro": p.parametro, "valor": p.valor, "unidade": ref["unidade"],
                           "limite_min": ref["min"], "limite_max": ref["max"], "conforme": conforme(p.parametro, p.valor)})
    async with aiosqlite.connect(DB_PATH) as conn:
        pontos = {pt["id"]: pt for pt in await list_pontos(conn)}
        if body.ponto_id not in pontos:
            raise HTTPException(400, "Ponto de coleta não existe")
        laudo_id = await insert_laudo(conn, {
            "ponto_id": body.ponto_id, "data_coleta": body.data_coleta, "laboratorio": body.laboratorio.strip(),
            "numero": (body.numero or "").strip() or None, "arquivo": arquivo, "obs": body.obs,
            "criado_ts": int(time.time()), "criado_por": user["name"]}, resultados)
        ponto = pontos[body.ponto_id]["nome"]
        data_br = datetime.date.fromisoformat(body.data_coleta).strftime("%d/%m/%Y")
        ruins = [r for r in resultados if not r["conforme"]]
        await _audit(conn, "ponto_coleta", ponto, "laudo_registrado",
                     f"Laudo {body.numero or laudo_id} de {data_br} ({body.laboratorio.strip()}): "
                     + ("conforme" if not ruins else f"{len(ruins)} parâmetro(s) fora do limite"), user["name"],
                     tipo="informativo")
    # Não conforme abre alerta sanitário; resultado conforme do mesmo ponto/parâmetro normaliza (§10.3)
    if alarms:
        for r in resultados:
            nome = PARAMETROS[r["parametro"]]["nome"]
            key = f"{ponto} · {nome}"
            if r["conforme"]:
                await alarms.close_alarm(key, "laudo_nao_conforme", f"{key}: voltou a conforme no laudo de {data_br}")
            else:
                lim = " a ".join(f"{v:g}" for v in (r["limite_min"], r["limite_max"]) if v is not None)
                await alarms.open_alarm({"tipo": "alarme", "severidade": "critico", "entidade": "ponto_coleta",
                                         "entidade_id": key, "codigo": "laudo_nao_conforme", "valor": r["valor"],
                                         "descricao": f"{key}: {r['valor']:g} {r['unidade']} fora do limite ({lim}) — laudo de {data_br}"})
    return {"id": laudo_id, "conforme": not ruins}


@app.get("/api/qualidade/laudos/{laudo_id}/pdf")
async def qualidade_laudo_pdf(laudo_id: int):
    async with aiosqlite.connect(DB_PATH) as conn:
        arquivo = await get_laudo_arquivo(conn, laudo_id)
    path = DATA_DIR / "laudos" / (arquivo or "")
    if not arquivo or not path.is_file():
        raise HTTPException(404, "Laudo sem PDF")
    return FileResponse(path, media_type="application/pdf", filename=f"laudo-{laudo_id}.pdf")


# ── Indicadores (Normas §8.3, §11) ───────────────────────────────

@app.get("/api/indicadores")
async def indicadores(days: int = Query(30, ge=1, le=180)):
    async with aiosqlite.connect(DB_PATH) as conn:
        return await calc_kpis(conn, days, alarms.limits_for if alarms else (lambda a: LIMITS))


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    await ws_manager.send_snapshot(ws)
    ws_manager._clients.append(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "xAguada"}


# Serve o frontend estático (SPA). Deve ficar após todas as rotas /api e /ws.
_FRONTEND_DIR = PROJECT_ROOT / "frontend"
if _FRONTEND_DIR.is_dir():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = _FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIR / "index.html"))
