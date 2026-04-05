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
import threading
import time
from glob import glob
from pathlib import Path
from typing import Callable, Optional

import yaml

from .calc import calc_level
from .db import insert_reading, upsert_state, upsert_node, upsert_node_seen

logger = logging.getLogger("bridge")

# Carrega reservoirs.yaml uma vez
_yaml_path = Path(__file__).parent / "reservoirs.yaml"
_raw = yaml.safe_load(_yaml_path.read_text())["reservoirs"]

# Índice: (node_id_lower, sensor_id) → dict de parâmetros
RESERVOIR_INDEX: dict[tuple[str, int], dict] = {}
for _node_id, _sensors in _raw.items():
    for _s in _sensors:
        RESERVOIR_INDEX[(_node_id.lower(), _s["sensor_id"])] = _s


FLAG_SENSOR_ERROR = 1 << 2


def _detect_serial_port(configured_port: Optional[str]) -> str:
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
    for pattern in ["/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"]:
        for p in glob(pattern):
            if Path(p).exists():
                return True
    return False


def _process_message(raw: dict) -> Optional[dict]:
    """Valida e enriquece uma mensagem do gateway. Retorna dict pronto para DB ou None."""
    try:
        # Só processa pacotes SENSOR
        if raw.get("type") != "SENSOR":
            return None

        node_id = raw.get("node_id", "").lower()
        sensor_id = int(raw.get("sensor_id", 0))
        distance_cm = raw.get("distance_cm")
        rssi = raw.get("rssi")
        vbat_raw = raw.get("vbat")
        seq = raw.get("seq", 0)
        # Timestamp sempre pelo servidor — gateway e nós não têm RTC confiável.
        ts = int(time.time())
        vbat = vbat_raw / 10.0 if vbat_raw is not None else None

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
    def __init__(self, db_path: str, notify_cb: Callable[[dict], None]):
        self.db_path = db_path
        self.notify_cb = notify_cb
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._mqtt_client = None
        self._cmd_queue: queue.Queue = queue.Queue()
        self._active_transport: Optional[str] = None
        self._wifi_mqtt_client = None
        self._gw_status: dict = {
            "connected": False,
            "port": None,
            "mac": None,
            "fw": None,
            "sim_mode": False,
            "last_seen": None,
            "transport": None,
        }
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
            self._mqtt_client.publish(topic, payload, retain=True)
        except Exception as e:
            logger.warning("MQTT publish error: %s", e)

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
                raw = json.loads(msg.payload.decode("utf-8"))
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
        for (node_id, sensor_id), params in RESERVOIR_INDEX.items():
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

    def _handle(self, raw: dict) -> None:
        msg_type = raw.get("type", "?")
        if msg_type == "SENSOR":
            logger.info(
                "SENSOR recebido: node=%s sensor=%s dist=%s rssi=%s ts=%s",
                raw.get("node_id"), raw.get("sensor_id"),
                raw.get("distance_cm"), raw.get("rssi"), raw.get("ts"),
            )
        elif msg_type == "HELLO":
            asyncio.run_coroutine_threadsafe(self._handle_hello(raw), self._loop)
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
            "last_vbat": (raw.get("vbat") / 10.0) if raw.get("vbat") is not None else None,
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
