# backend/alarms.py
"""Alarmes de nível e falhas de sensor com histerese (Normas_Tecnicas.md §3.4, §5, §10).

Cada transição vira um evento insert-only na tabela `events`: o alarme abre com tipo
alarme/falha e fecha com um evento informativo `normalizado` que aponta para ele (ref_id).
O estado ativo é reconstruído do banco ao subir, então reinício não duplica alarme.
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Optional

import aiosqlite

from .db import ONLINE_TIMEOUT_S, get_active_alarms, get_all_states, insert_event

logger = logging.getLogger("alarms")

# ponytail: limites globais em % do volume. Por reservatório (reservoirs.yaml) quando os
# níveis operacionais de cada um forem definidos; hoje só existe volume/altura máximos.
LIMITS = {"critico": 20.0, "baixo": 35.0, "alto": 98.0}
HYST_PCT = 3.0          # dispara no limite, normaliza só depois de voltar HYST_PCT além dele
JUMP_CM = 50.0          # salto abrupto: > 0,5 m ...
JUMP_WINDOW_S = 300     # ... em 5 min (§3.4)


def duration(minutes: int) -> str:
    if minutes < 60:
        return f"{minutes} min"
    if minutes < 1440:
        return f"{minutes // 60} h {minutes % 60:02d} min"
    return f"{minutes // 1440} dias"


def level_band(pct: Optional[float], current: Optional[str]) -> Optional[str]:
    """Faixa de nível com histerese: None (normal), 'baixo', 'critico' ou 'alto'."""
    if pct is None:
        return current
    if pct <= LIMITS["critico"] or (current == "critico" and pct <= LIMITS["critico"] + HYST_PCT):
        return "critico"
    if pct <= LIMITS["baixo"] or (current in ("critico", "baixo") and pct <= LIMITS["baixo"] + HYST_PCT):
        return "baixo"
    if pct >= LIMITS["alto"] or (current == "alto" and pct >= LIMITS["alto"] - HYST_PCT):
        return "alto"
    return None


_BAND_EVENT = {
    "critico": ("alarme", "critico", "nivel_critico", "Nível crítico"),
    "baixo":   ("alarme", "alerta",  "nivel_baixo",   "Nível baixo"),
    "alto":    ("alarme", "alerta",  "nivel_alto",    "Nível alto (risco de transbordo)"),
}


class AlarmEngine:
    def __init__(self, db_path: str, notify: Callable[[dict], None] = lambda ev: None):
        self.db_path = db_path
        self.notify = notify
        self.active: dict[tuple[str, str], dict] = {}     # (alias, grupo) → evento aberto
        self.last: dict[str, tuple[int, float]] = {}      # alias → (ts, level_cm) p/ salto

    async def load(self) -> None:
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            for ev in await get_active_alarms(conn):
                self.active.setdefault((ev["entidade_id"], self._group(ev["codigo"])), ev)

    @staticmethod
    def _group(codigo: str) -> str:
        return "nivel" if codigo.startswith("nivel_") else codigo

    async def _emit(self, conn, ev: dict) -> dict:
        saved = await insert_event(conn, {"ts": int(time.time()), **ev})
        logger.info("evento %s %s %s: %s", saved["tipo"], saved["entidade_id"], saved["codigo"], saved["descricao"])
        self.notify(saved)
        return saved

    async def _open(self, conn, alias: str, group: str, ev: dict) -> None:
        if (alias, group) in self.active:
            return
        self.active[(alias, group)] = await self._emit(conn, ev)

    async def _close(self, conn, alias: str, group: str, descricao: str, valor=None) -> None:
        opened = self.active.pop((alias, group), None)
        if not opened:
            return
        await self._emit(conn, {"tipo": "informativo", "severidade": "info", "entidade": opened["entidade"],
                                "entidade_id": alias, "codigo": "normalizado", "descricao": descricao,
                                "valor": valor, "ref_id": opened["id"]})

    async def on_reading(self, record: dict) -> None:
        """Chamado a cada leitura gravada (sensor ou entrada manual)."""
        alias, name = record["alias"], record.get("name") or record["alias"]
        pct, level, ts = record.get("pct"), record.get("level_cm"), int(record.get("ts") or time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            # leitura chegou: sensor voltou
            await self._close(conn, alias, "sensor_offline", f"{name}: sensor voltou a comunicar")

            if record.get("out_of_range"):
                await self._open(conn, alias, "sensor_fora_faixa", {
                    "tipo": "falha", "severidade": "alerta", "entidade": "sensor", "entidade_id": alias,
                    "codigo": "sensor_fora_faixa", "valor": record.get("distance_cm"),
                    "descricao": f"{name}: leitura fora da faixa do reservatório (distância {record.get('distance_cm')} cm)"})
            else:
                await self._close(conn, alias, "sensor_fora_faixa", f"{name}: leitura voltou à faixa")

            prev = self.last.get(alias)
            if level is not None:
                if prev and ts - prev[0] <= JUMP_WINDOW_S and abs(level - prev[1]) > JUMP_CM:
                    # pontual (não fica ativo): informativo com severidade de alerta
                    await self._emit(conn, {"tipo": "informativo", "severidade": "alerta", "entidade": "sensor", "entidade_id": alias,
                                            "codigo": "sensor_salto", "valor": round(level - prev[1], 1),
                                            "descricao": f"{name}: salto de {level - prev[1]:+.0f} cm em {ts - prev[0]} s (leitura suspeita)",
                                            "ref_id": None})
                self.last[alias] = (ts, level)

            current = self.active.get((alias, "nivel"))
            band_now = current["codigo"].removeprefix("nivel_") if current else None
            band = level_band(None if record.get("out_of_range") else pct, band_now)
            if band != band_now:
                if band_now:
                    await self._close(conn, alias, "nivel", f"{name}: nível normalizado ({pct:.0f}%)" if band is None
                                      else f"{name}: saiu de {_BAND_EVENT[band_now][3].lower()} ({pct:.0f}%)", pct)
                if band:
                    tipo, sev, codigo, texto = _BAND_EVENT[band]
                    await self._open(conn, alias, "nivel", {"tipo": tipo, "severidade": sev, "entidade": "reservatorio",
                                                            "entidade_id": alias, "codigo": codigo, "valor": pct,
                                                            "descricao": f"{name}: {texto.lower()} — {pct:.0f}%"})

    async def check_offline(self) -> None:
        """Rodado periodicamente: reservatório sem leitura há mais de ONLINE_TIMEOUT_S = falha crítica."""
        now = int(time.time())
        async with aiosqlite.connect(self.db_path) as conn:
            conn.row_factory = aiosqlite.Row
            for st in await get_all_states(conn):
                if st["online"]:
                    continue
                minutes = (now - (st["ts"] or 0)) // 60
                await self._open(conn, st["alias"], "sensor_offline", {
                    "tipo": "falha", "severidade": "critico", "entidade": "sensor", "entidade_id": st["alias"],
                    "codigo": "sensor_offline", "valor": minutes,
                    "descricao": f"{st['name'] or st['alias']}: sem comunicação há {duration(minutes)}"})
