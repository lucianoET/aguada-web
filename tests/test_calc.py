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
