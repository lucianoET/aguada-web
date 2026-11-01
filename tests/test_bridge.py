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


def test_vbat_volts_aceita_volts_e_decimos():
    from backend.bridge import _vbat_volts
    assert _vbat_volts(5.0) == 5.0      # gateway já converteu
    assert _vbat_volts(5) == 5.0        # ArduinoJson imprime 5.0 como 5
    assert _vbat_volts(4.9) == 4.9
    assert _vbat_volts(50) == 5.0       # décimos crus
    assert _vbat_volts(33) == 3.3
    assert _vbat_volts(-1) is None
    assert _vbat_volts(None) is None


YAML2 = """reservoirs:
  "0XAAAA":
    - sensor_id: 1
      alias: AAA
      name: Tanque A
      level_max_cm: 300   # medido
      volume_max_L: 30000
      sensor_offset_cm: 10
    - sensor_id: 2
      alias: AAB
      name: Tanque B
      level_max_cm: 200
      volume_max_L: 20000
      sensor_offset_cm: 10
  "0XCCCC":
    - sensor_id: 1
      alias: CCC
      name: Tanque C
      level_max_cm: 100
      volume_max_L: 1000
      sensor_offset_cm: 10
"""


class _FakeMqtt:
    def __init__(self):
        self.pub = []

    def publish(self, topic, payload, retain=False):
        self.pub.append((topic, payload))


def _bridge_with(tmp_path, monkeypatch):
    f = tmp_path / "reservoirs.yaml"
    f.write_text(YAML2)
    monkeypatch.setattr(b, "_yaml_path", f)
    index, _ = _load_reservoirs(f)
    monkeypatch.setattr(b, "RESERVOIR_INDEX", index)
    br = Bridge.__new__(Bridge)
    br._mqtt_client = _FakeMqtt()
    return br, f, index


def test_config_set_aplica_e_grava_so_a_linha_certa(tmp_path, monkeypatch):
    br, f, index = _bridge_with(tmp_path, monkeypatch)
    br._on_config_set("aguada/0xaaaa/2/config/sensor_offset_cm/set", b"35")
    br._on_config_set("aguada/0xaaaa/1/config/volume_max_L/set", b"31000")
    assert index[("0xaaaa", 2)]["sensor_offset_cm"] == 35
    assert index[("0xaaaa", 1)]["volume_max_l"] == 31000
    txt = f.read_text()
    assert "level_max_cm: 300   # medido" in txt          # comentário preservado
    assert txt.count("sensor_offset_cm: 35") == 1          # só o AAB mudou
    assert "volume_max_L: 31000" in txt and "volume_max_L: 1000\n" in txt
    topic, payload = br._mqtt_client.pub[-1]
    assert topic == "aguada/0xaaaa/1/config" and '"volume_max_L": 31000' in payload


def test_config_set_rejeita_fora_da_faixa(tmp_path, monkeypatch):
    br, f, index = _bridge_with(tmp_path, monkeypatch)
    br._on_config_set("aguada/0xcccc/1/config/level_max_cm/set", b"5")
    br._on_config_set("aguada/0xcccc/1/config/level_max_cm/set", b"nan")
    assert index[("0xcccc", 1)]["level_max_cm"] == 100
    assert f.read_text() == YAML2


def test_air_temp_decodifica_canal_t_ext():
    from backend.bridge import air_temp_c
    assert air_temp_c(1253, 0) == 25.3
    assert air_temp_c(950, 0) == -5.0
    assert air_temp_c(0xFFFF, 4) is None
    assert air_temp_c(1253, 4) is None


def test_air_temp_publica_no_alias_do_reservatorio(tmp_path, monkeypatch):
    br, f, index = _bridge_with(tmp_path, monkeypatch)
    monkeypatch.setattr(b, "NODE_ALIASES", {"0xdddd": "0xaaaa"})
    br._air_temp_discovery = set()
    br._handle({"type": "HEARTBEAT", "node_id": "0xDDDD", "sensor_id": 241,
                "distance_cm": 1281, "flags": 0})
    topics = dict(br._mqtt_client.pub)
    assert "homeassistant/sensor/aguada_aaa_temp_ar/config" in topics
    assert '"temp_c": 28.1' in topics["aguada/0xaaaa/air_temp/state"]


def test_porta_by_id_nao_cai_em_outro_dispositivo(monkeypatch):
    from backend.bridge import _detect_serial_port, _is_serial_available
    gw = "/dev/serial/by-id/usb-Espressif_USB_JTAG_serial_debug_unit_GW-if00"
    monkeypatch.setattr(b, "glob", lambda pat: ["/dev/ttyACM0"] if "ttyACM" in pat else [])
    assert _detect_serial_port(gw) == gw
    assert _is_serial_available(gw) is False
