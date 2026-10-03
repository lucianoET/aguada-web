# tests/test_calc.py
import pytest
from backend.calc import calc_level, calc_consumption_events, decimate_readings

def test_calc_level_normal():
    result = calc_level(distance_cm=215, level_max_cm=450, sensor_offset_cm=20, volume_max_l=80000)
    # level = clamp(450 - (215 - 20), 0, 450) = clamp(255, 0, 450) = 255
    assert result["level_cm"] == pytest.approx(255.0)
    assert result["pct"] == pytest.approx(255 / 450 * 100, rel=1e-4)
    assert result["volume_l"] == pytest.approx(255 / 450 * 80000, rel=1e-4)

def test_calc_level_clamp_zero():
    result = calc_level(distance_cm=500, level_max_cm=200, sensor_offset_cm=10, volume_max_l=40000)
    assert result["level_cm"] == 0.0
    assert result["pct"] == 0.0

def test_calc_level_clamp_max():
    result = calc_level(distance_cm=0, level_max_cm=200, sensor_offset_cm=10, volume_max_l=40000)
    assert result["level_cm"] == 200.0
    assert result["pct"] == 100.0

def test_calc_level_error_distance():
    result = calc_level(distance_cm=None, level_max_cm=200, sensor_offset_cm=10, volume_max_l=40000)
    assert result["level_cm"] is None
    assert result["pct"] is None

def test_consumption_events_classifies_consumption():
    readings = [
        {"ts": 3600, "volume_l": 45000},
        {"ts": 7100, "volume_l": 43000},
    ]
    events = calc_consumption_events(readings, date="2026-03-23")
    assert len(events) == 1
    assert events[0]["type"] == "consumption"
    assert events[0]["delta_l"] == pytest.approx(-2000)
    assert events[0]["ts_start"] == 3600
    assert events[0]["ts_end"] == 7100

def test_consumption_events_classifies_supply():
    readings = [
        {"ts": 3600, "volume_l": 43000},
        {"ts": 7100, "volume_l": 50000},
    ]
    events = calc_consumption_events(readings, date="2026-03-23")
    assert events[0]["type"] == "supply"

def test_consumption_events_classifies_stable():
    readings = [
        {"ts": 3600, "volume_l": 45000},
        {"ts": 7100, "volume_l": 45030},
    ]
    events = calc_consumption_events(readings, date="2026-03-23")
    assert events[0]["type"] == "stable"


def test_consumption_events_detects_cross_hour_recovery_with_hourly_medians():
    readings = [
        {"ts": 23 * 3600 + 10 * 60, "volume_l": 10000},
        {"ts": 23 * 3600 + 20 * 60, "volume_l": 7000},
        {"ts": 23 * 3600 + 30 * 60, "volume_l": 10000},
        {"ts": 24 * 3600 + 5 * 60, "volume_l": 7000},
        {"ts": 24 * 3600 + 15 * 60, "volume_l": 10000},
        {"ts": 24 * 3600 + 25 * 60, "volume_l": 10000},
    ]

    events = calc_consumption_events(readings, date="2026-03-23")

    assert len(events) == 1
    assert events[0]["type"] == "stable"
    assert events[0]["delta_l"] == pytest.approx(0)

def test_decimate_passthrough_if_under_limit():
    readings = [{"ts": i, "volume_l": i * 10, "level_cm": float(i), "pct": i * 0.1}
                for i in range(100)]
    result = decimate_readings(readings, max_points=500)
    assert result == readings

def test_decimate_reduces_to_max_points():
    readings = [{"ts": i, "volume_l": i * 10, "level_cm": float(i), "pct": i * 0.1}
                for i in range(1000)]
    result = decimate_readings(readings, max_points=500)
    assert len(result) <= 500

def test_decimate_handles_missing_volume_l():
    readings = [{"ts": i, "level_cm": float(i), "pct": i * 0.1} for i in range(1000)]
    # não deve levantar KeyError
    result = decimate_readings(readings, max_points=500)
    assert len(result) <= 500
    assert all(r["volume_l"] == 0.0 for r in result)


def _cie(level_cm_by_hour):
    # Cisterna 245 m³ / 240 cm (≈1021 L/cm), 6 leituras por hora
    l_per_cm = 245000 / 240
    return [{"ts": h * 3600 + m * 600, "level_cm": lvl, "volume_l": lvl * l_per_cm}
            for h, lvls in enumerate(level_cm_by_hour, start=1) for m, lvl in enumerate(lvls)]


def test_consumption_ignores_one_cm_sensor_flicker():
    # Oscila 11↔12 cm a hora toda: nenhum consumo/abastecimento
    flick = [11, 12, 11, 12, 11, 12]
    events = calc_consumption_events(_cie([flick, [12] * 6, [11] * 6, flick]), date="2026-10-01")
    assert all(e["type"] == "stable" for e in events)


def test_consumption_counts_slow_drift_once_accumulated():
    # Desce 1 cm/h: cada hora isolada é ruído, mas o acumulado vira consumo real.
    # 100→98 conta (2 cm); 98→97 ainda está abaixo do limiar e entra quando acumular.
    events = calc_consumption_events(_cie([[100] * 6, [99] * 6, [98] * 6, [97] * 6]), date="2026-10-01")
    consumed = sum(-e["delta_l"] for e in events if e["type"] == "consumption")
    assert consumed == pytest.approx(2 * 245000 / 240, rel=0.01)


def test_consumption_single_hour_uses_medians_not_endpoints():
    # CB31 real (01/10): sensor ruidoso, 1ª leitura 180 e última 186 — sem abastecimento de fato
    lvls = [180, 189, 179, 180, 185, 188, 185, 182, 188, 187, 187, 187, 181, 188, 171,
            188, 187, 189, 189, 179, 187, 187, 185, 182, 186]
    readings = [{"ts": 19 * 3600 + i * 60, "level_cm": l, "volume_l": l * 200.0} for i, l in enumerate(lvls)]
    events = calc_consumption_events(readings, date="2026-10-01")
    assert len(events) == 1 and events[0]["type"] == "stable"


def test_consumption_noisy_sensor_raises_threshold_but_keeps_real_fill():
    # Sensor ±5 cm (CB31): medianas que diferem 2 cm são ruído; enchimento de 20 cm/h é real
    noisy = [180, 189, 179, 186, 185, 188, 185, 182, 188, 187, 187, 187]
    shifted = [l + 2 for l in noisy]
    rd = lambda hours: [{"ts": (h + 1) * 3600 + i * 300, "level_cm": l, "volume_l": l * 200.0}
                        for h, lvls in enumerate(hours) for i, l in enumerate(lvls)]
    assert all(e["type"] == "stable" for e in calc_consumption_events(rd([noisy, shifted]), date="x"))
    filling = [l + 20 for l in noisy]
    events = calc_consumption_events(rd([noisy, filling]), date="x")
    assert [e["type"] for e in events] == ["supply"]
