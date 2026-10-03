# backend/qualidade.py
"""Laudos de qualidade da água (Normas_Tecnicas.md §9).

Limites de referência da Portaria GM/MS nº 888/2021, que substituiu a 2.914/2011 citada nas
normas do projeto. O limite usado fica gravado junto do resultado, então mudar a tabela abaixo
não reescreve laudos antigos.
"""
from __future__ import annotations

import aiosqlite

# ponytail: catálogo fixo dos parâmetros de rotina; parâmetro novo entra aqui.
# presenca=True → valor 0 = ausente, 1 = presente em 100 mL.
PARAMETROS = {
    "ph":                {"nome": "pH",                    "unidade": "",           "min": 6.0, "max": 9.0},
    "cloro_livre":       {"nome": "Cloro residual livre",  "unidade": "mg/L",       "min": 0.2, "max": 5.0},
    "turbidez":          {"nome": "Turbidez",              "unidade": "uT",         "min": None, "max": 5.0},
    "cor_aparente":      {"nome": "Cor aparente",          "unidade": "uH",         "min": None, "max": 15.0},
    "fluoreto":          {"nome": "Fluoreto",              "unidade": "mg/L",       "min": None, "max": 1.5},
    "coliformes_totais": {"nome": "Coliformes totais",     "unidade": "em 100 mL",  "min": None, "max": 0.0, "presenca": True},
    "e_coli":            {"nome": "Escherichia coli",      "unidade": "em 100 mL",  "min": None, "max": 0.0, "presenca": True},
}

# Pontos iniciais: saída de cada reservatório de água potável
PONTOS_PADRAO = [
    ("Casa de Bombas Ilha das Flores (CBIF)", "CBIF"),
    ("Cisternas Ilha do Engenho (CIE)", "CIE"),
    ("Casa de Bombas Nº3 (CB3)", "CB3"),
    ("Castelo de Consumo (CON)", "CON"),
]


def conforme(parametro: str, valor: float) -> bool:
    p = PARAMETROS[parametro]
    return (p["min"] is None or valor >= p["min"]) and (p["max"] is None or valor <= p["max"])


async def seed_pontos(conn: aiosqlite.Connection) -> None:
    async with conn.execute("SELECT COUNT(*) FROM pontos_coleta") as cur:
        if (await cur.fetchone())[0]:
            return
    await conn.executemany("INSERT INTO pontos_coleta (nome, reservatorio) VALUES (?, ?)", PONTOS_PADRAO)
    await conn.commit()


async def list_pontos(conn: aiosqlite.Connection) -> list[dict]:
    conn.row_factory = aiosqlite.Row
    async with conn.execute("SELECT * FROM pontos_coleta ORDER BY id") as cur:
        return [dict(r) for r in await cur.fetchall()]


async def insert_laudo(conn: aiosqlite.Connection, laudo: dict, resultados: list[dict]) -> int:
    cur = await conn.execute(
        """INSERT INTO laudos (ponto_id, data_coleta, laboratorio, numero, arquivo, obs, criado_ts, criado_por)
           VALUES (:ponto_id, :data_coleta, :laboratorio, :numero, :arquivo, :obs, :criado_ts, :criado_por)""",
        laudo,
    )
    laudo_id = cur.lastrowid
    await conn.executemany(
        """INSERT INTO laudo_parametros (laudo_id, parametro, valor, unidade, limite_min, limite_max, conforme)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        [(laudo_id, r["parametro"], r["valor"], r["unidade"], r["limite_min"], r["limite_max"], int(r["conforme"]))
         for r in resultados],
    )
    await conn.commit()
    return laudo_id


async def list_laudos(conn: aiosqlite.Connection, ponto_id: int | None = None, limit: int = 100) -> list[dict]:
    conn.row_factory = aiosqlite.Row
    where, args = ("WHERE l.ponto_id = ?", [ponto_id]) if ponto_id else ("", [])
    async with conn.execute(
        f"""SELECT l.*, p.nome AS ponto FROM laudos l JOIN pontos_coleta p ON p.id = l.ponto_id
            {where} ORDER BY l.data_coleta DESC, l.id DESC LIMIT ?""", (*args, limit)
    ) as cur:
        laudos = [dict(r) for r in await cur.fetchall()]
    if not laudos:
        return []
    marks = ",".join("?" * len(laudos))
    async with conn.execute(f"SELECT * FROM laudo_parametros WHERE laudo_id IN ({marks}) ORDER BY id",
                            [l["id"] for l in laudos]) as cur:
        params = [dict(r) for r in await cur.fetchall()]
    for l in laudos:
        l["parametros"] = [p for p in params if p["laudo_id"] == l["id"]]
        l["conforme"] = all(p["conforme"] for p in l["parametros"])
    return laudos


async def get_laudo_arquivo(conn: aiosqlite.Connection, laudo_id: int) -> str | None:
    async with conn.execute("SELECT arquivo FROM laudos WHERE id = ?", (laudo_id,)) as cur:
        row = await cur.fetchone()
    return row[0] if row else None
