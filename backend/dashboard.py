# backend/dashboard.py
"""Dados da página de análise (níveis, volume e consumo) — leitura síncrona do SQLite.

Usado por GET /api/dashboard e por tools/build_dashboard.py (HTML autocontido).
"""
from __future__ import annotations

import datetime as dt
import sqlite3
import statistics
from collections import defaultdict

from .calc import calc_consumption_events

ORDER = ["CON", "CAV", "CIE1", "CIE2", "CB31", "CB32", "CBIF1", "CBIF2"]


def median_m3(rows: list[dict]) -> float | None:
    vols = [r["volume_l"] for r in rows if r["volume_l"] is not None]
    return round(statistics.median(vols) / 1000, 2) if vols else None


def build_data(db_path) -> dict:
    # ponytail: varre todas as leituras (~1 s com 110k linhas); filtrar por período no SQL se crescer muito
    conn = sqlite3.connect(db_path)  # só SELECT; mode=ro falha em WAL com o app gravando
    conn.row_factory = sqlite3.Row
    try:
        meta = {r["alias"]: r for r in conn.execute("SELECT alias, name, volume_max_l FROM reservoir_state")}
        aliases = sorted({r[0] for r in conn.execute("SELECT DISTINCT alias FROM readings")},
                         key=lambda a: (ORDER.index(a) if a in ORDER else len(ORDER), a))

        hourly: dict[str, list] = {}
        daily = []
        for alias in aliases:
            rows = [dict(r) for r in conn.execute(
                "SELECT ts, volume_l, pct FROM readings WHERE alias=? ORDER BY ts", (alias,))]
            by_hour: dict[int, list[dict]] = defaultdict(list)
            by_day: dict[str, list[dict]] = defaultdict(list)
            for r in rows:
                by_day[dt.datetime.fromtimestamp(r["ts"]).date().isoformat()].append(r)
                if r["pct"] is not None:
                    by_hour[r["ts"] // 3600 * 3600].append(r)
            # mediana horária: mesmo filtro de ruído que o backend usa no consumo
            # ponto = [ts_ms, pct, volume_m3]
            hourly[alias] = [[h * 1000, round(statistics.median(x["pct"] for x in v), 1), median_m3(v)]
                             for h, v in sorted(by_hour.items())]

            for day, day_rows in sorted(by_day.items()):
                t0 = dt.datetime.fromisoformat(day).timestamp()
                pts = [p for p in hourly[alias] if t0 * 1000 <= p[0] < (t0 + 86400) * 1000]
                pcts = [p[1] for p in pts]
                vols = [p[2] for p in pts if p[2] is not None]
                ev = calc_consumption_events(day_rows, date=day)
                daily.append({
                    "d": day, "a": alias, "n": len(day_rows),
                    "pmin": min(pcts) if pcts else None,
                    "pavg": round(statistics.fmean(pcts), 1) if pcts else None,
                    "pmax": max(pcts) if pcts else None,
                    "vmin": min(vols) if vols else None,
                    "vavg": round(statistics.fmean(vols), 2) if vols else None,
                    "vmax": max(vols) if vols else None,
                    "c": round(sum(abs(e["delta_l"]) for e in ev if e["type"] == "consumption") / 1000, 2),
                    "s": round(sum(e["delta_l"] for e in ev if e["type"] == "supply") / 1000, 2),
                })
    finally:
        conn.close()

    return {
        "generated": dt.datetime.now().strftime("%d/%m/%Y %H:%M"),
        "reservoirs": [{"alias": a, "name": (meta[a]["name"] if a in meta else a),
                        "cap_m3": round((meta[a]["volume_max_l"] or 0) / 1000) if a in meta else None}
                       for a in aliases],
        "hourly": hourly,
        "daily": daily,
    }
