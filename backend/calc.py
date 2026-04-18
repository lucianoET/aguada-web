# backend/calc.py
"""Funções puras de cálculo — sem I/O, sem banco."""
from __future__ import annotations
from typing import Optional
from collections import defaultdict
import datetime
import statistics


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


def _classify_delta(delta_l: float, min_delta_l: float) -> str:
    if delta_l <= -min_delta_l:
        return "consumption"
    if delta_l >= min_delta_l:
        return "supply"
    return "stable"


def calc_consumption_events(readings: list[dict], date: str, min_delta_l: float = 50.0) -> list[dict]:
    """
    Agrupa leituras por hora usando volume mediano e retorna eventos de consumo/abastecimento.

    O volume mediano por hora reduz o impacto de oscilações rápidas do sensor e, ao
    comparar horas consecutivas, evita perder recuperações que cruzam a virada da hora.
    Cada reading deve ter: {ts (unix int), volume_l}.
    """
    valid = sorted(
        (r for r in readings if r.get("ts") is not None and r.get("volume_l") is not None),
        key=lambda item: item["ts"],
    )
    if len(valid) < 2:
        return []

    buckets: dict[tuple[int, int, int, int], list[dict]] = defaultdict(list)
    for reading in valid:
        dt = datetime.datetime.fromtimestamp(reading["ts"])
        buckets[(dt.year, dt.month, dt.day, dt.hour)].append(reading)

    bucket_states = []
    for key in sorted(buckets.keys()):
        pts = sorted(buckets[key], key=lambda item: item["ts"])
        volumes = [float(item["volume_l"]) for item in pts]
        bucket_states.append({
            "hour": f"{key[3]:02d}:00",
            "ts": pts[-1]["ts"],
            "vol": float(statistics.median(volumes)),
        })

    if len(bucket_states) == 1:
        vol_start = float(valid[0]["volume_l"])
        vol_end = float(valid[-1]["volume_l"])
        delta_l = vol_end - vol_start
        return [{
            "hour": datetime.datetime.fromtimestamp(valid[-1]["ts"]).strftime("%H:00"),
            "ts_start": valid[0]["ts"],
            "ts_end": valid[-1]["ts"],
            "duration_min": round(max(0, valid[-1]["ts"] - valid[0]["ts"]) / 60.0, 1),
            "vol_start": round(vol_start, 1),
            "vol_end": round(vol_end, 1),
            "delta_l": round(delta_l, 1),
            "type": _classify_delta(delta_l, min_delta_l),
        }]

    raw_events = []
    previous = bucket_states[0]
    for current in bucket_states[1:]:
        delta_l = current["vol"] - previous["vol"]
        raw_events.append({
            "hour": current["hour"],
            "ts_start": previous["ts"],
            "ts_end": current["ts"],
            "duration_min": round(max(0, current["ts"] - previous["ts"]) / 60.0, 1),
            "vol_start": round(previous["vol"], 1),
            "vol_end": round(current["vol"], 1),
            "delta_l": round(delta_l, 1),
            "type": _classify_delta(delta_l, min_delta_l),
        })
        previous = current

    merged_events = []
    for event in raw_events:
        if not merged_events or event["type"] == "stable":
            merged_events.append(event)
            continue
        previous_event = merged_events[-1]
        if previous_event["type"] != event["type"]:
            merged_events.append(event)
            continue
        previous_event["ts_end"] = event["ts_end"]
        previous_event["duration_min"] = round(max(0, previous_event["ts_end"] - previous_event["ts_start"]) / 60.0, 1)
        previous_event["vol_end"] = event["vol_end"]
        previous_event["delta_l"] = round(previous_event["delta_l"] + event["delta_l"], 1)
        previous_event["hour"] = event["hour"]

    return merged_events


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
