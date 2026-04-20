# backend/main.py
import asyncio
import json
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

import aiosqlite
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
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

from .bridge import Bridge, RESERVOIR_INDEX
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
)
from .calc import calc_consumption_events, decimate_readings
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

    def broadcast(self, data: dict):
        """Chamado pela bridge thread — agenda envio no loop asyncio principal."""
        if self._loop is None:
            return
        msg = json.dumps({"type": "reading", "data": data})
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
        await ws.send_text(json.dumps({"type": "snapshot", "data": states}))


ws_manager = WSManager()
bridge: Optional[Bridge] = None
scheduler: Optional[AsyncIOScheduler] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global bridge, scheduler, DATA_DIR, DB_PATH, REPORTS_DIR
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

    loop = asyncio.get_running_loop()
    ws_manager.set_loop(loop)

    bridge = Bridge(db_path=DB_PATH, notify_cb=ws_manager.broadcast)
    bridge.start(loop)

    scheduler = AsyncIOScheduler(timezone=os.getenv("TZ", "America/Sao_Paulo"))
    scheduler.add_job(_daily_report_job, "cron", hour=6, minute=0)
    scheduler.start()

    yield

    scheduler.shutdown()


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


class ReportDailyDataRequest(BaseModel):
    date: str
    electrician: Optional[str] = ""
    ose: Optional[str] = ""
    volume_rows: list[dict] = Field(default_factory=list)
    hydrometer_rows: list[dict] = Field(default_factory=list)
    pump_rows: list[dict] = Field(default_factory=list)
    valve_rows: list[dict] = Field(default_factory=list)


@app.get("/api/reservoirs")
async def get_reservoirs():
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        states = await get_all_states(conn)
    # Enriquecer com lat/lng e capacity_l do reservoirs.yaml via RESERVOIR_INDEX
    alias_to_meta: dict[str, dict] = {}
    for params in RESERVOIR_INDEX.values():
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
async def put_report_data_route(body: ReportDailyDataRequest):
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


# Build alias → params index from RESERVOIR_INDEX for manual readings
_ALIAS_PARAMS: dict[str, dict] = {}
for (_nid, _sid), _p in RESERVOIR_INDEX.items():
    _ALIAS_PARAMS[_p["alias"]] = {**_p, "node_id": _nid, "sensor_id": _sid}


@app.post("/api/readings/manual")
async def post_manual_reading(body: ManualReadingRequest):
    alias = body.alias.upper()
    params = _ALIAS_PARAMS.get(alias)
    if params is None:
        raise HTTPException(400, f"Alias '{alias}' não encontrado")

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
        "node_id": params["node_id"],
        "sensor_id": params["sensor_id"],
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

    return {"ok": True, "alias": alias, "volume_l": volume_l, "pct": pct, "level_cm": level_cm}


@app.post("/api/manual/hydrometers")
async def post_manual_hydrometer(body: ManualHydrometerRequest):
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
        await insert_manual_hydrometer_reading(conn, item)
    return {"ok": True, **item}


@app.get("/api/manual/hydrometers")
async def get_manual_hydrometers(meter_name: Optional[str] = Query(None), limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_hydrometer_history(conn, meter_name=meter_name, limit=limit)
    return {"items": rows}


@app.post("/api/manual/pumps")
async def post_manual_pump(body: ManualPumpRequest):
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
        await insert_manual_pump_log(conn, item)
    return {"ok": True, **item}


@app.get("/api/manual/pumps")
async def get_manual_pumps(limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_pump_logs(conn, limit=limit)
    return {"items": rows}


@app.post("/api/manual/valves")
async def post_manual_valve(body: ManualValveRequest):
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
        await insert_manual_valve_log(conn, item)
    return {"ok": True, **item}


@app.get("/api/manual/valves")
async def get_manual_valves(limit: int = Query(200, ge=1, le=1000)):
    async with aiosqlite.connect(DB_PATH) as conn:
        conn.row_factory = aiosqlite.Row
        rows = await get_manual_valve_logs(conn, limit=limit)
    return {"items": rows}


@app.post("/api/manual/reservoirs")
async def post_manual_reservoir(body: ManualReservoirRequest):
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
async def post_report_note(body: ReportNoteRequest):
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
async def archive_report_note_route(note_id: int):
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
async def patch_node_meta(node_id: str, body: dict):
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
async def post_node_cmd(node_id: str, body: dict):
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


# Serve o frontend estático (SPA). Deve ficar após todas as rotas /api e /ws.
_FRONTEND_DIR = PROJECT_ROOT / "frontend"
if _FRONTEND_DIR.is_dir():
    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        candidate = _FRONTEND_DIR / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        return FileResponse(str(_FRONTEND_DIR / "index.html"))
