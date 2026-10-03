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


# ponytail: tuning knob — o ultrassônico oscila entre dois cm vizinhos (na CIE, 1 cm ≈ 1 m³).
# Uma variação só vira consumo/abastecimento quando acumula >= noise_cm desde o último
# nível aceito: oscilação some, escoamento lento (< 1 cm/h) ainda é contado ao acumular.
# noise_cm = max(NOISE_CM, ruído medido no dia) — sensor ruidoso (CB31, ±5 cm) sobe o limiar.
NOISE_CM = 1.5


def _noise_cm(groups: list[list[dict]]) -> float:
    """σ robusto (1.4826·MAD) do nível em torno da mediana de cada grupo, com piso NOISE_CM."""
    devs = []
    for pts in groups:
        med = _median_or_none([r.get("level_cm") for r in pts])
        if med is not None:
            devs += [abs(float(r["level_cm"]) - med) for r in pts if r.get("level_cm") is not None]
    return max(NOISE_CM, 1.4826 * statistics.median(devs)) if devs else NOISE_CM


def _moved(cur: dict, ref: dict, min_delta_l: float, noise_cm: float = NOISE_CM) -> bool:
    if abs(cur["vol"] - ref["vol"]) < min_delta_l:
        return False
    if cur["lvl"] is None or ref["lvl"] is None:
        return True  # leituras sem level_cm: só o limiar em litros
    return abs(cur["lvl"] - ref["lvl"]) >= noise_cm


def _median_or_none(values: list) -> Optional[float]:
    vals = [float(v) for v in values if v is not None]
    return float(statistics.median(vals)) if vals else None


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
            "lvl": _median_or_none([item.get("level_cm") for item in pts]),
        })

    noise_cm = _noise_cm(list(buckets.values()))

    if len(bucket_states) == 1:
        # Uma hora só: mediana da 1ª metade vs 2ª metade (leitura crua isolada é ruído)
        half = len(valid) // 2
        head, tail = valid[:half], valid[half:]
        vol_start = float(statistics.median(float(r["volume_l"]) for r in head))
        vol_end = float(statistics.median(float(r["volume_l"]) for r in tail))
        delta_l = vol_end - vol_start
        moved = _moved({"vol": vol_end, "lvl": _median_or_none([r.get("level_cm") for r in tail])},
                       {"vol": vol_start, "lvl": _median_or_none([r.get("level_cm") for r in head])},
                       min_delta_l, noise_cm)
        return [{
            "hour": datetime.datetime.fromtimestamp(valid[-1]["ts"]).strftime("%H:00"),
            "ts_start": valid[0]["ts"],
            "ts_end": valid[-1]["ts"],
            "duration_min": round(max(0, valid[-1]["ts"] - valid[0]["ts"]) / 60.0, 1),
            "vol_start": round(vol_start, 1),
            "vol_end": round(vol_end, 1),
            "delta_l": round(delta_l, 1),
            "type": _classify_delta(delta_l, min_delta_l) if moved else "stable",
        }]

    raw_events = []
    previous = ref = bucket_states[0]  # ref = último nível aceito
    for current in bucket_states[1:]:
        if _moved(current, ref, min_delta_l, noise_cm):
            # Variação acumulada desde ref: absorve os "stable" intermediários
            while raw_events and raw_events[-1]["type"] == "stable" and raw_events[-1]["ts_start"] >= ref["ts"]:
                raw_events.pop()
            start = ref
            delta_l = current["vol"] - ref["vol"]
            kind = _classify_delta(delta_l, min_delta_l)
            ref = current
        else:
            start = previous
            delta_l = current["vol"] - previous["vol"]  # informativo, fora do resumo
            kind = "stable"
        raw_events.append({
            "hour": current["hour"],
            "ts_start": start["ts"],
            "ts_end": current["ts"],
            "duration_min": round(max(0, current["ts"] - start["ts"]) / 60.0, 1),
            "vol_start": round(start["vol"], 1),
            "vol_end": round(current["vol"], 1),
            "delta_l": round(delta_l, 1),
            "type": kind,
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
