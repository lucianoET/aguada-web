# backend/calc.py
"""Funções puras de cálculo — sem I/O, sem banco."""
from __future__ import annotations
from typing import Optional
from collections import defaultdict
import datetime


def calc_level(
    distance_cm: Optional[float],
    level_max_cm: float,
    sensor_offset_cm: float,
    volume_max_l: float = 0,
) -> dict:
    """Calcula level_cm, pct e volume_l a partir da distância medida."""
    if distance_cm is None:
        return {"level_cm": None, "pct": None, "volume_l": None, "out_of_range": False}

    level = level_max_cm - (distance_cm - sensor_offset_cm)
    out_of_range = level < 0.0 or level > level_max_cm
    level = max(0.0, min(float(level_max_cm), level))
    pct = level / level_max_cm * 100.0
    volume = pct / 100.0 * volume_max_l
    return {
        "level_cm": round(level, 1),
        "pct": round(pct, 2),
        "volume_l": round(volume, 1),
        "out_of_range": out_of_range,
    }


def calc_consumption_events(readings: list[dict], date: str) -> list[dict]:
    """
    Agrupa leituras por hora e retorna eventos de consumo/abastecimento.
    Cada reading deve ter: {ts (unix int), volume_l}.
    """
    buckets: dict[int, list[dict]] = defaultdict(list)
    for r in readings:
        hour = datetime.datetime.fromtimestamp(r["ts"], tz=datetime.timezone.utc).hour
        buckets[hour].append(r)

    events = []
    for hour in sorted(buckets.keys()):
        pts = sorted(buckets[hour], key=lambda x: x["ts"])
        vol_start = pts[0]["volume_l"]
        vol_end = pts[-1]["volume_l"]
        delta = vol_end - vol_start
        if delta < -50:
            etype = "consumption"
        elif delta > 50:
            etype = "supply"
        else:
            etype = "stable"
        events.append({
            "hour": f"{hour:02d}:00",
            "vol_start": round(vol_start, 1),
            "vol_end": round(vol_end, 1),
            "delta_l": round(delta, 1),
            "type": etype,
        })
    return events


def decimate_readings(readings: list[dict], max_points: int = 500) -> list[dict]:
    """
    Decimação por média de intervalo.
    Se len(readings) <= max_points, retorna sem modificação.
    """
    n = len(readings)
    if n <= max_points:
        return readings

    bucket_size = n / max_points
    result = []
    for i in range(max_points):
        start = int(i * bucket_size)
        end = int((i + 1) * bucket_size)
        bucket = readings[start:end]
        if not bucket:
            continue
        mid = bucket[len(bucket) // 2]
        vol_vals = [r["volume_l"] for r in bucket if r.get("volume_l") is not None]
        avg_volume = sum(vol_vals) / len(vol_vals) if vol_vals else 0.0
        level_vals = [r["level_cm"] for r in bucket if r.get("level_cm") is not None]
        pct_vals = [r["pct"] for r in bucket if r.get("pct") is not None]
        avg_level = sum(level_vals) / len(level_vals) if level_vals else 0.0
        avg_pct = sum(pct_vals) / len(pct_vals) if pct_vals else 0.0
        result.append({
            "ts": mid["ts"],
            "volume_l": round(avg_volume, 1),
            "level_cm": round(avg_level, 1),
            "pct": round(avg_pct, 2),
        })
    return result
