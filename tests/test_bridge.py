# tests/test_bridge.py
import os
import pytest
import backend.bridge as b
from backend.bridge import Bridge, _process_message, _load_reservoirs, RESERVOIR_INDEX, NODE_ALIASES

YAML = """
reservoirs:
  "0XAAAA":
    - sensor_id: 1
      alias: AAA
      name: Tanque A
      level_max_cm: 300
      volume_max_L: 30000
      sensor_offset_cm: 10
      also: ["0XBBBB"]
  "0XCCCC":
    - sensor_id: 1
      type: air_quality
      alias: AQ
"""


def test_wired_node_alias_maps_to_primary():
    # Payload do node-eth: type minúsculo, vbat -1, node_id alternativo do CAV
    raw = {"type": "sensor", "node_id": "0xEE02", "sensor_id": 1,
           "distance_cm": 120, "rssi": 0, "vbat": -1, "flags": 0, "seq": 7}
    rec = _process_message(raw)
    assert rec is not None
    assert rec["alias"] == "CAV"
    assert rec["node_id"] == "0xc9c4"
    assert rec["vbat"] is None


def test_alias_node_not_in_index():
    # Um reservatório = uma entrada; o node alternativo só existe como alias
    assert ("0xee02", 1) not in RESERVOIR_INDEX
    assert NODE_ALIASES["0xee02"] == "0xc9c4"


def test_load_reservoirs(tmp_path):
    f = tmp_path / "r.yaml"
    f.write_text(YAML)
    index, aliases = _load_reservoirs(f)
    assert list(index) == [("0xaaaa", 1)]           # air_quality fica de fora
    assert index[("0xaaaa", 1)]["volume_max_l"] == 30000
    assert aliases == {"0xbbbb": "0xaaaa"}


def test_load_reservoirs_missing_volume_fails(tmp_path):
    f = tmp_path / "r.yaml"
    f.write_text(YAML.replace("      volume_max_L: 30000\n", ""))
    with pytest.raises(ValueError, match="volume_max_l"):
        _load_reservoirs(f)


@pytest.fixture
def swap_yaml(tmp_path, monkeypatch):
    saved_index, saved_aliases = dict(RESERVOIR_INDEX), dict(NODE_ALIASES)
    f = tmp_path / "r.yaml"
    f.write_text(YAML)
    monkeypatch.setattr(b, "_yaml_path", f)
    monkeypatch.setattr(b, "_yaml_mtime", 0.0)
    yield f
    b._swap(RESERVOIR_INDEX, saved_index)
    b._swap(NODE_ALIASES, saved_aliases)


def test_reload_picks_up_edit_and_keeps_old_on_error(swap_yaml):
    b.reload_reservoirs()
    assert RESERVOIR_INDEX[("0xaaaa", 1)]["sensor_offset_cm"] == 10

    # Edição em runtime (bridge HA mudando o offset)
    swap_yaml.write_text(YAML.replace("sensor_offset_cm: 10", "sensor_offset_cm: 35"))
    os.utime(swap_yaml, (1, 1))
    b.reload_reservoirs()
    assert RESERVOIR_INDEX[("0xaaaa", 1)]["sensor_offset_cm"] == 35

    # Arquivo quebrado: mantém a config anterior
    swap_yaml.write_text("reservoirs: [")
    os.utime(swap_yaml, (2, 2))
    b.reload_reservoirs()
    assert RESERVOIR_INDEX[("0xaaaa", 1)]["sensor_offset_cm"] == 35


def test_seq_dedup():
    br = Bridge.__new__(Bridge)  # sem MQTT/thread
    br._seen_seq = {}
    pkt = {"type": "SENSOR", "node_id": "0x7758", "sensor_id": 1, "seq": 42}
    assert not br._seen_before(pkt)
    assert br._seen_before(dict(pkt))                 # mesmo pacote por outro caminho
    assert not br._seen_before({**pkt, "seq": 43})    # próximo pacote
    assert not br._seen_before({**pkt, "seq": None})  # sem seq: nunca descarta


def test_apply_remote_config(swap_yaml):
    b.reload_reservoirs()
    b.apply_remote_config("0XAAAA", "1", b'{"level_max_cm": 320, "sensor_offset_cm": 0, "volume_max_L": 32000}')
    p = RESERVOIR_INDEX[("0xaaaa", 1)]
    assert (p["level_max_cm"], p["sensor_offset_cm"], p["volume_max_l"]) == (320, 0, 32000)
    # Valor inválido (zero divide no calc, string, bool) é ignorado
    b.apply_remote_config("0XAAAA", "1", b'{"level_max_cm": 0, "volume_max_L": "x", "sensor_offset_cm": true}')
    assert (p["level_max_cm"], p["sensor_offset_cm"], p["volume_max_l"]) == (320, 0, 32000)
    b.apply_remote_config("0XFFFF", "1", b'{"level_max_cm": 999}')  # reservatório desconhecido: no-op
