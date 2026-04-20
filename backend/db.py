# backend/db.py
"""Acesso ao SQLite — schema, inserts, queries. Sem lógica de negócio."""
import json
import logging
import time
import aiosqlite

logger = logging.getLogger("db")

INVALID_VALVE_PREFIXES = ("VALV-IE-INTERLI",)

# Nó considerado ONLINE se o último pacote chegou há menos de X segundos.
# Intervalo padrão dos nós = 120s; 5 intervalos perdidos = offline.
ONLINE_TIMEOUT_S = 600

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          INTEGER NOT NULL,
    node_id     TEXT    NOT NULL,
    sensor_id   INTEGER NOT NULL,
    alias       TEXT    NOT NULL,
    distance_cm REAL,
    level_cm    REAL,
    volume_l    REAL,
    pct         REAL,
    rssi        INTEGER,
    vbat        REAL,
    seq         INTEGER
);
CREATE INDEX IF NOT EXISTS idx_readings_ts    ON readings(ts DESC);
CREATE INDEX IF NOT EXISTS idx_readings_alias ON readings(alias, ts DESC);

CREATE TABLE IF NOT EXISTS reservoir_state (
    alias        TEXT PRIMARY KEY,
    node_id      TEXT,
    sensor_id    INTEGER,
    name         TEXT,
    ts           INTEGER,
    level_cm     REAL,
    volume_l     REAL,
    pct          REAL,
    level_max_cm REAL,
    volume_max_l REAL,
    rssi         INTEGER,
    online       INTEGER DEFAULT 1,
    out_of_range INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS manual_hydrometer_readings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           INTEGER NOT NULL,
    meter_name   TEXT    NOT NULL,
    reading      REAL    NOT NULL,
    unit         TEXT    NOT NULL DEFAULT 'm3',
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_hydrometer_ts ON manual_hydrometer_readings(ts DESC);
CREATE INDEX IF NOT EXISTS idx_manual_hydrometer_name_ts ON manual_hydrometer_readings(meter_name, ts DESC);

CREATE TABLE IF NOT EXISTS manual_pump_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           INTEGER NOT NULL,
    pump_name    TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    operational_status TEXT,
    mode         TEXT    NOT NULL DEFAULT 'manual',
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_pump_ts ON manual_pump_logs(ts DESC);

CREATE TABLE IF NOT EXISTS manual_valve_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           INTEGER NOT NULL,
    valve_name   TEXT    NOT NULL,
    state        TEXT    NOT NULL,
    note         TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_valve_ts ON manual_valve_logs(ts DESC);

CREATE TABLE IF NOT EXISTS nodes (
    node_id     TEXT    PRIMARY KEY,
    alias       TEXT,
    name        TEXT,
    num_sensors INTEGER DEFAULT 0,
    fw_version  TEXT,
    last_seen   INTEGER,
    last_rssi   INTEGER,
    last_vbat   REAL,
    flags       INTEGER DEFAULT 0,
    note        TEXT
);

CREATE TABLE IF NOT EXISTS manual_reservoir_logs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    ts             INTEGER NOT NULL,
    reservoir_name TEXT    NOT NULL,
    has_sensor     INTEGER NOT NULL DEFAULT 0,
    level_cm       REAL,
    volume_l       REAL,
    pct            REAL,
    note           TEXT
);
CREATE INDEX IF NOT EXISTS idx_manual_reservoir_ts ON manual_reservoir_logs(ts DESC);

CREATE TABLE IF NOT EXISTS report_notes (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    date         TEXT    NOT NULL,
    note         TEXT    NOT NULL,
    created_ts   INTEGER NOT NULL,
    archived_ts  INTEGER
);
CREATE INDEX IF NOT EXISTS idx_report_notes_date_archived ON report_notes(date, archived_ts, created_ts DESC);

CREATE TABLE IF NOT EXISTS report_daily_data (
    date                TEXT PRIMARY KEY,
    electrician         TEXT,
    ose                 TEXT,
    volume_rows_json    TEXT,
    hydrometer_rows_json TEXT,
    pump_rows_json      TEXT,
    valve_rows_json     TEXT,
    updated_ts          INTEGER NOT NULL
);
"""


def is_supported_valve_name(name: str | None) -> bool:
    normalized = (name or "").strip().upper()
    if not normalized:
        return False
    return not any(normalized.startswith(prefix) for prefix in INVALID_VALVE_PREFIXES)


def _filter_supported_valve_rows(rows: list[dict]) -> list[dict]:
    return [row for row in rows if is_supported_valve_name(row.get("valve_name"))]

async def init_db(conn: aiosqlite.Connection) -> None:
    await conn.executescript(SCHEMA)
    # Migration: add out_of_range column if missing (existing databases without it)
    try:
        await conn.execute(
            "ALTER TABLE reservoir_state ADD COLUMN out_of_range INTEGER DEFAULT 0"
        )
    except Exception:
        pass  # column already exists
    try:
        await conn.execute(
            "ALTER TABLE manual_pump_logs ADD COLUMN operational_status TEXT"
        )
    except Exception:
        pass  # column already exists
    await conn.commit()
    conn.row_factory = aiosqlite.Row


async def upsert_node(conn: aiosqlite.Connection, node: dict) -> None:
    """Insert or update node record from a HELLO packet. Never overwrites alias/name/note."""
    await conn.execute(
        """INSERT INTO nodes (node_id, num_sensors, fw_version, last_seen, last_rssi, last_vbat, flags)
           VALUES (:node_id, :num_sensors, :fw_version, :last_seen, :last_rssi, :last_vbat, :flags)
           ON CONFLICT(node_id) DO UPDATE SET
               num_sensors=excluded.num_sensors,
               fw_version=COALESCE(excluded.fw_version, nodes.fw_version),
               last_seen=excluded.last_seen,
               last_rssi=excluded.last_rssi,
               last_vbat=excluded.last_vbat,
               flags=excluded.flags""",
        node,
    )
    await conn.commit()


async def upsert_node_seen(conn: aiosqlite.Connection, node_id: str, sensor_id: int,
                           last_seen: int, last_rssi, last_vbat, flags: int) -> None:
    """Update node telemetry from a SENSOR packet.
    On first-ever SENSOR: creates the row with num_sensors=sensor_id (lower bound).
    On conflict: updates only last_seen/rssi/vbat/flags and bumps num_sensors if sensor_id
    is higher than stored value. Never touches alias/name/note/fw_version.
    """
    await conn.execute(
        """INSERT INTO nodes (node_id, num_sensors, fw_version, last_seen, last_rssi, last_vbat, flags)
           VALUES (:node_id, :num_sensors, NULL, :last_seen, :last_rssi, :last_vbat, :flags)
           ON CONFLICT(node_id) DO UPDATE SET
               num_sensors=MAX(nodes.num_sensors, excluded.num_sensors),
               last_seen=excluded.last_seen,
               last_rssi=excluded.last_rssi,
               last_vbat=excluded.last_vbat,
               flags=excluded.flags""",
        {"node_id": node_id, "num_sensors": sensor_id,
         "last_seen": last_seen, "last_rssi": last_rssi,
         "last_vbat": last_vbat, "flags": flags},
    )
    await conn.commit()


async def patch_node(conn: aiosqlite.Connection, node_id: str, fields: dict) -> bool:
    """Update editable node fields (alias, name, note). Returns False if node not found."""
    allowed = {"alias", "name", "note"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    set_clause = ", ".join(f"{k}=:{k}" for k in updates)
    updates["node_id"] = node_id
    cur = await conn.execute(
        f"UPDATE nodes SET {set_clause} WHERE node_id=:node_id", updates
    )
    await conn.commit()
    return cur.rowcount > 0


async def get_all_nodes(conn: aiosqlite.Connection) -> list[dict]:
    now = int(time.time())
    async with conn.execute("SELECT * FROM nodes ORDER BY last_seen DESC NULLS LAST") as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["online"] = (now - (d["last_seen"] or 0)) < ONLINE_TIMEOUT_S
        result.append(d)
    return result


async def get_node(conn: aiosqlite.Connection, node_id: str) -> dict | None:
    now = int(time.time())
    async with conn.execute("SELECT * FROM nodes WHERE node_id=?", (node_id,)) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    d = dict(row)
    d["online"] = (now - (d["last_seen"] or 0)) < ONLINE_TIMEOUT_S
    return d


async def insert_reading(conn: aiosqlite.Connection, r: dict) -> None:
    await conn.execute(
        """INSERT INTO readings
           (ts, node_id, sensor_id, alias, distance_cm, level_cm, volume_l, pct, rssi, vbat, seq)
           VALUES (:ts, :node_id, :sensor_id, :alias, :distance_cm, :level_cm, :volume_l,
                   :pct, :rssi, :vbat, :seq)""",
        r,
    )
    await conn.commit()


async def upsert_state(conn: aiosqlite.Connection, s: dict) -> None:
    row = dict(s)
    row.setdefault("out_of_range", False)
    cur = await conn.execute(
        """INSERT INTO reservoir_state
           (alias, node_id, sensor_id, name, ts, level_cm, volume_l, pct,
            level_max_cm, volume_max_l, rssi, out_of_range)
           VALUES (:alias, :node_id, :sensor_id, :name, :ts, :level_cm, :volume_l, :pct,
                   :level_max_cm, :volume_max_l, :rssi, :out_of_range)
           ON CONFLICT(alias) DO UPDATE SET
               node_id=excluded.node_id, sensor_id=excluded.sensor_id,
               name=excluded.name,
               ts=excluded.ts, level_cm=excluded.level_cm, volume_l=excluded.volume_l,
               pct=excluded.pct, rssi=excluded.rssi,
               level_max_cm=excluded.level_max_cm, volume_max_l=excluded.volume_max_l,
               out_of_range=excluded.out_of_range
           WHERE excluded.ts >= reservoir_state.ts""",
        row,
    )
    if cur.rowcount == 0:
        # A cláusula WHERE bloqueou a atualização: o ts recebido é mais antigo que o armazenado.
        # Isso pode indicar que o gateway enviou ts sem sincronização (SETTIME não recebido).
        logger.warning(
            "upsert_state bloqueado (ts muito antigo): alias=%s ts_recebido=%s",
            s.get("alias"), s.get("ts"),
        )
    await conn.commit()


async def get_all_states(conn: aiosqlite.Connection) -> list[dict]:
    now = int(time.time())
    async with conn.execute("SELECT * FROM reservoir_state") as cur:
        rows = await cur.fetchall()
    result = []
    for row in rows:
        d = dict(row)
        d["online"] = (now - (d["ts"] or 0)) < ONLINE_TIMEOUT_S
        result.append(d)
    return result


async def get_history(
    conn: aiosqlite.Connection, alias: str, since_ts: int, until_ts: int | None = None
) -> list[dict]:
    query = """SELECT ts, distance_cm, level_cm, volume_l, pct, rssi, vbat, seq
           FROM readings
           WHERE alias=? AND ts>=?"""
    params: tuple = (alias, since_ts)
    if until_ts is not None:
        query += " AND ts<?"
        params = (alias, since_ts, until_ts)
    query += " ORDER BY ts ASC"
    async with conn.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_readings_for_date(
    conn: aiosqlite.Connection, alias: str, date_str: str
) -> list[dict]:
    """Retorna todas as leituras de um alias em um dia (YYYY-MM-DD, fuso local do servidor)."""
    import datetime
    day = datetime.date.fromisoformat(date_str)
    ts_start = int(datetime.datetime(day.year, day.month, day.day, 0, 0, 0).timestamp())
    ts_end = ts_start + 86400
    async with conn.execute(
        """SELECT ts, distance_cm, volume_l, level_cm, pct, rssi, vbat, seq
           FROM readings
           WHERE alias=? AND ts>=? AND ts<?
           ORDER BY ts ASC""",
        (alias, ts_start, ts_end),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def insert_manual_hydrometer_reading(conn: aiosqlite.Connection, item: dict) -> None:
    await conn.execute(
        """INSERT INTO manual_hydrometer_readings (ts, meter_name, reading, unit, note)
           VALUES (:ts, :meter_name, :reading, :unit, :note)""",
        item,
    )
    await conn.commit()


async def insert_manual_pump_log(conn: aiosqlite.Connection, item: dict) -> None:
    await conn.execute(
        """INSERT INTO manual_pump_logs (ts, pump_name, state, operational_status, mode, note)
           VALUES (:ts, :pump_name, :state, :operational_status, :mode, :note)""",
        item,
    )
    await conn.commit()


async def insert_manual_valve_log(conn: aiosqlite.Connection, item: dict) -> None:
    await conn.execute(
        """INSERT INTO manual_valve_logs (ts, valve_name, state, note)
           VALUES (:ts, :valve_name, :state, :note)""",
        item,
    )
    await conn.commit()


async def insert_manual_reservoir_log(conn: aiosqlite.Connection, item: dict) -> None:
    await conn.execute(
        """INSERT INTO manual_reservoir_logs (ts, reservoir_name, has_sensor, level_cm, volume_l, pct, note)
           VALUES (:ts, :reservoir_name, :has_sensor, :level_cm, :volume_l, :pct, :note)""",
        item,
    )
    await conn.commit()


async def get_manual_hydrometer_history(conn: aiosqlite.Connection, meter_name: str | None = None, limit: int = 200) -> list[dict]:
    if meter_name:
        async with conn.execute(
            """SELECT ts, meter_name, reading, unit, note
               FROM manual_hydrometer_readings
               WHERE meter_name=?
               ORDER BY ts DESC
               LIMIT ?""",
            (meter_name, limit),
        ) as cur:
            rows = await cur.fetchall()
    else:
        async with conn.execute(
            """SELECT ts, meter_name, reading, unit, note
               FROM manual_hydrometer_readings
               ORDER BY ts DESC
               LIMIT ?""",
            (limit,),
        ) as cur:
            rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_manual_pump_logs(conn: aiosqlite.Connection, limit: int = 200) -> list[dict]:
    async with conn.execute(
        """SELECT ts, pump_name, state, operational_status, mode, note
           FROM manual_pump_logs
           ORDER BY ts DESC
           LIMIT ?""",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_manual_valve_logs(conn: aiosqlite.Connection, limit: int = 200) -> list[dict]:
    async with conn.execute(
        """SELECT ts, valve_name, state, note
           FROM manual_valve_logs
           ORDER BY ts DESC
           LIMIT ?""",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return _filter_supported_valve_rows([dict(r) for r in rows])


async def get_manual_reservoir_logs(conn: aiosqlite.Connection, limit: int = 200) -> list[dict]:
    async with conn.execute(
        """SELECT ts, reservoir_name, has_sensor, level_cm, volume_l, pct, note
           FROM manual_reservoir_logs
           ORDER BY ts DESC
           LIMIT ?""",
        (limit,),
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_latest_pump_states(conn: aiosqlite.Connection) -> list[dict]:
    """Retorna o estado mais recente de cada bomba (uma linha por bomba)."""
    async with conn.execute(
        """SELECT p.id, p.ts, p.pump_name, p.state, p.operational_status, p.mode, p.note
           FROM manual_pump_logs p
           INNER JOIN (
               SELECT pump_name, MAX(id) AS max_id
               FROM manual_pump_logs
               GROUP BY pump_name
           ) latest ON p.id = latest.max_id
           ORDER BY p.pump_name"""
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_latest_valve_states(conn: aiosqlite.Connection) -> list[dict]:
    """Retorna o estado mais recente de cada válvula (uma linha por válvula)."""
    async with conn.execute(
        """SELECT v.id, v.ts, v.valve_name, v.state, v.note
           FROM manual_valve_logs v
           INNER JOIN (
               SELECT valve_name, MAX(id) AS max_id
               FROM manual_valve_logs
               GROUP BY valve_name
           ) latest ON v.id = latest.max_id
           ORDER BY v.valve_name"""
    ) as cur:
        rows = await cur.fetchall()
    return _filter_supported_valve_rows([dict(r) for r in rows])


async def get_latest_hydrometer_readings(conn: aiosqlite.Connection) -> list[dict]:
    """Retorna a leitura mais recente de cada hidrômetro (uma linha por hidrômetro)."""
    async with conn.execute(
        """SELECT h.id, h.ts, h.meter_name, h.reading, h.unit, h.note
           FROM manual_hydrometer_readings h
           INNER JOIN (
               SELECT meter_name, MAX(id) AS max_id
               FROM manual_hydrometer_readings
               GROUP BY meter_name
           ) latest ON h.id = latest.max_id
           ORDER BY h.meter_name"""
    ) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def get_pump_states_for_date(conn: aiosqlite.Connection, date_str: str) -> list[dict]:
    """Retorna o último estado de cada bomba como de fim do dia (para relatório)."""
    import datetime
    day = datetime.date.fromisoformat(date_str)
    ts_end = int(datetime.datetime(day.year, day.month, day.day, 23, 59, 59).timestamp())
    async with conn.execute(
        "SELECT DISTINCT pump_name FROM manual_pump_logs ORDER BY pump_name"
    ) as cur:
        names = [r[0] for r in await cur.fetchall()]
    out: list[dict] = []
    for name in names:
        async with conn.execute(
            """SELECT ts, pump_name, state, operational_status, mode, note FROM manual_pump_logs
               WHERE pump_name=? AND ts<=? ORDER BY ts DESC LIMIT 1""",
            (name, ts_end),
        ) as cur:
            row = await cur.fetchone()
        if row:
            out.append(dict(row))
    return out


async def get_valve_states_for_date(conn: aiosqlite.Connection, date_str: str) -> list[dict]:
    """Retorna o último estado de cada válvula como de fim do dia (para relatório)."""
    import datetime
    day = datetime.date.fromisoformat(date_str)
    ts_end = int(datetime.datetime(day.year, day.month, day.day, 23, 59, 59).timestamp())
    async with conn.execute(
        "SELECT DISTINCT valve_name FROM manual_valve_logs ORDER BY valve_name"
    ) as cur:
        names = [r[0] for r in await cur.fetchall() if is_supported_valve_name(r[0])]
    out: list[dict] = []
    for name in names:
        async with conn.execute(
            """SELECT ts, valve_name, state, note FROM manual_valve_logs
               WHERE valve_name=? AND ts<=? ORDER BY ts DESC LIMIT 1""",
            (name, ts_end),
        ) as cur:
            row = await cur.fetchone()
        if row:
            out.append(dict(row))
    return out


async def get_manual_hydrometer_summary_for_date(conn: aiosqlite.Connection, date_str: str) -> list[dict]:
    """Retorna anterior/atual/diferença por hidrômetro para a data (base em ts unix local)."""
    import datetime
    day = datetime.date.fromisoformat(date_str)
    ts_start = int(datetime.datetime(day.year, day.month, day.day, 0, 0, 0).timestamp())
    ts_end = ts_start + 86400

    async with conn.execute("SELECT DISTINCT meter_name FROM manual_hydrometer_readings ORDER BY meter_name") as cur:
        meters = [r[0] for r in await cur.fetchall()]

    out: list[dict] = []
    for meter_name in meters:
        async with conn.execute(
            """SELECT reading, unit FROM manual_hydrometer_readings
               WHERE meter_name=? AND ts < ?
               ORDER BY ts DESC LIMIT 1""",
            (meter_name, ts_start),
        ) as cur:
            prev = await cur.fetchone()

        async with conn.execute(
            """SELECT reading, unit FROM manual_hydrometer_readings
               WHERE meter_name=? AND ts < ?
               ORDER BY ts DESC LIMIT 1""",
            (meter_name, ts_end),
        ) as cur:
            curr = await cur.fetchone()

        prev_val = float(prev[0]) if prev else None
        curr_val = float(curr[0]) if curr else None
        diff = (curr_val - prev_val) if (prev_val is not None and curr_val is not None) else None
        unit = (curr[1] if curr else (prev[1] if prev else "m3"))

        out.append({
            "meter_name": meter_name,
            "previous": prev_val,
            "current": curr_val,
            "diff": diff,
            "unit": unit,
        })

    return out


async def insert_report_note(conn: aiosqlite.Connection, item: dict) -> int:
    cur = await conn.execute(
        """INSERT INTO report_notes (date, note, created_ts, archived_ts)
           VALUES (:date, :note, :created_ts, NULL)""",
        item,
    )
    await conn.commit()
    return int(cur.lastrowid)


async def get_report_notes(conn: aiosqlite.Connection, date_str: str, active_only: bool = True) -> list[dict]:
    query = """SELECT id, date, note, created_ts, archived_ts
       FROM report_notes
       WHERE date=?"""
    params: tuple = (date_str,)
    if active_only:
        query += " AND archived_ts IS NULL"
    query += " ORDER BY created_ts DESC, id DESC"
    async with conn.execute(query, params) as cur:
        rows = await cur.fetchall()
    return [dict(r) for r in rows]


async def archive_report_note(conn: aiosqlite.Connection, note_id: int, archived_ts: int) -> bool:
    cur = await conn.execute(
        "UPDATE report_notes SET archived_ts=? WHERE id=? AND archived_ts IS NULL",
        (archived_ts, note_id),
    )
    await conn.commit()
    return cur.rowcount > 0


def _decode_json_field(raw_value: str | None, fallback):
    if not raw_value:
        return fallback
    try:
        return json.loads(raw_value)
    except Exception:
        return fallback


async def get_report_daily_data(conn: aiosqlite.Connection, date_str: str) -> dict | None:
    async with conn.execute(
        """SELECT date, electrician, ose, volume_rows_json, hydrometer_rows_json,
                  pump_rows_json, valve_rows_json, updated_ts
           FROM report_daily_data
           WHERE date=?""",
        (date_str,),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        return None
    data = dict(row)
    return {
        "date": data["date"],
        "electrician": data.get("electrician") or "",
        "ose": data.get("ose") or "",
        "volume_rows": _decode_json_field(data.get("volume_rows_json"), []),
        "hydrometer_rows": _decode_json_field(data.get("hydrometer_rows_json"), []),
        "pump_rows": _decode_json_field(data.get("pump_rows_json"), []),
        "valve_rows": _decode_json_field(data.get("valve_rows_json"), []),
        "updated_ts": data["updated_ts"],
    }


async def upsert_report_daily_data(conn: aiosqlite.Connection, item: dict) -> None:
    payload = {
        "date": item["date"],
        "electrician": (item.get("electrician") or "").strip(),
        "ose": (item.get("ose") or "").strip(),
        "volume_rows_json": json.dumps(item.get("volume_rows") or [], ensure_ascii=False),
        "hydrometer_rows_json": json.dumps(item.get("hydrometer_rows") or [], ensure_ascii=False),
        "pump_rows_json": json.dumps(item.get("pump_rows") or [], ensure_ascii=False),
        "valve_rows_json": json.dumps(item.get("valve_rows") or [], ensure_ascii=False),
        "updated_ts": int(item.get("updated_ts") or time.time()),
    }
    await conn.execute(
        """INSERT INTO report_daily_data (
               date, electrician, ose, volume_rows_json, hydrometer_rows_json,
               pump_rows_json, valve_rows_json, updated_ts
           ) VALUES (
               :date, :electrician, :ose, :volume_rows_json, :hydrometer_rows_json,
               :pump_rows_json, :valve_rows_json, :updated_ts
           )
           ON CONFLICT(date) DO UPDATE SET
               electrician=excluded.electrician,
               ose=excluded.ose,
               volume_rows_json=excluded.volume_rows_json,
               hydrometer_rows_json=excluded.hydrometer_rows_json,
               pump_rows_json=excluded.pump_rows_json,
               valve_rows_json=excluded.valve_rows_json,
               updated_ts=excluded.updated_ts""",
        payload,
    )
    await conn.commit()
