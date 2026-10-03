#!/usr/bin/env python3
"""Extrai as redes do PDF "PROJETO REDE INCÊNDIO E AGUADA" como GeoJSON para o mapa.

Uso: python3 tools/georef_plantas.py "<caminho do PDF>"

Saída: frontend/assets/plantas/redes.geojson, uma feição por camada (propriedade `layer`):
incendio, agua, predios, areas, os rótulos das Áreas A/B/C e os pontos dos símbolos —
hidrante (folha 1), registro (as duas folhas) e hidrometro (caixa "H" da folha 2). Os nomes
(HID-0xx, prédio e vazão) vêm de tools/plantas_rotulos.json, lido à mão na planta.

O PDF é vetor de CAD (A0, 1:1000, texto em traços SHX, sem layers): as camadas saem pela
espessura do traço — 2,09 = tubulação (folha 1 incêndio, folha 2 água potável), 4,18 = prédios,
4,70 = limites das Áreas. Não há coordenadas no PDF: o encaixe vem de pontos de controle
casados à mão entre a planta e o satélite (tiles z17 de leaflet-tiles-sat). Resíduo ~3 m;
conferido contra o OSM: Res. Elevado Nº1 = CON (5 m), Nº2 = CAV (14 m), CB03 (8 m),
CB02 (8 m), CB01 = "Casa de Bombas Nº2" da planta (9 m).
"""
from __future__ import annotations

import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

DPI = 200            # referência dos pontos de controle (px da página girada 90°)
PAGE_W_PT = 2384.0   # largura da folha A0 em pt (antes de girar)
# Área de desenho na página girada (exclui carimbo, legenda e moldura) e a rosa dos ventos
CROP = (340, 190, 8010, 6430)
EXCLUDE = [(550, 250, 900, 700)]

# ponytail: calibração. Pontos (px da folha 2 girada, 200 dpi) → (px do mosaico de satélite z17
# com origem no tile x=49837, y=74077). Planta nova ou encaixe torto: ajustar/adicionar pontos aqui.
TILE_ORIGIN = (49837, 74077)
CONTROL = [
    ((1681, 1362), (880, 1036)),   # Comando (prédio com pátio)
    ((424, 1830), (1003, 1135)),   # cabeça do Cais Administrativo
    ((490, 3200), (1145, 1043)),   # cabeça do Cais Operativo
    ((2767, 4924), (1180, 694)),   # heliponto
]
# A folha 1 é o mesmo desenho base deslocado (correlação de fase): p2 = p1 + OFFSET_P1
OFFSET_P1 = (24, -132)

# (folha, espessura do traço) → camada
LAYERS = {(1, 2.09): "incendio", (2, 2.09): "agua", (2, 4.18): "predios", (2, 4.70): "areas"}
AREA_LABELS = {"Área A": (850, 944), "Área B": (1446, 3106), "Área C": (5490, 5046)}

ROTULOS = Path(__file__).with_name("plantas_rotulos.json")

TOKEN = re.compile(r"[MLCZ]|-?[\d.]+")


def fit_affine() -> np.ndarray:
    p = np.array([c[0] for c in CONTROL], float)
    q = np.array([c[1] for c in CONTROL], float)
    a = np.hstack([p, np.ones((len(p), 1))])
    m = np.vstack([np.linalg.lstsq(a, q[:, i], rcond=None)[0] for i in (0, 1)])
    res = np.hypot(*(a @ m.T - q).T) * 1.1  # ~1,1 m/px em z17 nesta latitude
    print(f"resíduo máx {res.max():.1f} m")
    return m


def svg_paths(svg: str):
    """(espessura, [polilinhas em pt da página]) de cada <path> com traço."""
    for attrs in re.findall(r"<path ([^>]*)/>", svg):
        sw = re.search(r'stroke-width="([\d.]+)"', attrs)
        if not sw:
            continue  # preenchidos = glifos do texto
        a, b, c, d, e, f = (float(v) for v in re.search(r'transform="matrix\(([^)]+)\)"', attrs).group(1).split(","))
        items = TOKEN.findall(re.search(r' d="([^"]+)"', attrs).group(1))
        polys, cur, i = [], [], 0
        while i < len(items):
            op = items[i]
            if op == "M":
                if len(cur) > 1:
                    polys.append(cur)
                cur = [(float(items[i + 1]), float(items[i + 2]))]
                i += 3
            elif op == "L":
                cur.append((float(items[i + 1]), float(items[i + 2])))
                i += 3
            elif op == "C":  # Bézier cúbica: amostra 4 pontos
                p0 = np.array(cur[-1])
                p1, p2, p3 = (np.array([float(items[i + k]), float(items[i + k + 1])]) for k in (1, 3, 5))
                for t in (0.25, 0.5, 0.75, 1.0):
                    cur.append(tuple((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t ** 2 * p2 + t ** 3 * p3))
                i += 7
            elif op == "Z":
                if cur:
                    cur.append(cur[0])
                i += 1
            else:
                i += 1
        if len(cur) > 1:
            polys.append(cur)
        yield float(sw.group(1)), [[(a * x + c * y + e, b * x + d * y + f) for x, y in p] for p in polys]


def main(pdf: str) -> None:
    out = Path(__file__).resolve().parent.parent / "frontend" / "assets" / "plantas" / "redes.geojson"
    out.parent.mkdir(parents=True, exist_ok=True)
    m17 = fit_affine()
    n = 2 ** 17 * 256
    k = DPI / 72

    def latlon(x: float, y: float) -> list[float]:
        mx, my = m17 @ np.array([x, y, 1.0])
        gx, gy = mx + TILE_ORIGIN[0] * 256, my + TILE_ORIGIN[1] * 256
        lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * gy / n))))
        return [round(gx / n * 360 - 180, 6), round(lat, 6)]

    def inside(x: float, y: float) -> bool:
        return (CROP[0] <= x <= CROP[2] and CROP[1] <= y <= CROP[3]
                and not any(x0 <= x <= x1 and y0 <= y <= y1 for x0, y0, x1, y1 in EXCLUDE))

    # prédios também viram linha: quase todos vêm do CAD em segmentos soltos, sem anel fechado
    lines: dict[str, list] = {name: [] for name in LAYERS.values()}
    dots, circles, squares = [], [], []   # símbolos, em px da folha 2
    with tempfile.TemporaryDirectory() as tmp:
        for page in (1, 2):
            svg = f"{tmp}/p{page}.svg"
            subprocess.run(["pdftocairo", "-svg", "-f", str(page), "-l", str(page), pdf, svg], check=True)
            dx, dy = OFFSET_P1 if page == 1 else (0, 0)
            for width, polys in svg_paths(Path(svg).read_text()):
                w = round(width, 2)
                layer = LAYERS.get((page, w))
                for poly in polys:
                    # pt da página → px girados 90° (como a referência dos pontos de controle)
                    px = [(y * k + dx, (PAGE_W_PT - x) * k + dy) for x, y in poly]
                    if not all(inside(*p) for p in px):
                        continue
                    xs, ys = [q[0] for q in px], [q[1] for q in px]
                    bw, bh, c = max(xs) - min(xs), max(ys) - min(ys), ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2)
                    if page == 1 and w == 4.18 and bw < 5 and bh < 5:
                        dots.append(c)                      # par de pontinhos do hidrante
                    elif w == 2.09 and len(px) >= 9 and 13 <= bw <= 19 and 13 <= bh <= 19:
                        circles.append((page, c))           # ⊗ do registro
                    elif page == 2 and w == 2.09 and len(px) == 5 and 18 <= bw <= 30 and 18 <= bh <= 30:
                        squares.append(c)                   # caixa do registro ou do "H"
                    if not layer:
                        continue
                    coords = [latlon(*p) for p in px]
                    coords = [c for j, c in enumerate(coords) if j == 0 or c != coords[j - 1]]
                    if len(coords) > 1:  # traço < 10 cm (pontinhos de símbolo) some no arredondamento
                        lines[layer].append(coords)

    feats = [{"type": "Feature", "properties": {"layer": name}, "geometry": {"type": "MultiLineString", "coordinates": c}}
             for name, c in lines.items() if c]

    near = lambda a, b, r: math.hypot(a[0] - b[0], a[1] - b[1]) < r
    point = lambda layer, p, **props: {"type": "Feature", "properties": {"layer": layer, **{k: v for k, v in props.items() if v is not None}},
                                       "geometry": {"type": "Point", "coordinates": latlon(*p)}}
    rotulos = json.loads(ROTULOS.read_text())
    hydrants: list[list] = []
    for d in dots:
        group = next((g for g in hydrants if near(g[0], d, 25)), None)
        group.append(d) if group else hydrants.append([d])
    for g in hydrants:
        c = (sum(x for x, _ in g) / len(g), sum(y for _, y in g) / len(g))
        r = next((r for r in rotulos["hidrantes"] if near((r["x"], r["y"]), c, 40)), {})
        feats.append(point("hidrante", c, id=r.get("id"), obs=r.get("obs")))
    feats += [point("registro", c, rede="incendio" if page == 1 else "agua") for page, c in circles]
    for c in squares:
        if any(page == 2 and near(c, rg, 4) for page, rg in circles):
            continue
        r = next((r for r in rotulos["hidrometros"] if near((r["x"], r["y"]), c, 40)), {})
        feats.append(point("hidrometro", c, predio=r.get("predio"), vazao_m3h=r.get("vazao_m3h")))
    feats += [{"type": "Feature", "properties": {"layer": "rotulo", "label": label}, "geometry": {"type": "Point", "coordinates": latlon(*p)}}
              for label, p in AREA_LABELS.items()]
    out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}, separators=(",", ":")) + "\n")
    pts = {}
    for f in feats:
        if f["geometry"]["type"] == "Point":
            pts[f["properties"]["layer"]] = pts.get(f["properties"]["layer"], 0) + 1
    print({name: len(c) for name, c in lines.items()}, pts, f"{out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
