#!/usr/bin/env python3
"""
Minimal MQTT 3.1.1 broker — supports CONNECT, PUBLISH, SUBSCRIBE, PING.
Single-file, no dependencies beyond stdlib. Enough for bridge.py + HA.
"""
import socket, threading, struct, logging, time

logging.basicConfig(level=logging.INFO,
    format="%(asctime)s %(levelname)-7s broker: %(message)s",
    datefmt="%H:%M:%S")
log = logging.getLogger("broker")

# ── packet types ──────────────────────────────────────────────────────────────
CONNECT=1; CONNACK=2; PUBLISH=3; PUBACK=4; SUBSCRIBE=8; SUBACK=9
UNSUBSCRIBE=10; UNSUBACK=11; PINGREQ=12; PINGRESP=13; DISCONNECT=14

# ── retained store & subscriptions ───────────────────────────────────────────
retained: dict[str, bytes] = {}   # topic → payload
clients: dict[str, "Client"] = {} # client_id → Client
clients_lock = threading.Lock()

def topic_match(pattern: str, topic: str) -> bool:
    pp = pattern.split("/"); tp = topic.split("/")
    i = j = 0
    while i < len(pp) and j < len(tp):
        if pp[i] == "#": return True
        if pp[i] == "+" or pp[i] == tp[j]:
            i += 1; j += 1
        else:
            return False
    return i == len(pp) and j == len(tp)

def deliver(topic: str, payload: bytes, qos: int, retain: bool):
    if retain:
        retained[topic] = payload
    with clients_lock:
        targets = list(clients.values())
    for c in targets:
        for sub_topic, sub_qos in list(c.subs.items()):
            if topic_match(sub_topic, topic):
                try:
                    c.send_publish(topic, payload, min(qos, sub_qos))
                except Exception:
                    pass

# ── wire helpers ──────────────────────────────────────────────────────────────
def encode_remaining(n: int) -> bytes:
    out = b""
    while True:
        b = n % 128; n //= 128
        out += bytes([b | (0x80 if n else 0)])
        if not n: break
    return out

def read_remaining(sock) -> int:
    mul = 1; val = 0
    for _ in range(4):
        b = sock.recv(1)
        if not b: return -1
        b = b[0]; val += (b & 127) * mul; mul *= 128
        if not (b & 128): break
    return val

def read_exactly(sock, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        d = sock.recv(n - len(buf))
        if not d: raise ConnectionError("closed")
        buf += d
    return buf

def utf8(data: bytes, off: int):
    length = struct.unpack_from("!H", data, off)[0]
    return data[off+2:off+2+length].decode(), off+2+length

# ── client handler ────────────────────────────────────────────────────────────
class Client:
    def __init__(self, sock, addr):
        self.sock = sock
        self.addr = addr
        self.client_id = ""
        self.subs: dict[str, int] = {}
        self._lock = threading.Lock()
        self._pid = 1

    def send_publish(self, topic: str, payload: bytes, qos: int):
        t = topic.encode()
        hdr = struct.pack("!H", len(t)) + t
        if qos > 0:
            hdr += struct.pack("!H", self._pid); self._pid = (self._pid % 65535) + 1
        pkt = bytes([(PUBLISH << 4) | (qos << 1)]) + encode_remaining(len(hdr) + len(payload)) + hdr + payload
        with self._lock:
            self.sock.sendall(pkt)

    def handle(self):
        try:
            while True:
                hdr = self.sock.recv(1)
                if not hdr: break
                cmd = hdr[0] >> 4
                flags = hdr[0] & 0xF
                rlen = read_remaining(self.sock)
                if rlen < 0: break
                data = read_exactly(self.sock, rlen) if rlen else b""

                if cmd == CONNECT:
                    # protocol name + level + flags + keepalive
                    pname, off = utf8(data, 0)
                    level = data[off]; off += 1
                    conn_flags = data[off]; off += 1
                    keepalive = struct.unpack_from("!H", data, off)[0]; off += 2
                    client_id, off = utf8(data, off)
                    self.client_id = client_id or f"anon-{id(self)}"
                    log.info("CONNECT cid=%s ka=%ds", self.client_id, keepalive)
                    with clients_lock:
                        # evict existing session
                        old = clients.get(self.client_id)
                        if old and old is not self:
                            try: old.sock.close()
                            except: pass
                        clients[self.client_id] = self
                    # CONNACK rc=0
                    self.sock.sendall(bytes([CONNACK << 4, 2, 0, 0]))

                elif cmd == PUBLISH:
                    retain = bool(flags & 1)
                    qos    = (flags >> 1) & 3
                    dup    = bool(flags & 8)
                    topic, off = utf8(data, 0)
                    if qos > 0:
                        pid = struct.unpack_from("!H", data, off)[0]; off += 2
                        # PUBACK
                        self.sock.sendall(bytes([PUBACK << 4, 2]) + struct.pack("!H", pid))
                    payload = data[off:]
                    log.debug("PUBLISH %s (%dB) retain=%s", topic, len(payload), retain)
                    deliver(topic, payload, qos, retain)

                elif cmd == SUBSCRIBE:
                    pid = struct.unpack_from("!H", data, 0)[0]; off = 2
                    granted = []
                    while off < len(data):
                        t, off = utf8(data, off)
                        qos_req = data[off]; off += 1
                        self.subs[t] = qos_req; granted.append(qos_req)
                        log.info("SUBSCRIBE cid=%s topic=%s", self.client_id, t)
                        # send retained messages
                        for rt, rp in list(retained.items()):
                            if topic_match(t, rt):
                                self.send_publish(rt, rp, qos_req)
                    suback = bytes([SUBACK << 4, 2 + len(granted)]) + struct.pack("!H", pid) + bytes(granted)
                    self.sock.sendall(suback)

                elif cmd == UNSUBSCRIBE:
                    pid = struct.unpack_from("!H", data, 0)[0]; off = 2
                    while off < len(data):
                        t, off = utf8(data, off)
                        self.subs.pop(t, None)
                    self.sock.sendall(bytes([UNSUBACK << 4, 2]) + struct.pack("!H", pid))

                elif cmd == PINGREQ:
                    self.sock.sendall(bytes([PINGRESP << 4, 0]))

                elif cmd == DISCONNECT:
                    break

        except Exception as e:
            log.debug("Client %s error: %s", self.client_id, e)
        finally:
            self.sock.close()
            with clients_lock:
                if clients.get(self.client_id) is self:
                    del clients[self.client_id]
            log.info("Disconnected cid=%s", self.client_id)

# ── server ────────────────────────────────────────────────────────────────────
def run(host="0.0.0.0", port=1883):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((host, port))
    srv.listen(32)
    log.info("Listening on %s:%d", host, port)
    while True:
        sock, addr = srv.accept()
        c = Client(sock, addr)
        threading.Thread(target=c.handle, daemon=True).start()

if __name__ == "__main__":
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", default=1883, type=int)
    p.add_argument("--debug", action="store_true")
    a = p.parse_args()
    if a.debug:
        logging.getLogger().setLevel(logging.DEBUG)
    run(a.host, a.port)
