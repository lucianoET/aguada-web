#!/usr/bin/env python3
"""Gera a página Análise como HTML autocontido (offline, dados embutidos).

Uso: python3 tools/build_dashboard.py [--db data/aguada.db] [--out data/dashboard_aguada_<data>.html]

Mesmo código da página do app (frontend/analise.html): dados de backend.dashboard.build_data,
render de frontend/assets/dashboard.js; aqui CSS, Chart.js e dados vão inline.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from backend.dashboard import build_data  # noqa: E402

ASSETS = ROOT / "frontend" / "assets"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, default=ROOT / "data" / "aguada.db")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / f"dashboard_aguada_{dt.date.today()}.html")
    args = ap.parse_args()

    data = build_data(args.db)
    inline = lambda name: (ASSETS / name).read_text(encoding="utf-8").replace("</", "<\\/") if name.endswith(".js") \
        else (ASSETS / name).read_text(encoding="utf-8")
    html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Aguada — Análise ({data['generated']})</title>
<style>{inline('aguada.css')}
{inline('dashboard.css')}</style>
</head>
<body>
<main class="dash" id="dash"></main>
<script>{inline('vendor/chart.min.js')}</script>
<script>window.DASH_DATA = {json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")};</script>
<script>{inline('dashboard.js')}</script>
</body>
</html>
"""
    args.out.write_text(html, encoding="utf-8")
    pts = sum(len(v) for v in data["hourly"].values())
    print(f"{args.out}  ({len(html) // 1024} KB, {pts} pontos horários, {len(data['daily'])} linhas diárias)")


if __name__ == "__main__":
    main()
