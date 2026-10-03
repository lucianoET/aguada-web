# backend/indicadores.py
"""Conciliação reservatórios × hidrômetros (Normas §8.3) e KPIs operacionais (§11, NBR ISO 24510).

Dia = fuso local do servidor, como em get_readings_for_date.
"""
from __future__ import annotations

import datetime
import statistics
from collections import defaultdict

import aiosqlite

from .calc import calc_consumption_events
from .db import get_readings_for_date

# ponytail: knob — acima disso a diferença entre o que saiu e o que foi medido vira alerta (§10.3)
DISCREP_PCT = 10.0

# O mesmo hidrômetro aparece com grafias diferentes nos lançamentos antigos
METER_NAMES = {"HID-AVAZ": ("HID-AVAZ", "HID-AV|AZ", "HID-AV/AZ")}

# a = o que saiu (enviado/distribuído), b = o que foi medido na chegada; perda aparente = a − b
PARES = [
    {"id": "con", "nome": "Saída do CON × HID-AV/AZ", "a": ("res", ["CON"]), "b": ("hid", ["HID-AVAZ"])},
    {"id": "avaz", "nome": "HID-AV/AZ × (HID-AV + HID-AZ)", "a": ("hid", ["HID-AVAZ"]), "b": ("hid", ["HID-AV", "HID-AZ"])},
    {"id": "sub", "nome": "Linha submarina: HID-IF × HID-PRAIA", "a": ("hid", ["HID-IF"]), "b": ("hid", ["HID-PRAIA"])},
]


def day_bounds(day: datetime.date) -> tuple[int, int]:
    start = int(datetime.datetime(day.year, day.month, day.day).timestamp())
    return start, start + 86400


async def _meter_rows(conn: aiosqlite.Connection, meter: str) -> list[tuple[int, float]]:
    names = METER_NAMES.get(meter, (meter,))
    async with conn.execute(
        f"SELECT ts, reading FROM manual_hydrometer_readings WHERE meter_name IN ({','.join('?' * len(names))}) ORDER BY ts, id",
        names,
    ) as cur:
        return [(r[0], r[1]) for r in await cur.fetchall()]


def meter_day_m3(rows: list[tuple[int, float]], day: datetime.date) -> float | None:
    """Consumo do dia = última leitura até o fim do dia − última leitura até o início."""
    start, end = day_bounds(day)
    before = [r for t, r in rows if t <= start]
    until = [r for t, r in rows if t <= end]
    if not before or not until or len(until) == len(before):
        return None  # sem leitura nova dentro do dia
    return round(until[-1] - before[-1], 3)


async def _reservoir_day_m3(conn: aiosqlite.Connection, alias: str, day: datetime.date) -> float | None:
    readings = await get_readings_for_date(conn, alias=alias, date_str=day.isoformat())
    if len(readings) < 2:
        return None
    events = calc_consumption_events(readings, date=day.isoformat())
    return round(sum(abs(e["delta_l"]) for e in events if e["type"] == "consumption") / 1000, 3)


async def conciliacao(conn: aiosqlite.Connection, days: int = 7, until: datetime.date | None = None) -> list[dict]:
    conn.row_factory = aiosqlite.Row
    until = until or datetime.date.today() - datetime.timedelta(days=1)   # último dia fechado
    meters = {m: await _meter_rows(conn, m) for p in PARES for kind, names in (p["a"], p["b"]) if kind == "hid" for m in names}
    out = []
    for i in range(days):
        day = until - datetime.timedelta(days=i)
        row = {"data": day.isoformat(), "pares": []}
        for par in PARES:
            vals = []
            for kind, names in (par["a"], par["b"]):
                parts = [await _reservoir_day_m3(conn, n, day) if kind == "res" else meter_day_m3(meters[n], day) for n in names]
                vals.append(None if any(v is None for v in parts) else round(sum(parts), 3))
            a, b = vals
            if a is None or b is None:
                status, diff, pct = "sem_dado", None, None
            else:
                diff = round(a - b, 3)
                pct = round(diff / a * 100, 1) if a else None
                status = "inconsistente" if pct is not None and abs(pct) > DISCREP_PCT else "ok"
            row["pares"].append({"id": par["id"], "nome": par["nome"], "a_m3": a, "b_m3": b, "diff_m3": diff, "diff_pct": pct, "status": status})
        out.append(row)
    return out


async def kpis(conn: aiosqlite.Connection, days: int, limits_for) -> dict:
    """KPIs da §11 para os últimos `days` dias (inclui hoje até agora)."""
    conn.row_factory = aiosqlite.Row
    end = int(datetime.datetime.now().timestamp())
    start = day_bounds(datetime.date.today() - datetime.timedelta(days=days - 1))[0]
    total_h = max(1, (end - start) // 3600)

    # Disponibilidade: horas com mediana horária acima do nível crítico do reservatório
    async with conn.execute("SELECT alias, ts, pct FROM readings WHERE ts >= ? AND pct IS NOT NULL", (start,)) as cur:
        hourly: dict[str, dict[int, list]] = defaultdict(lambda: defaultdict(list))
        for r in await cur.fetchall():
            hourly[r["alias"]][r["ts"] // 3600].append(r["pct"])
    async with conn.execute("SELECT alias, name FROM reservoir_state") as cur:
        names = {r["alias"]: r["name"] for r in await cur.fetchall()}
    disponibilidade = []
    for alias in sorted(names):
        hours = hourly.get(alias, {})
        crit = limits_for(alias)["critico"]
        acima = sum(1 for v in hours.values() if statistics.median(v) > crit)
        # pct sobre as horas com leitura; cobertura separa "sensor parado" de "reservatório baixo"
        disponibilidade.append({"alias": alias, "nome": names[alias] or alias, "horas_total": total_h,
                                "horas_com_dado": len(hours), "horas_acima_min": acima,
                                "pct": round(acima / len(hours) * 100, 1) if hours else None,
                                "cobertura_pct": round(len(hours) / total_h * 100, 1), "limite_critico": crit})

    async def scalar(sql: str, *args) -> int:
        async with conn.execute(sql, args) as cur:
            return (await cur.fetchone())[0] or 0

    # Acionamento = registro "ligada" quando o anterior da mesma bomba não era "ligada"
    acionamentos = await scalar(
        """SELECT COUNT(*) FROM (
               SELECT ts, state, LAG(state) OVER (PARTITION BY pump_name ORDER BY ts, id) AS antes
               FROM manual_pump_logs) WHERE ts >= ? AND state = 'ligada' AND (antes IS NULL OR antes != 'ligada')""", start)
    alarmes = await scalar("SELECT COUNT(*) FROM events WHERE ts >= ? AND tipo IN ('alarme', 'falha')", start)
    criticos = await scalar("SELECT COUNT(*) FROM events WHERE ts >= ? AND tipo IN ('alarme', 'falha') AND severidade = 'critico'", start)
    intervencoes = await scalar("SELECT COUNT(*) FROM events WHERE ts >= ? AND usuario IS NOT NULL AND tipo = 'comando'", start)
    nao_conf = await scalar(
        """SELECT COUNT(*) FROM laudo_parametros lp JOIN laudos l ON l.id = lp.laudo_id
           WHERE lp.conforme = 0 AND l.data_coleta >= ?""",
        datetime.date.fromtimestamp(start).isoformat())
    laudos = await scalar("SELECT COUNT(*) FROM laudos WHERE data_coleta >= ?", datetime.date.fromtimestamp(start).isoformat())

    conc = await conciliacao(conn, days=days)
    pares = [p for d in conc for p in d["pares"] if p["status"] != "sem_dado"]
    return {
        "periodo": {"dias": days, "inicio_ts": start, "fim_ts": end},
        "disponibilidade": disponibilidade,
        "acionamentos_bomba": acionamentos,
        "eventos_alarme": alarmes,
        "eventos_criticos": criticos,
        "intervencoes_manuais": intervencoes,
        "laudos": laudos,
        "nao_conformidades": nao_conf,
        "conciliacao": {"dias_conciliados": len(pares), "dias_ok": sum(1 for p in pares if p["status"] == "ok"),
                        "limite_pct": DISCREP_PCT, "dias": conc},
    }
