# backend/bridge.py
"""
Bridge serial → SQLite + WebSocket notify.
Roda como thread daemon iniciada pelo FastAPI startup.
"""
import asyncio
import json
import logging
import os
import queue
import random
import re
import tempfile
import threading
import time
from glob import glob
from pathlib import Path
from typing import Callable, Optional

import yaml

from .calc import calc_level
from .db import insert_reading, upsert_state, upsert_node, upsert_node_seen

logger = logging.getLogger("bridge")

# Fonte única: luctronics_firmware/platformio/tools/reservoirs.yaml (repo aguada-firmware),
# o mesmo arquivo que o bridge do Home Assistant lê e edita em runtime. RESERVOIRS_FILE
# aponta direto para ele; sem a variável, usa a cópia em backend/ (tools/sync_reservoirs.sh).
_yaml_path = Path(__file__).parent / "reservoirs.yaml"
_env_yaml = os.getenv("RESERVOIRS_FILE")
if _env_yaml:
    if Path(_env_yaml).exists():
        _yaml_path = Path(_env_yaml)
    else:
        logger.warning("RESERVOIRS_FILE=%s não existe — usando %s", _env_yaml, _yaml_path)

_REQUIRED = ("alias", "name", "sensor_offset_cm", "volume_max_l")


def _load_reservoirs(path: Path) -> tuple[dict, dict]:
    """Lê reservoirs.yaml → (índice, aliases).

    índice:  (node_id_lower, sensor_id) → params. Uma entrada por reservatório.
    aliases: node_id alternativo ("also") → node_id principal (ex.: node cabeado
             0xee02 → 0xc9c4), como NODE_ALIASES no bridge HA.
    Entrada incompleta levanta ValueError — erro de config aparece no load, não vira None.
    """
    index: dict[tuple[str, int], dict] = {}
    aliases: dict[str, str] = {}
    for node_id, sensors in yaml.safe_load(path.read_text())["reservoirs"].items():
        nid = str(node_id).lower()
        for s in sensors:
            if "level_max_cm" not in s:
                continue  # entradas sem nível (ex.: type: air_quality) são só do bridge HA
            s["volume_max_l"] = s.get("volume_max_l", s.get("volume_max_L"))
            missing = [k for k in _REQUIRED if s.get(k) is None]
            if missing:
                raise ValueError(f"{path}: {nid}/{s.get('sensor_id')} sem {', '.join(missing)}")
            index[(nid, int(s["sensor_id"]))] = s
            for alt in s.get("also", []):
                aliases[str(alt).lower()] = nid
    return index, aliases


_yaml_mtime = _yaml_path.stat().st_mtime
RESERVOIR_INDEX, NODE_ALIASES = _load_reservoirs(_yaml_path)


def _swap(target: dict, new: dict) -> None:
    # ponytail: sem lock — atribuição/pop por chave são atômicas no GIL e leitores iteram
    # sobre list(...). Lock se um dia houver leitor que itere o dict direto.
    for k in target.keys() - new.keys():
        target.pop(k, None)
    target.update(new)


# (chave no payload do bridge HA, chave no params, mínimo aceito)
_REMOTE_PARAMS = (("level_max_cm", "level_max_cm", 1),
                  ("sensor_offset_cm", "sensor_offset_cm", 0),
                  ("volume_max_L", "volume_max_l", 1))


# Editáveis no HA (number): param do YAML -> (rótulo, sufixo da entidade, unidade, mín, máx, ícone).
# Mesmos nomes/ids do bridge HA (aguada-firmware/tools/bridge.py RESERVOIR_PARAMS).
EDITABLE_PARAMS = {
    "level_max_cm":     ("Altura útil", "altura_util", "cm", 50, 1000, "mdi:arrow-expand-vertical"),
    "sensor_offset_cm": ("Offset do sensor", "offset_sensor", "cm", 0, 200, "mdi:arrow-collapse-down"),
    "volume_max_L":     ("Volume máximo", "volume_maximo", "L", 1, 500000, "mdi:cup-water"),
}
_PARAM_KEY = {"volume_max_L": "volume_max_l"}  # params normaliza volume_max_L -> volume_max_l


def param_value(params: dict, param: str):
    return params.get(_PARAM_KEY.get(param, param))


def persist_param(node_id: str, alias: str, param: str, value: int) -> bool:
    """Troca só a linha `param: N` do reservatório no YAML (comentários sobrevivem).
    Retorna False se não achou a linha ou o arquivo é só leitura."""
    path = os.path.realpath(_yaml_path)
    with open(path, encoding="utf-8") as f:
        lines = f.read().splitlines(keepends=True)
    node_re = re.compile(r'^\s*["\']?%s["\']?\s*:' % re.escape(node_id), re.IGNORECASE)
    alias_re = re.compile(r'^\s*(?:-\s+)?alias:\s*["\']?%s["\']?\s*(#.*)?$' % re.escape(alias))
    param_re = re.compile(r"^(\s*(?:-\s+)?%s\s*:\s*)(-?\d+(?:\.\d+)?)(.*)$" % re.escape(param))
    start = next((i for i, l in enumerate(lines) if node_re.match(l)), None)
    if start is None:
        return False
    in_item, m = False, None
    for i in range(start + 1, len(lines)):
        body = lines[i].rstrip("\r\n")
        if body.strip() and not body.startswith(" "):
            break
        if re.match(r'^\s*["\']?0[xX][0-9A-Fa-f]+["\']?\s*:', body):  # próximo node
            break
        if re.match(r"^\s*-\s", body):
            in_item = bool(alias_re.match(body))
        elif alias_re.match(body):
            in_item = True
        m = param_re.match(body) if in_item else None
        if m:
            lines[i] = m.group(1) + str(value) + m.group(3) + lines[i][len(body):]
            break
    if not m:
        return False
    st = os.stat(path)
    try:
        fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), prefix=".reservoirs.", suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write("".join(lines))
        os.chmod(tmp, st.st_mode & 0o7777)
        try:
            os.chown(tmp, st.st_uid, st.st_gid)  # container roda como root; o arquivo é do host
        except PermissionError:
            pass
        os.replace(tmp, path)
    except OSError as e:
        logger.error("Config não persistida em %s: %s", path, e)
        return False
    global _yaml_mtime
    _yaml_mtime = os.stat(path).st_mtime  # já aplicado em memória; não recarregar
    return True


def apply_remote_config(node_id: str, sensor_id: str, payload: bytes) -> None:
    """Aplica os parâmetros editáveis que o bridge HA publica (retido) em
    aguada/<node>/<sid>/config quando alguém muda um offset no HA. Cobre o caso em que
    o arquivo não chega ao container (Docker Desktop não propaga os.replace)."""
    params = RESERVOIR_INDEX.get((node_id.lower(), int(sensor_id)))
    if params is None:
        return
    cfg = json.loads(payload)
    for src, dst, lo in _REMOTE_PARAMS:
        v = cfg.get(src)
        if isinstance(v, (int, float)) and not isinstance(v, bool) and v >= lo and v != params.get(dst):
            logger.info("Config remota %s %s: %s -> %s", params["alias"], dst, params.get(dst), v)
            params[dst] = v


def reload_reservoirs() -> None:
    """Relê reservoirs.yaml se mudou no disco (o bridge HA edita offsets em runtime).
    Arquivo inválido: loga uma vez e mantém a config anterior."""
    global _yaml_mtime
    try:
        mtime = _yaml_path.stat().st_mtime
        if mtime == _yaml_mtime:
            return
        _yaml_mtime = mtime
        index, aliases = _load_reservoirs(_yaml_path)
    except Exception as e:
        logger.error("reservoirs.yaml inválido, mantendo config anterior: %s", e)
        return
    _swap(RESERVOIR_INDEX, index)
    _swap(NODE_ALIASES, aliases)
    logger.info("reservoirs.yaml recarregado: %d reservatórios", len(index))


FLAG_SENSOR_ERROR = 1 << 2
SENSOR_ID_T_EXT = 0xF1  # HEARTBEAT: distance_cm = °C*10 + 1000 (firmware temp_enc)


def air_temp_c(raw, flags) -> Optional[float]:
    """Decodifica o canal T_EXT; None = sonda sem leitura (erro/ausente)."""
    if raw is None or flags & FLAG_SENSOR_ERROR or raw == 0xFFFF:
        return None
    return round((int(raw) - 1000) / 10.0, 1)

# (chave, rótulo, value_template, unidade, device_class, ícone) — espelha publish_discovery
# do bridge HA (aguada-firmware/tools/bridge.py), adaptado ao payload deste bridge.
_DISCOVERY_ENTITIES = (
    ("nivel", "Nível", "{{ value_json.level_cm }}", "cm", "distance", "mdi:water-level"),
    ("pct", "Volume %", "{{ value_json.pct }}", "%", None, "mdi:percent"),
    ("volume", "Volume", "{{ value_json.volume_l }}", "L", None, "mdi:water"),
    ("distancia", "Distância", "{{ value_json.distance_cm }}", "cm", "distance", "mdi:ruler"),
    ("rssi", "RSSI", "{{ value_json.rssi }}", "dBm", "signal_strength", "mdi:wifi"),
    ("bateria", "Bateria", "{{ value_json.vbat }}", "V", "voltage", "mdi:battery"),
    ("last_update", "Último dado", "{{ as_datetime(value_json.ts).isoformat() }}", None,
     "timestamp", "mdi:clock-outline"),
)
SEQ_DEDUP_TTL_S = 120  # mesmo valor do bridge HA


def _pinned(configured_port: Optional[str]) -> bool:
    """Porta por número de série (/dev/serial/by-id/...): só ela serve. Sem fallback,
    senão outro ESP plugado (ex.: um nó no USB) vira "gateway" e é resetado."""
    return bool(configured_port) and "/serial/by-id/" in configured_port


def _detect_serial_port(configured_port: Optional[str]) -> str:
    if _pinned(configured_port):
        return configured_port
    candidates: list[str] = []
    if configured_port:
        candidates.append(configured_port)

    candidates.extend(sorted(glob("/dev/serial/by-id/*")))
    candidates.extend(sorted(glob("/dev/ttyACM*")))
    candidates.extend(sorted(glob("/dev/ttyUSB*")))

    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        if Path(candidate).exists():
            return candidate

    return configured_port or "/dev/ttyUSB0"


def _should_pulse_dtr(serial_port: str) -> bool:
    """Avoid DTR reset on native USB CDC devices (ex.: ESP32-C3/S3 USB JTAG CDC on ttyACM).

    Classic USB-UART adapters (CH340/CP210x on ttyUSB) may benefit from a reset pulse,
    but native USB CDC devices tend to reset/disconnect when DTR is toggled by the host.
    """
    port = (serial_port or "").lower()
    if "/dev/ttyacm" in port:
        return False
    if "usb_jtag_serial_debug_unit" in port:
        return False
    return True


def _is_serial_available(configured_port: Optional[str]) -> bool:
    """Verifica rapidamente se há porta serial disponível, sem abrir o dispositivo."""
    if configured_port and Path(configured_port).exists():
        return True
    if _pinned(configured_port):
        return False
    for pattern in ["/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"]:
        for p in glob(pattern):
            if Path(p).exists():
                return True
    return False


def _vbat_volts(v) -> Optional[float]:
    """vbat em volts. O pacote leva décimos (50 = 5,0 V; -1 = sem medição), mas o
    gateway já converte para volts no JSON (5.0, que o ArduinoJson pode imprimir
    como 5). Valor < 10 = já em volts; >= 10 = décimos."""
    if v is None or isinstance(v, bool):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f < 0:
        return None
    return round(f if f < 10 else f / 10.0, 2)


def _process_message(raw: dict) -> Optional[dict]:
    """Valida e enriquece uma mensagem do gateway. Retorna dict pronto para DB ou None."""
    try:
        # Só processa pacotes SENSOR (node-eth publica "sensor" minúsculo)
        if str(raw.get("type", "")).upper() != "SENSOR":
            return None

        reload_reservoirs()
        node_id = raw.get("node_id", "").lower()
        node_id = NODE_ALIASES.get(node_id, node_id)
        sensor_id = int(raw.get("sensor_id", 0))
        distance_cm = raw.get("distance_cm")
        rssi = raw.get("rssi")
        vbat_raw = raw.get("vbat")
        seq = raw.get("seq", 0)
        # Timestamp sempre pelo servidor — gateway e nós não têm RTC confiável.
        ts = int(time.time())
        # vbat < 0 = sem medição (node-eth alimentado pela rede manda -1)
        vbat = _vbat_volts(vbat_raw)

        # Descarta leituras com erro de sensor
        flags = raw.get("flags", 0)
        if flags & FLAG_SENSOR_ERROR:
            logger.warning("FLAG_SENSOR_ERROR em node_id=%s sensor=%d — descartado", node_id, sensor_id)
            return None

        params = RESERVOIR_INDEX.get((node_id, sensor_id))
        if params is None:
            logger.warning("node_id=%s sensor=%d não encontrado no reservoirs.yaml", node_id, sensor_id)
            return None

        calc = calc_level(
            distance_cm=distance_cm,
            level_max_cm=params["level_max_cm"],
            sensor_offset_cm=params["sensor_offset_cm"],
            volume_max_l=params["volume_max_l"],
        )

        return {
            "ts": ts,
            "node_id": node_id,
            "sensor_id": sensor_id,
            "alias": params["alias"],
            "distance_cm": distance_cm,
            "level_cm": calc["level_cm"],
            "volume_l": calc["volume_l"],
            "pct": calc["pct"],
            "out_of_range": calc["out_of_range"],
            "rssi": rssi,
            "vbat": vbat,
            "seq": seq,
            "name": params["name"],
            "level_max_cm": params["level_max_cm"],
            "volume_max_l": params["volume_max_l"],
        }
    except Exception as e:
        logger.error("Erro ao processar mensagem: %s — %s", raw, e)
        return None


class Bridge:
    def __init__(self, db_path: str, notify_cb: Callable[[dict], None], after_save=None):
        self.db_path = db_path
        self.notify_cb = notify_cb
        self.after_save = after_save  # async (record) → None, ex.: avaliação de alarmes
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._mqtt_client = None
        self._cmd_queue: queue.Queue = queue.Queue()
        self._active_transport: Optional[str] = None
        self._wifi_mqtt_client = None
        self._seen_seq: dict[tuple, float] = {}
        self._gw_status: dict = {
            "connected": False,
            "port": None,
            "mac": None,
            "fw": None,
            "sim_mode": False,
            "last_seen": None,
            "transport": None,
        }
        self._discovery_sent: set = set()
        self._air_temp_discovery: set = set()
        self._init_mqtt()

    def _init_mqtt(self) -> None:
        host = os.getenv("MQTT_HOST", "")
        if not host:
            return
        import paho.mqtt.client as mqtt
        self._mqtt_client = mqtt.Client()
        user = os.getenv("MQTT_USER", "")
        pwd = os.getenv("MQTT_PASS", "")
        if user:
            self._mqtt_client.username_pw_set(user, pwd)
        port = int(os.getenv("MQTT_PORT", "1883"))
        self._mqtt_client.on_connect = lambda c, *_: self._on_mqtt_connect()
        self._mqtt_client.on_message = lambda c, u, msg: self._on_config_set(msg.topic, msg.payload)
        self._mqtt_client.connect_async(host, port)
        self._mqtt_client.loop_start()
        logger.info("MQTT configurado: %s:%d", host, port)

    def _publish_mqtt(self, record: dict) -> None:
        if not self._mqtt_client:
            return
        alias = record["alias"]
        node_id = record["node_id"]
        sensor_id = record["sensor_id"]
        payload = json.dumps({
            "alias": alias,
            "distance_cm": record.get("distance_cm"),
            "level_cm": record.get("level_cm"),
            "pct": record.get("pct"),
            "volume_l": record.get("volume_l"),
            "rssi": record.get("rssi"),
            "vbat": record.get("vbat"),
            "seq": record.get("seq"),
            "ts": record.get("ts"),
        })
        topic = f"aguada/{node_id}/{sensor_id}/state"
        try:
            if (node_id, sensor_id) not in self._discovery_sent:
                self._publish_discovery(alias, record.get("name") or alias, topic)
                self._discovery_sent.add((node_id, sensor_id))
            self._mqtt_client.publish(topic, payload, retain=True)
        except Exception as e:
            logger.warning("MQTT publish error: %s", e)

    def _publish_discovery(self, alias: str, name: str, state_topic: str) -> None:
        """HA MQTT Discovery com os mesmos entity_ids do bridge HA (sensor.aguada_<alias>_*),
        que o package aguada do Home Assistant consome. Retido: sobrevive a restart do HA."""
        a = alias.lower()
        dev = {"name": alias, "identifiers": [f"aguada_{a}"], "manufacturer": "Aguada"}
        for key, label, vt, uom, dc, icon in _DISCOVERY_ENTITIES:
            cfg = {
                "name": f"{name} - {label}",
                "unique_id": f"aguada_{a}_{key}",
                "default_entity_id": f"sensor.aguada_{a}_{key}",
                "state_topic": state_topic,
                "value_template": vt,
                "device": dev,
                "icon": icon,
            }
            if uom:
                cfg["unit_of_measurement"] = uom
                cfg["state_class"] = "measurement"
            if dc:
                cfg["device_class"] = dc
            self._mqtt_client.publish(f"homeassistant/sensor/aguada_{a}_{key}/config",
                                      json.dumps(cfg), retain=True)
        logger.info("HA Discovery publicado: %s", alias)

    def _on_mqtt_connect(self) -> None:
        """Campos editáveis no HA para todo reservatório do YAML, com ou sem leitura."""
        self._mqtt_client.subscribe("aguada/+/+/config/+/set")
        for (node_id, sensor_id), params in list(RESERVOIR_INDEX.items()):
            self._publish_param_discovery(node_id, sensor_id, params)
            self._publish_params(node_id, sensor_id, params)

    def _publish_param_discovery(self, node_id: str, sensor_id: int, params: dict) -> None:
        a = params["alias"].lower()
        config_tp = f"aguada/{node_id}/{sensor_id}/config"
        dev = {"name": params["alias"], "identifiers": [f"aguada_{a}"], "manufacturer": "Aguada"}
        for param, (label, ent, unit, lo, hi, icon) in EDITABLE_PARAMS.items():
            uid = f"aguada_{a}_cfg_{param}"
            cfg = {
                "name": f"{params['name']} - {label}",
                "unique_id": uid,
                "default_entity_id": f"number.aguada_{a}_{ent}",
                "state_topic": config_tp,
                "value_template": "{{ value_json.%s }}" % param,
                "command_topic": f"{config_tp}/{param}/set",
                "min": lo, "max": hi, "step": 1, "mode": "box",
                "entity_category": "config",
                "unit_of_measurement": unit,
                "icon": icon,
                "device": dev,
            }
            self._mqtt_client.publish(f"homeassistant/number/{uid}/config", json.dumps(cfg), retain=True)

    def _publish_params(self, node_id: str, sensor_id: int, params: dict) -> None:
        state = {p: param_value(params, p) for p in EDITABLE_PARAMS}
        self._mqtt_client.publish(f"aguada/{node_id}/{sensor_id}/config", json.dumps(state), retain=True)

    def _on_config_set(self, topic: str, payload: bytes) -> None:
        """Edição no HA: valida, aplica em memória (vale na próxima leitura), grava no YAML."""
        parts = topic.split("/")  # aguada/<node>/<sid>/config/<param>/set
        if len(parts) != 6 or parts[3] != "config" or parts[5] != "set":
            return
        node_id, param = parts[1].lower(), parts[4]
        try:
            sensor_id = int(parts[2])
        except ValueError:
            return
        params = RESERVOIR_INDEX.get((node_id, sensor_id))
        if params is None or param not in EDITABLE_PARAMS:
            logger.warning("Config set ignorado: %s", topic)
            return
        lo, hi = EDITABLE_PARAMS[param][3], EDITABLE_PARAMS[param][4]
        try:
            v = float(payload.decode(errors="replace").strip())
        except ValueError:
            v = float("nan")
        if not (lo <= v <= hi):  # NaN também cai aqui
            logger.warning("Config rejeitada: %s %s=%r", params["alias"], param, payload)
        else:
            new = int(round(v))
            logger.info("Config %s %s: %s -> %s", params["alias"], param, param_value(params, param), new)
            params[_PARAM_KEY.get(param, param)] = new
            if not persist_param(node_id, params["alias"], param, new):
                logger.warning("Config %s %s só em memória (YAML não gravado)", params["alias"], param)
        self._publish_params(node_id, sensor_id, params)

    def get_status(self) -> dict:
        """Retorna status atual do gateway USB (thread-safe)."""
        return dict(self._gw_status)

    def start(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop
        serial_port = _detect_serial_port(os.getenv("SERIAL_PORT"))
        self._thread = threading.Thread(
            target=self._run, args=(serial_port,), daemon=True, name="bridge"
        )
        self._thread.start()
        logger.info("Bridge iniciado (porta=%s)", serial_port)

    def _run(self, serial_port: str) -> None:
        transport_mode = os.getenv("GATEWAY_TRANSPORT", "auto").strip().lower()
        allow_sim = os.getenv("BRIDGE_ALLOW_SIMULATION", "0").strip().lower() in {"1", "true", "yes", "on"}

        while True:
            serial_available = _is_serial_available(serial_port)
            try_serial = transport_mode == "serial" or (transport_mode == "auto" and serial_available)
            try_wifi   = transport_mode in ("wifi", "auto")

            if try_serial:
                try:
                    self._run_serial_once(serial_port)
                    continue
                except Exception as e:
                    self._gw_status["connected"] = False
                    self._active_transport = None
                    if not try_wifi:
                        if allow_sim:
                            logger.warning("Serial indisponível (%s) — simulação ativada", e)
                            self._gw_status["sim_mode"] = True
                            self._sim_loop()
                            return
                        logger.error("Serial indisponível (%s). Nova tentativa em 5s.", e)
                        time.sleep(5)
                        continue
                    logger.warning("Serial falhou (%s) — tentando WiFi", e)

            if try_wifi:
                try:
                    self._run_wifi_transport()
                    continue
                except Exception as e:
                    self._gw_status["connected"] = False
                    self._active_transport = None
                    if transport_mode == "wifi" and allow_sim:
                        logger.warning("WiFi indisponível (%s) — simulação ativada", e)
                        self._gw_status["sim_mode"] = True
                        self._sim_loop()
                        return
                    logger.error("WiFi transport falhou: %s — nova tentativa em 5s.", e)
                    time.sleep(5)
            elif not try_serial:
                logger.error("GATEWAY_TRANSPORT inválido: %r. Use 'auto', 'serial' ou 'wifi'.", transport_mode)
                time.sleep(10)

    def _run_serial_once(self, serial_port: str) -> None:
        """Abre a serial e lê em loop até falhar. Levanta exceção ao desconectar."""
        import serial as pyserial
        resolved_port = _detect_serial_port(serial_port)
        if resolved_port != serial_port:
            logger.warning("SERIAL_PORT ajustada automaticamente: %s -> %s", serial_port, resolved_port)
        ser = pyserial.Serial(resolved_port, 115200, timeout=1, dsrdtr=False, rtscts=False)
        logger.info("Serial aberto: %s", resolved_port)
        self._gw_status.update({
            "connected": True, "port": resolved_port, "sim_mode": False, "transport": "serial",
        })
        self._active_transport = "serial"
        try:
            ser.reset_input_buffer()
            ser.reset_output_buffer()
        except Exception as e:
            logger.debug("Reset de buffers serial ignorado: %s", e)

        if _should_pulse_dtr(resolved_port):
            try:
                ser.setDTR(False)
                time.sleep(0.15)
                ser.setDTR(True)
                logger.debug("Pulso DTR aplicado para resetar o gateway")
            except Exception as e:
                logger.debug("Pulso DTR ignorado: %s", e)
        else:
            logger.info("Pulso DTR desativado para USB CDC nativa: %s", resolved_port)

        self._drain_startup_serial(ser, 3.0)
        self._send_settime(ser)
        self._read_loop(ser)

    def _run_wifi_transport(self) -> None:
        """Subscreve MQTT do gateway WiFi e processa mensagens até desconectar."""
        import paho.mqtt.client as mqtt

        host = os.getenv("GW_MQTT_HOST") or os.getenv("MQTT_HOST", "")
        if not host:
            raise RuntimeError(
                "WiFi transport requer GW_MQTT_HOST (ou MQTT_HOST) configurado no .env"
            )

        port      = int(os.getenv("GW_MQTT_PORT") or os.getenv("MQTT_PORT", "1883"))
        user      = os.getenv("GW_MQTT_USER") or os.getenv("MQTT_USER", "")
        pwd       = os.getenv("GW_MQTT_PASS") or os.getenv("MQTT_PASS", "")
        topic_sub = os.getenv("GW_MQTT_TOPIC", "aguada/#")

        connected    = threading.Event()
        disconnected = threading.Event()

        def on_connect(client, userdata, flags, rc, properties=None):
            if rc == 0:
                client.subscribe(topic_sub)
                self._gw_status.update({
                    "connected": True, "sim_mode": False,
                    "transport": "wifi", "port": f"mqtt://{host}:{port}",
                })
                self._active_transport = "wifi"
                try:
                    client.publish("aguada/cmd/settime", json.dumps({"cmd": "SETTIME", "ts": int(time.time())}))
                except Exception as e:
                    logger.warning("WiFi transport: falha ao enviar SETTIME inicial: %s", e)
                logger.info(
                    "WiFi transport: conectado %s:%d, subscrito em %s", host, port, topic_sub
                )
            else:
                logger.error("WiFi transport: MQTT connect negado rc=%s", rc)
            connected.set()

        def on_message(client, userdata, msg):
            try:
                parts = msg.topic.split("/")
                if len(parts) == 4 and parts[3] == "config":  # aguada/<node>/<sid>/config
                    apply_remote_config(parts[1], parts[2], msg.payload)
                    return
                # Retido = último estado reenviado no (re)subscribe, não pacote novo
                if msg.retain:
                    return
                try:
                    raw = json.loads(msg.payload)
                except ValueError:
                    return  # status em texto puro ("online"/"offline") no mesmo broker
                if not isinstance(raw, dict) or "type" not in raw:
                    return  # estado calculado pelo bridge HA (aguada/<node>/<sid>/state) etc.
                self._gw_status["last_seen"] = int(time.time())
                if raw.get("type") == "GATEWAY_STATUS":
                    if raw.get("mac"):
                        self._gw_status["mac"] = raw["mac"]
                    if raw.get("fw"):
                        self._gw_status["fw"] = raw["fw"]
                self._handle(raw)
            except Exception as e:
                logger.warning("WiFi transport: erro on_message: %s", e)

        def on_disconnect(client, userdata, disconnect_flags, rc, properties=None):
            self._gw_status["connected"] = False
            logger.warning(
                "WiFi transport: MQTT desconectado rc=%s flags=%s", rc, disconnect_flags
            )
            disconnected.set()

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="aguada-bridge-rx")
        client.on_connect    = on_connect
        client.on_message    = on_message
        client.on_disconnect = on_disconnect
        if user:
            client.username_pw_set(user, pwd)

        self._wifi_mqtt_client = client
        client.connect(host, port, keepalive=60)
        client.loop_start()
        try:
            if not connected.wait(timeout=15):
                raise RuntimeError(f"Timeout ao conectar MQTT WiFi {host}:{port}")
            if not self._gw_status.get("connected"):
                raise RuntimeError(f"MQTT WiFi negou conexão {host}:{port}")
            disconnected.wait()  # bloqueia até desconexão
            raise RuntimeError("MQTT WiFi desconectado")
        finally:
            self._wifi_mqtt_client = None
            client.loop_stop()
            try:
                client.disconnect()
            except Exception:
                pass

    def send_cmd(self, cmd_dict: dict) -> None:
        """Enfileira/envia um comando JSON para o gateway (serial ou WiFi)."""
        if self._active_transport == "wifi":
            self._send_cmd_wifi(cmd_dict)
        else:
            self._cmd_queue.put(cmd_dict)

    def _send_cmd_wifi(self, cmd_dict: dict) -> None:
        """Publica comando via MQTT para o gateway WiFi."""
        if not self._wifi_mqtt_client:
            logger.warning("send_cmd WiFi: cliente MQTT não disponível")
            return
        cmd = cmd_dict.get("cmd", "").upper()
        if cmd == "RESTART":
            topic = "aguada/cmd/restart"
        elif cmd == "CONFIG":
            topic = "aguada/cmd/config"
        elif cmd == "SETTIME":
            topic = "aguada/cmd/settime"
        else:
            topic = f"aguada/cmd/{cmd.lower()}"
        try:
            self._wifi_mqtt_client.publish(topic, json.dumps(cmd_dict))
            logger.info("CMD WiFi: topic=%s payload=%s", topic, cmd_dict)
        except Exception as e:
            logger.error("send_cmd WiFi: erro MQTT: %s", e)

    def _flush_cmd_queue(self, ser) -> None:
        """Envia todos os comandos pendentes na fila para o serial."""
        try:
            while True:
                cmd_dict = self._cmd_queue.get_nowait()
                raw = json.dumps(cmd_dict) + "\n"
                ser.write(raw.encode())
                logger.info("CMD enviado ao gateway: %s", raw.strip())
        except queue.Empty:
            pass

    def _send_settime(self, ser) -> None:
        """Sincroniza o timestamp do gateway com o servidor."""
        ts = int(time.time())
        cmd = json.dumps({"cmd": "SETTIME", "ts": ts}) + "\n"
        ser.write(cmd.encode())
        logger.info("SETTIME enviado ao gateway: ts=%d", ts)

    def _normalize_serial_line(self, raw_line: str) -> str:
        line = raw_line.strip()
        if not line:
            return ""
        if line.startswith("{"):
            return line
        json_start = line.find("{")
        if json_start >= 0:
            return line[json_start:].strip()
        return line

    def _read_serial_line(self, ser) -> str:
        raw = ser.readline().decode("utf-8", errors="replace")
        return self._normalize_serial_line(raw)

    def _handle_non_json_serial_line(self, line: str) -> None:
        lowered = line.lower()
        if "waiting for download" in lowered or "download_boot" in lowered:
            logger.error("Gateway entrou em modo bootloader UART: %s", line[:160])
            return
        if line.startswith("ets ") or line.startswith("rst:") or "boot:" in lowered:
            logger.info("Boot do gateway: %s", line[:160])
            return
        logger.debug("Linha serial não-JSON: %r", line[:160])

    def _drain_startup_serial(self, ser, duration_s: float) -> None:
        deadline = time.time() + duration_s
        logger.info("Aguardando %.1fs para boot do gateway...", duration_s)
        while time.time() < deadline:
            line = self._read_serial_line(ser)
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                self._handle_non_json_serial_line(line)
                continue

            if raw.get("type") == "GATEWAY_READY":
                logger.info("GATEWAY_READY recebido durante startup")
            self._handle(raw)

    def _read_loop(self, ser) -> None:
        while True:
            try:
                self._flush_cmd_queue(ser)
                line = self._read_serial_line(ser)
                if not line:
                    continue
                logger.debug("Serial RX: %r", line)
                try:
                    raw = json.loads(line)
                except json.JSONDecodeError:
                    self._handle_non_json_serial_line(line)
                    continue
                # Reenvia SETTIME quando gateway reinicia
                if raw.get("type") == "GATEWAY_READY":
                    logger.info("GATEWAY_READY recebido — reenviando SETTIME")
                    self._gw_status["mac"] = raw.get("mac")
                    self._gw_status["fw"] = raw.get("fw")
                    self._gw_status["last_seen"] = int(time.time())
                    self._send_settime(ser)
                self._handle(raw)
            except Exception as e:
                msg = str(e).lower()
                serial_drop_markers = (
                    "device reports readiness to read but returned no data",
                    "input/output error",
                    "device disconnected",
                    "port is closed",
                    "bad file descriptor",
                )
                if any(m in msg for m in serial_drop_markers):
                    logger.error("Serial desconectada durante leitura (%s). Reconectando...", e)
                    try:
                        ser.close()
                    except Exception:
                        pass
                    raise
                logger.error("Erro no read_loop: %s", e)
                time.sleep(1)

    def _sim_loop(self) -> None:
        """Gera leituras sintéticas para todos os reservatórios a cada 30s."""
        logger.info("Modo simulação ativo")
        # Estado simulado por alias
        aliases_params = {}
        for (node_id, sensor_id), params in list(RESERVOIR_INDEX.items()):
            alias = params["alias"]
            aliases_params[alias] = {"node_id": node_id, "sensor_id": sensor_id, "params": params}

        state = {alias: 60.0 for alias in aliases_params}

        while True:
            ts = int(time.time())
            for alias, info in aliases_params.items():
                params = info["params"]
                state[alias] = max(5.0, min(100.0, state[alias] + random.uniform(-2, 1)))
                pct = state[alias]
                level = pct / 100 * params["level_max_cm"]
                distance = params["level_max_cm"] - level + params["sensor_offset_cm"]
                raw = {
                    "type": "SENSOR",
                    "node_id": info["node_id"],
                    "sensor_id": info["sensor_id"],
                    "distance_cm": round(distance, 1),
                    "rssi": random.randint(-80, -50),
                    "vbat": random.choice([32, 33, 34]),
                    "flags": 0,
                    "seq": random.randint(0, 65535),
                    "ts": ts,
                }
                self._handle(raw)
            time.sleep(30)

    def _seen_before(self, raw: dict) -> bool:
        """O mesmo pacote chega por dois caminhos (espelho WiFi do gateway + republicação
        do bridge USB). Mesmo (node, sensor, seq) dentro de SEQ_DEDUP_TTL_S = duplicado."""
        seq = raw.get("seq")
        if seq is None:
            return False
        key = (str(raw.get("node_id", "")).lower(), str(raw.get("sensor_id")), seq)
        now = time.monotonic()
        last = self._seen_seq.get(key)
        if last is not None and now - last < SEQ_DEDUP_TTL_S:
            return True
        self._seen_seq[key] = now
        if len(self._seen_seq) > 512:
            self._seen_seq = {k: t for k, t in self._seen_seq.items() if now - t < SEQ_DEDUP_TTL_S}
        return False

    def _handle(self, raw: dict) -> None:
        msg_type = str(raw.get("type", "?")).upper()
        if msg_type == "SENSOR":
            if self._seen_before(raw):
                logger.debug("SENSOR duplicado ignorado: %s", raw)
                return
            logger.info(
                "SENSOR recebido: node=%s sensor=%s dist=%s rssi=%s ts=%s",
                raw.get("node_id"), raw.get("sensor_id"),
                raw.get("distance_cm"), raw.get("rssi"), raw.get("ts"),
            )
        elif msg_type == "HELLO":
            # Node reiniciou: seq recomeça, esquece as entradas de dedup dele
            nid = str(raw.get("node_id", "")).lower()
            self._seen_seq = {k: t for k, t in self._seen_seq.items() if k[0] != nid}
            asyncio.run_coroutine_threadsafe(self._handle_hello(raw), self._loop)
            return
        elif msg_type == "HEARTBEAT" and int(raw.get("sensor_id", 0)) == SENSOR_ID_T_EXT:
            self._handle_air_temp(raw)
            return
        elif msg_type not in ("GATEWAY_READY", "GATEWAY_STATUS", "CMD_ACK"):
            logger.debug("Mensagem tipo=%s: %s", msg_type, raw)
        record = _process_message(raw)
        if record is None:
            if msg_type == "SENSOR":
                logger.warning(
                    "SENSOR descartado por _process_message: node=%s sensor=%s flags=%s",
                    raw.get("node_id"), raw.get("sensor_id"), raw.get("flags"),
                )
            return
        asyncio.run_coroutine_threadsafe(self._save_and_notify(record), self._loop)

    def _handle_air_temp(self, raw: dict) -> None:
        """Temperatura do ar do reservatório (sonda da compensação do ultrassom)."""
        node_id = str(raw.get("node_id", "")).lower()
        node_id = NODE_ALIASES.get(node_id, node_id)
        params = RESERVOIR_INDEX.get((node_id, 1))
        if params is None or not self._mqtt_client:
            return
        temp = air_temp_c(raw.get("distance_cm"), raw.get("flags", 0))
        logger.info("Temperatura do ar %s: %s °C", params["alias"], temp)
        topic = f"aguada/{node_id}/air_temp/state"
        if node_id not in self._air_temp_discovery:
            a = params["alias"].lower()
            cfg = {
                "name": f"{params['name']} - Temperatura do ar",
                "unique_id": f"aguada_{a}_temp_ar",
                "default_entity_id": f"sensor.aguada_{a}_temp_ar",
                "state_topic": topic,
                "value_template": "{{ value_json.temp_c }}",
                "unit_of_measurement": "°C",
                "device_class": "temperature",
                "state_class": "measurement",
                "device": {"name": params["alias"], "identifiers": [f"aguada_{a}"],
                           "manufacturer": "Aguada"},
            }
            self._mqtt_client.publish(f"homeassistant/sensor/aguada_{a}_temp_ar/config",
                                      json.dumps(cfg), retain=True)
            self._air_temp_discovery.add(node_id)
        self._mqtt_client.publish(topic, json.dumps({"temp_c": temp, "ts": int(time.time())}),
                                  retain=True)

    async def _handle_hello(self, raw: dict) -> None:
        import aiosqlite
        node_id = raw.get("node_id", "").lower()
        if not node_id:
            return
        node = {
            "node_id": node_id,
            "num_sensors": int(raw.get("num_sensors", 0)),
            "fw_version": raw.get("fw_version"),
            "last_seen": int(time.time()),
            "last_rssi": raw.get("rssi"),
            "last_vbat": _vbat_volts(raw.get("vbat")),
            "flags": raw.get("flags", 0),
        }
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await upsert_node(conn, node)
            logger.info("HELLO: node=%s num_sensors=%d fw=%s rssi=%s",
                        node_id, node["num_sensors"], node["fw_version"], node["last_rssi"])
        except Exception as e:
            logger.error("Erro ao salvar node no DB: %s", e)
        self.notify_cb({"type": "node_seen", "node_id": node_id,
                        "num_sensors": node["num_sensors"], "fw_version": node["fw_version"],
                        "last_seen": node["last_seen"], "last_rssi": node["last_rssi"]})

    async def _save_and_notify(self, record: dict) -> None:
        import aiosqlite
        try:
            async with aiosqlite.connect(self.db_path) as conn:
                conn.row_factory = aiosqlite.Row
                await insert_reading(conn, record)
                await upsert_state(conn, record)
                await upsert_node_seen(
                    conn,
                    node_id=record["node_id"],
                    sensor_id=record["sensor_id"],
                    last_seen=record["ts"],
                    last_rssi=record.get("rssi"),
                    last_vbat=record.get("vbat"),
                    flags=record.get("flags", 0),
                )
            logger.info(
                "Gravado: alias=%s dist=%.1f level=%.1f ts=%d",
                record["alias"], record.get("distance_cm") or 0,
                record.get("level_cm") or 0, record["ts"],
            )
        except Exception as e:
            logger.error("Erro ao gravar no DB: %s — registro: %s", e, record)
            return
        self.notify_cb(record)
        self._publish_mqtt(record)
        if self.after_save:
            try:
                await self.after_save(record)
            except Exception as e:
                logger.error("after_save falhou: %s — registro: %s", e, record.get("alias"))
