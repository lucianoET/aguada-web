#!/usr/bin/env python3
"""
download_vendors.py — Baixa Alpine.js, Chart.js, Leaflet e tiles OSM para uso offline.
Executar uma vez antes do deploy: python3 scripts/download_vendors.py
"""
import os, urllib.request, math
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VENDOR_DIR = ROOT / "frontend" / "assets" / "vendor"
TILES_DIR  = ROOT / "frontend" / "assets" / "leaflet-tiles"

VENDOR_DIR.mkdir(parents=True, exist_ok=True)
TILES_DIR.mkdir(parents=True, exist_ok=True)

VENDORS = [
    ("alpine.min.js",    "https://cdn.jsdelivr.net/npm/alpinejs@3.14.1/dist/cdn.min.js"),
    ("leaflet.min.js",   "https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"),
    ("leaflet.min.css",  "https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"),
]

def download(url, dest):
    if dest.exists():
        print(f"  [OK] {dest.name} (já existe)")
        return
    print(f"  Baixando {dest.name}...")
    urllib.request.urlretrieve(url, dest)
    print(f"  [OK] {dest.name}")

# Vendors JS/CSS
for name, url in VENDORS:
    download(url, VENDOR_DIR / name)

# Chart.js — copiar do aguada3 se disponível, senão baixar
chart_src = Path("/home/luc/Dev/aguada3/assets/js/chart.min.js")
chart_dst = VENDOR_DIR / "chart.min.js"
if not chart_dst.exists():
    if chart_src.exists():
        import shutil
        shutil.copy(chart_src, chart_dst)
        print(f"  [OK] chart.min.js (copiado do aguada3)")
    else:
        download("https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js", chart_dst)

# Tiles OSM — área da CMASM (zoom 13-17)
# Centro: -22.8390, -43.1080 | bbox aprox: -22.86,-43.12 → -22.82,-43.09
def deg2tile(lat, lng, zoom):
    lat_r = math.radians(lat)
    n = 2 ** zoom
    x = int((lng + 180) / 360 * n)
    y = int((1 - math.log(math.tan(lat_r) + 1/math.cos(lat_r)) / math.pi) / 2 * n)
    return x, y

LAT_MIN, LAT_MAX = -22.86, -22.82
LNG_MIN, LNG_MAX = -43.12, -43.09
ZOOM_MIN, ZOOM_MAX = 13, 17

total = 0
for z in range(ZOOM_MIN, ZOOM_MAX + 1):
    x0, _y0 = deg2tile(LAT_MAX, LNG_MIN, z)
    x1, _y1 = deg2tile(LAT_MIN, LNG_MAX, z)
    y0, y1 = min(_y0, _y1), max(_y0, _y1)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            tile_dir = TILES_DIR / str(z) / str(x)
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_path = tile_dir / f"{y}.png"
            if not tile_path.exists():
                url = f"https://tile.openstreetmap.org/{z}/{x}/{y}.png"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "aguada-web/1.0"})
                    with urllib.request.urlopen(req) as r, open(tile_path, "wb") as f:
                        f.write(r.read())
                    total += 1
                    if total % 20 == 0:
                        print(f"  Tiles baixados: {total}")
                except Exception as e:
                    print(f"  [WARN] {url}: {e}")

print(f"\n[OSM] {total} tiles baixados.")

# Tiles satélite ESRI WorldImagery — mesma área
SAT_DIR = ROOT / "frontend" / "assets" / "leaflet-tiles-sat"
SAT_DIR.mkdir(parents=True, exist_ok=True)

import time
total_sat = 0
for z in range(ZOOM_MIN, ZOOM_MAX + 1):
    x0, _y0 = deg2tile(LAT_MAX, LNG_MIN, z)
    x1, _y1 = deg2tile(LAT_MIN, LNG_MAX, z)
    y0, y1 = min(_y0, _y1), max(_y0, _y1)
    for x in range(x0, x1 + 1):
        for y in range(y0, y1 + 1):
            tile_dir = SAT_DIR / str(z) / str(x)
            tile_dir.mkdir(parents=True, exist_ok=True)
            tile_path = tile_dir / f"{y}.jpg"
            if not tile_path.exists():
                # ESRI URL usa /tile/{z}/{y}/{x} (y antes de x)
                url = f"https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "aguada-web/1.0"})
                    with urllib.request.urlopen(req, timeout=15) as r, open(tile_path, "wb") as f:
                        f.write(r.read())
                    total_sat += 1
                    if total_sat % 20 == 0:
                        print(f"  Satélite: {total_sat} tiles")
                    time.sleep(0.05)
                except Exception as e:
                    print(f"  [WARN] sat {url}: {e}")

print(f"\n[DONE] Vendors, {total} tiles OSM, {total_sat} tiles satélite baixados.")
print(f"  Vendors:   {VENDOR_DIR}")
print(f"  OSM:       {TILES_DIR}")
print(f"  Satélite:  {SAT_DIR}")
