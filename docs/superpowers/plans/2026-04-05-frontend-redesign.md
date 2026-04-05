# Frontend Redesign (Fase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrar o frontend do aguada-web para o estilo visual do aguada3 — sidebar colapsável, CSS offline, Leaflet/OSM, 6 páginas consolidadas — sem tocar no backend FastAPI/SQLite.

**Architecture:** Migração incremental: fundação CSS + vendors primeiro, depois cada página substituída individualmente. Todas as páginas compartilham `aguada.css` e `shared.js` atualizado. Alpine.js, Chart.js e Leaflet servidos localmente de `frontend/assets/vendor/`.

**Tech Stack:** HTML puro, Alpine.js 3.x (offline), Chart.js 4.4.x (offline), Leaflet 1.9.x (offline), CSS customizado (variáveis do aguada3) + Tailwind 3 (utilitários de layout), FastAPI backend inalterado.

**Referências de código:**
- Estilo visual: `/home/luc/Dev/aguada3/assets/css/aguada3.css`
- SCADA SVG: `/home/luc/Dev/aguada2-main/backend/public/scada.php`
- Ícones: `/home/luc/Dev/aguada2-main/backend/public/assets/icons/`
- Chart.js offline: `/home/luc/Dev/aguada3/assets/js/chart.min.js`
- Lógica Alpine atual: `frontend/assets/shared.js`, `frontend/*.html`

---

## Mapa de Arquivos

| Arquivo | Ação | Responsabilidade |
|---------|------|-----------------|
| `frontend/assets/aguada.css` | CRIAR | Sistema de design: variáveis, sidebar, topbar, cards, badges, modal |
| `frontend/assets/shared.js` | ATUALIZAR | Remover CDN, adicionar `toggleTheme()`, `sidebarState`, manter mixins |
| `frontend/assets/vendor/alpine.min.js` | CRIAR | Alpine.js 3.x offline |
| `frontend/assets/vendor/chart.min.js` | CRIAR | Chart.js 4.4.x offline (copiar do aguada3) |
| `frontend/assets/vendor/leaflet.min.js` | CRIAR | Leaflet 1.9.x offline |
| `frontend/assets/vendor/leaflet.min.css` | CRIAR | Leaflet CSS offline |
| `frontend/assets/icons/` | CRIAR | Ícones PNG copiados do aguada2 (pump, valve, hydrometer) |
| `scripts/download_vendors.py` | CRIAR | Download automático de vendors + tiles OSM |
| `frontend/index.html` | REESCREVER | Dashboard: KPI strip + mapa Leaflet + modal lateral |
| `frontend/scada.html` | REESCREVER | SCADA: SVG topologia + painel lateral de equipamentos |
| `frontend/analise.html` | CRIAR | Análise: 4 abas (Histórico, Consumo, Abastecimento, Dados) |
| `frontend/report.html` | MIGRAR | Relatório: mesmo conteúdo, novo layout |
| `frontend/dispositivos.html` | MIGRAR | Dispositivos: mesmo conteúdo, novo layout |
| `frontend/documentacao.html` | MIGRAR | Documentação: accordion expandido com docs xAguada |

---

## Task 1: Script de Download de Vendors

**Files:**
- Create: `scripts/download_vendors.py`

- [ ] **Step 1: Criar o script de download**

```python
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
    x0, y1 = deg2tile(LAT_MAX, LNG_MIN, z)
    x1, y0 = deg2tile(LAT_MIN, LNG_MAX, z)
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

print(f"\n[DONE] Vendors e {total} tiles OSM baixados.")
print(f"  Vendors: {VENDOR_DIR}")
print(f"  Tiles:   {TILES_DIR}")
```

- [ ] **Step 2: Copiar ícones do aguada2**

```bash
mkdir -p frontend/assets/icons
cp /home/luc/Dev/aguada2-main/backend/public/assets/icons/pump.png    frontend/assets/icons/
cp /home/luc/Dev/aguada2-main/backend/public/assets/icons/valve.png   frontend/assets/icons/
cp /home/luc/Dev/aguada2-main/backend/public/assets/icons/hydrometer.png frontend/assets/icons/
```

- [ ] **Step 3: Executar o script**

```bash
cd /home/luc/Dev/aguada-web
python3 scripts/download_vendors.py
```

Esperado: sem erros, `frontend/assets/vendor/` com 4 arquivos, `frontend/assets/leaflet-tiles/` com tiles nos zooms 13-17.

- [ ] **Step 4: Verificar**

```bash
ls frontend/assets/vendor/
# alpine.min.js  chart.min.js  leaflet.min.css  leaflet.min.js

ls frontend/assets/leaflet-tiles/
# 13  14  15  16  17

ls frontend/assets/icons/
# hydrometer.png  pump.png  valve.png
```

- [ ] **Step 5: Commit**

```bash
git add scripts/download_vendors.py frontend/assets/icons/
git commit -m "feat: script download vendors offline + ícones aguada2"
```

---

## Task 2: Sistema de Design — aguada.css

**Files:**
- Create: `frontend/assets/aguada.css`

- [ ] **Step 1: Criar aguada.css com variáveis e layout**

```css
/* ============================================================
   AGUADA — Design System v1.0
   Tema escuro (padrão) inspirado no aguada3.
   Tema claro via [data-theme="light"] no <html>.
   ============================================================ */

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Variáveis — Tema Escuro (padrão) ──────────────────────── */
:root {
  --bg:         #0b0f14;
  --bg2:        #111820;
  --bg3:        #161e28;
  --card:       #192030;
  --border:     #1e2d3d;
  --border2:    #243344;
  --text:       #c9d4e0;
  --text2:      #6b82a0;
  --text3:      #3d556e;
  --blue:       #3b82f6;
  --blue-dim:   #1e3a5f;
  --green:      #22c55e;
  --green-dim:  #14532d;
  --yellow:     #f59e0b;
  --yellow-dim: #78350f;
  --red:        #ef4444;
  --red-dim:    #7f1d1d;
  --cyan:       #06b6d4;
  --mono: 'Courier New', Courier, monospace;
  --sans: system-ui, -apple-system, 'Segoe UI', sans-serif;
  --sidebar-w-collapsed: 42px;
  --sidebar-w-expanded:  220px;
  --topbar-h: 48px;
  --radius: 8px;
}

/* ── Tema Claro ─────────────────────────────────────────────── */
[data-theme="light"] {
  --bg:    #f1f5f9;
  --bg2:   #ffffff;
  --bg3:   #e2e8f0;
  --card:  #ffffff;
  --border: #e2e8f0;
  --border2: #cbd5e1;
  --text:  #1e293b;
  --text2: #64748b;
  --text3: #94a3b8;
}

html, body { height: 100%; font-family: var(--sans); background: var(--bg); color: var(--text); font-size: 14px; line-height: 1.5; }
a { color: inherit; text-decoration: none; }
button { cursor: pointer; font-family: var(--sans); border: none; background: none; }

/* ── Layout Global ──────────────────────────────────────────── */
.layout { display: flex; height: 100vh; overflow: hidden; }

/* ── Sidebar ────────────────────────────────────────────────── */
.sidebar {
  width: var(--sidebar-w-collapsed);
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex; flex-direction: column; flex-shrink: 0;
  overflow: hidden;
  transition: width 0.2s ease;
  position: relative; z-index: 50;
}
.sidebar.expanded,
.sidebar:hover { width: var(--sidebar-w-expanded); }

.sidebar-brand {
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 10px;
  overflow: hidden; white-space: nowrap; flex-shrink: 0;
  min-height: 56px;
}
.sidebar-logo {
  width: 42px; min-width: 42px;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 14px; font-weight: 600; color: var(--cyan);
}
.sidebar-brand-text { font-family: var(--mono); font-size: 13px; color: var(--cyan); letter-spacing: 2px; opacity: 0; transition: opacity 0.15s; }
.sidebar.expanded .sidebar-brand-text,
.sidebar:hover .sidebar-brand-text { opacity: 1; }

.sidebar-nav { padding: 8px 0; flex: 1; overflow-y: auto; }
.sidebar-section {
  font-size: 9px; text-transform: uppercase; letter-spacing: 1.5px;
  color: var(--text3); padding: 10px 0 4px;
  text-align: center; overflow: hidden; white-space: nowrap;
  opacity: 0; transition: opacity 0.15s;
}
.sidebar.expanded .sidebar-section,
.sidebar:hover .sidebar-section { opacity: 1; text-align: left; padding-left: 14px; }

.nav-link {
  display: flex; align-items: center; gap: 10px;
  padding: 8px 0; color: var(--text2); font-size: 13px;
  transition: all 0.15s; overflow: hidden; white-space: nowrap;
}
.nav-link:hover { background: var(--bg3); color: var(--text); }
.nav-link.active { background: var(--blue-dim); color: var(--blue); }
.nav-icon {
  width: 42px; min-width: 42px;
  display: flex; align-items: center; justify-content: center;
  font-size: 15px; flex-shrink: 0;
}
.nav-label { opacity: 0; transition: opacity 0.15s; }
.sidebar.expanded .nav-label,
.sidebar:hover .nav-label { opacity: 1; }

.sidebar-footer {
  padding: 10px 0; border-top: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
  overflow: hidden; white-space: nowrap; flex-shrink: 0;
}
.gw-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; margin-left: 17px; }
.gw-dot.on  { background: var(--green); }
.gw-dot.sim { background: var(--yellow); }
.gw-dot.off { background: var(--red); }
.gw-label { font-family: var(--mono); font-size: 10px; color: var(--text3); opacity: 0; transition: opacity 0.15s; }
.sidebar.expanded .gw-label,
.sidebar:hover .gw-label { opacity: 1; }

/* ── Main / Topbar / Content ────────────────────────────────── */
.main { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-width: 0; }

.topbar {
  height: var(--topbar-h); background: var(--bg2);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
  padding: 0 20px; flex-shrink: 0;
}
.topbar-title { font-size: 15px; font-weight: 500; }
.topbar-sub { font-size: 11px; color: var(--text2); margin-top: 1px; }
.topbar-right { display: flex; align-items: center; gap: 12px; }

.content { flex: 1; overflow-y: auto; padding: 20px; }

/* ── KPI Strip ──────────────────────────────────────────────── */
.kpi-strip { display: flex; gap: 10px; padding: 10px 20px; background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0; flex-wrap: wrap; }
.kpi-item { background: var(--card); border: 1px solid var(--border); border-radius: 6px; padding: 6px 14px; display: flex; align-items: center; gap: 8px; }
.kpi-label { font-size: 10px; color: var(--text3); text-transform: uppercase; letter-spacing: 1px; }
.kpi-value { font-family: var(--mono); font-size: 16px; font-weight: 600; }

/* ── Cards ──────────────────────────────────────────────────── */
.card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); }
.card-header { padding: 12px 16px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: center; }
.card-body { padding: 16px; }
.section-title { font-size: 10px; text-transform: uppercase; letter-spacing: 1.5px; color: var(--text3); margin-bottom: 10px; }

/* ── Badges de Status ISA-101 ───────────────────────────────── */
.badge { font-size: 10px; padding: 2px 8px; border-radius: 10px; font-weight: 600; text-transform: uppercase; white-space: nowrap; display: inline-block; }
.badge-green  { background: var(--green-dim);  color: var(--green); }
.badge-yellow { background: var(--yellow-dim); color: var(--yellow); }
.badge-red    { background: var(--red-dim);    color: var(--red); }
.badge-gray   { background: var(--bg3);        color: var(--text3); }
.badge-blue   { background: var(--blue-dim);   color: var(--blue); }

/* ── SCADA — Equipamentos ───────────────────────────────────── */
.eq-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); padding: 12px 14px; }
.eq-codigo { font-family: var(--mono); font-size: 10px; color: var(--text3); }
.eq-nome { font-size: 13px; font-weight: 500; margin-top: 2px; }
.eq-local { font-size: 11px; color: var(--text3); }
.eq-controls { display: flex; gap: 6px; flex-wrap: wrap; margin: 8px 0; }
.eq-btn { padding: 3px 10px; background: var(--bg3); border: 1px solid var(--border2); color: var(--text2); border-radius: 4px; font-size: 11px; cursor: pointer; }
.eq-btn:hover { background: var(--bg2); color: var(--text); }
.eq-btn.active { background: var(--blue-dim); border-color: var(--blue); color: var(--blue); }

/* ── Hidrômetros ────────────────────────────────────────────── */
.hidro-card { background: var(--card); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
.hidro-head { padding: 10px 14px; border-bottom: 1px solid var(--border); }
.hidro-body { padding: 12px 14px; }
.hidro-valor { font-family: var(--mono); font-size: 20px; }

/* ── Abas ───────────────────────────────────────────────────── */
.tabs { display: flex; gap: 2px; border-bottom: 1px solid var(--border); padding: 0 20px; background: var(--bg2); flex-shrink: 0; }
.tab-btn { padding: 10px 16px; font-size: 12px; color: var(--text2); border-bottom: 2px solid transparent; cursor: pointer; transition: all 0.15s; background: none; border-left: none; border-right: none; border-top: none; }
.tab-btn:hover { color: var(--text); }
.tab-btn.active { color: var(--blue); border-bottom-color: var(--blue); }

/* ── Modal ──────────────────────────────────────────────────── */
.modal-overlay { position: fixed; inset: 0; background: rgba(0,0,0,0.6); z-index: 100; display: flex; align-items: center; justify-content: center; }
.modal-box { background: var(--bg2); border: 1px solid var(--border2); border-radius: 10px; padding: 0; width: 400px; max-width: 95vw; max-height: 90vh; overflow-y: auto; }
.modal-header { padding: 14px 18px; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; align-items: flex-start; }
.modal-body { padding: 16px 18px; }
.modal-footer { padding: 12px 18px; border-top: 1px solid var(--border); display: flex; justify-content: flex-end; gap: 8px; }

/* Modal lateral (Dashboard — deslizante da direita) */
.modal-side {
  position: fixed; top: 0; right: 0; bottom: 0; width: 340px;
  background: var(--bg2); border-left: 1px solid var(--border2);
  z-index: 100; overflow-y: auto;
  transform: translateX(100%); transition: transform 0.25s ease;
}
.modal-side.open { transform: translateX(0); }

/* ── Tank bar (reservatório visual) ─────────────────────────── */
.tank-wrap { position: relative; width: 100%; height: 80px; border: 1px solid var(--border2); border-radius: 4px; overflow: hidden; background: var(--bg3); }
.tank-fill { position: absolute; bottom: 0; left: 0; right: 0; transition: height 0.6s ease; }
.tank-label { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; font-family: var(--mono); font-size: 18px; font-weight: 600; }

/* ── Inputs / Forms ─────────────────────────────────────────── */
.form-input {
  width: 100%; padding: 7px 10px;
  background: var(--bg3); border: 1px solid var(--border2);
  border-radius: 4px; color: var(--text); font-family: var(--sans); font-size: 13px;
}
.form-input:focus { outline: none; border-color: var(--blue); }
.form-select { width: 100%; padding: 6px 10px; background: var(--bg3); border: 1px solid var(--border2); border-radius: 4px; color: var(--text); font-size: 13px; cursor: pointer; }
.btn { padding: 6px 16px; border-radius: 4px; font-size: 12px; font-weight: 500; cursor: pointer; transition: opacity 0.15s; }
.btn-primary { background: var(--blue); color: white; }
.btn-primary:hover { opacity: 0.9; }
.btn-secondary { background: var(--bg3); color: var(--text2); border: 1px solid var(--border2); }
.btn-secondary:hover { color: var(--text); }

/* ── WS Status indicator ────────────────────────────────────── */
.ws-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.ws-dot.connected    { background: var(--green); }
.ws-dot.disconnected { background: var(--red); animation: pulse 1.5s infinite; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* ── Theme toggle button ────────────────────────────────────── */
.theme-btn { width: 32px; height: 32px; border-radius: 6px; display: flex; align-items: center; justify-content: center; color: var(--text2); transition: background 0.15s; }
.theme-btn:hover { background: var(--bg3); color: var(--text); }

/* ── Responsividade ─────────────────────────────────────────── */
@media (max-width: 1024px) {
  .sidebar { position: fixed; top: 0; bottom: 0; left: 0; z-index: 200; transform: translateX(-100%); transition: transform 0.2s ease; width: var(--sidebar-w-expanded) !important; }
  .sidebar.mobile-open { transform: translateX(0); }
  .sidebar:hover { width: var(--sidebar-w-expanded) !important; }
  .main { margin-left: 0 !important; }
}
@media (max-width: 768px) {
  .kpi-strip { gap: 6px; padding: 8px 12px; }
  .content { padding: 12px; }
  .modal-side { width: 100%; }
}

/* ── Leaflet customização tema escuro ───────────────────────── */
.leaflet-container { background: #0d1520; }
.leaflet-tile-pane { filter: grayscale(0.3) brightness(0.85); }
[data-theme="light"] .leaflet-tile-pane { filter: none; }
.leaflet-popup-content-wrapper { background: var(--card); border: 1px solid var(--border2); color: var(--text); border-radius: var(--radius); box-shadow: 0 4px 20px rgba(0,0,0,0.5); }
.leaflet-popup-tip { background: var(--card); }
```

- [ ] **Step 2: Verificar que o arquivo foi criado corretamente**

```bash
wc -l frontend/assets/aguada.css
# Esperado: ~200 linhas
head -5 frontend/assets/aguada.css
# Esperado: /* AGUADA — Design System ...
```

- [ ] **Step 3: Commit**

```bash
git add frontend/assets/aguada.css
git commit -m "feat: aguada.css — sistema de design com tema escuro/claro e sidebar colapsável"
```

---

## Task 3: Atualizar shared.js

**Files:**
- Modify: `frontend/assets/shared.js`

- [ ] **Step 1: Substituir shared.js completo**

```javascript
// shared.js — constantes, helpers e mixins comuns a todas as páginas
// Versão offline: sem referências a CDN

const ORDERED_ALIASES = ['CON', 'CAV', 'CB31', 'CB32', 'CIE1', 'CIE2', 'CBIF1', 'CBIF2'];

// Cor de preenchimento das barras de nível por alias
const ALIAS_FILL_COLORS = {
  CON:   '#059669', CAV:   '#dc2626',
  CB31:  '#7c3aed', CB32:  '#7c3aed',
  CIE1:  '#0891b2', CIE2:  '#0891b2',
  CBIF1: '#2563eb', CBIF2: '#2563eb',
};

// Cor ISA-101 baseada em percentual
function statusColor(pct, online) {
  if (!online) return '#3d556e';
  if (pct <= 20) return '#ef4444';
  if (pct <= 35) return '#f59e0b';
  return '#22c55e';
}

// Cor para marcador Leaflet baseada em percentual e online
function markerColor(pct, online) {
  if (!online) return '#3d556e';
  if (pct <= 20) return '#ef4444';
  if (pct <= 35) return '#f59e0b';
  return '#22c55e';
}

function formatTs(ts) {
  if (!ts) return '—';
  return new Date(ts * 1000).toLocaleString('pt-BR', {
    day: '2-digit', month: '2-digit', year: '2-digit',
    hour: '2-digit', minute: '2-digit'
  });
}

function timeAgo(ts) {
  if (!ts) return '—';
  const then = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  if (Number.isNaN(then.getTime())) return '—';
  const diffSec = Math.floor((Date.now() - then) / 1000);
  if (Number.isNaN(diffSec) || diffSec < 0) return '—';
  if (diffSec < 60) return `${diffSec}s atrás`;
  const diffMin = Math.floor(diffSec / 60);
  if (diffMin < 60) return `${diffMin}min atrás`;
  return `${Math.floor(diffMin / 60)}h atrás`;
}

function rssiColor(rssi) {
  if (rssi == null) return 'var(--text3)';
  if (rssi >= -60) return 'var(--green)';
  if (rssi >= -75) return 'var(--yellow)';
  return 'var(--red)';
}

// ── Tema claro/escuro ──────────────────────────────────────────
function getTheme() {
  return localStorage.getItem('aguada-theme') || 'dark';
}

function applyTheme(theme) {
  if (theme === 'light') {
    document.documentElement.setAttribute('data-theme', 'light');
  } else {
    document.documentElement.removeAttribute('data-theme');
  }
  localStorage.setItem('aguada-theme', theme);
}

function toggleTheme() {
  const current = getTheme();
  applyTheme(current === 'dark' ? 'light' : 'dark');
}

// Aplicar tema imediatamente ao carregar (evita flash)
applyTheme(getTheme());

// ── Sidebar state ──────────────────────────────────────────────
const sidebarState = {
  mobileOpen: false,
  toggle() {
    this.mobileOpen = !this.mobileOpen;
    const sidebar = document.querySelector('.sidebar');
    if (sidebar) sidebar.classList.toggle('mobile-open', this.mobileOpen);
  },
};

// ── WebSocket mixin ────────────────────────────────────────────
function wsMixin() {
  return {
    wsConnected: false,
    lastUpdate: null,
    _ws: null,

    wsConnect(onMessage) {
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const url = `${proto}://${location.host}/ws`;
      this._ws = new WebSocket(url);
      this._ws.onopen  = () => { this.wsConnected = true; };
      this._ws.onclose = () => { this.wsConnected = false; setTimeout(() => this.wsConnect(onMessage), 5000); };
      this._ws.onerror = () => { this._ws.close(); };
      this._ws.onmessage = (e) => {
        try {
          const data = JSON.parse(e.data);
          this.lastUpdate = Date.now() / 1000;
          onMessage(data);
        } catch (_) {}
      };
    },
  };
}

// ── Modal de reservatório (reutilizável) ───────────────────────
function reservoirModalMixin() {
  return {
    modal: {
      open: false, alias: '', name: '', online: false, out_of_range: false,
      pct: 0, volume_l: null, level_cm: null, rssi: null, ts: null,
      volume_max_l: null, level_max_cm: null, lat: null, lng: null,
      manualMode: 'pct', manualValue: '', saving: false,
      feedback: '', feedbackOk: true,
    },

    openModal(alias) {
      const r = this.reservoirs.find(r => r.alias === alias);
      this.modal.alias = alias;
      this.modal.manualMode = 'pct';
      this.modal.manualValue = '';
      this.modal.saving = false;
      this.modal.feedback = '';
      this._fillModal(r || { alias, online: false });
      this.modal.open = true;
    },

    _fillModal(r) {
      this.modal.name         = r.name || r.alias;
      this.modal.online       = r.online ?? false;
      this.modal.out_of_range = r.out_of_range ?? false;
      this.modal.pct          = r.pct != null ? Math.max(0, Math.min(100, r.pct)) : 0;
      this.modal.volume_l     = r.volume_l ?? null;
      this.modal.level_cm     = r.level_cm ?? null;
      this.modal.rssi         = r.rssi ?? null;
      this.modal.ts           = r.ts ?? null;
      this.modal.volume_max_l = r.volume_max_l ?? null;
      this.modal.level_max_cm = r.level_max_cm ?? null;
      this.modal.lat          = r.lat ?? null;
      this.modal.lng          = r.lng ?? null;
    },

    closeModal() { this.modal.open = false; },

    async submitManual() {
      if (!this.modal.manualValue) return;
      this.modal.saving = true;
      this.modal.feedback = '';
      try {
        const val = parseFloat(this.modal.manualValue);
        if (isNaN(val) || val < 0) throw new Error('Valor inválido');
        const body = { alias: this.modal.alias };
        if (this.modal.manualMode === 'pct') body.pct = val;
        else body.volume_l = val;
        const res = await fetch('/api/readings/manual', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const json = await res.json();
        if (!res.ok) throw new Error(json.detail || 'Erro ao salvar');
        const idx = this.reservoirs.findIndex(r => r.alias === this.modal.alias);
        const updated = { ...(this.reservoirs[idx] || {}), alias: json.alias, pct: json.pct, volume_l: json.volume_l, level_cm: json.level_cm, ts: Math.floor(Date.now() / 1000), online: true };
        if (idx >= 0) this.reservoirs[idx] = updated;
        else this.reservoirs.push(updated);
        this.reservoirs = [...this.reservoirs];
        this._fillModal(updated);
        this.modal.feedback = `Salvo: ${json.pct}% · ${Math.round(json.volume_l)} L`;
        this.modal.feedbackOk = true;
        this.modal.manualValue = '';
      } catch (e) {
        this.modal.feedback = e.message || 'Erro ao salvar';
        this.modal.feedbackOk = false;
      } finally {
        this.modal.saving = false;
      }
    },

    formatTs, timeAgo, rssiColor, statusColor, markerColor,
  };
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/assets/shared.js
git commit -m "feat: shared.js — offline, toggleTheme, wsMixin, sidebarState, markerColor"
```

---

## Task 4: Dashboard (`index.html`)

**Files:**
- Modify: `frontend/index.html`

O Dashboard tem: sidebar + topbar + KPI strip + mapa Leaflet (tela cheia restante) + modal lateral de reservatório.

- [ ] **Step 1: Reescrever index.html**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Aguada — Dashboard</title>
  <link rel="stylesheet" href="assets/aguada.css" />
  <link rel="stylesheet" href="assets/vendor/leaflet.min.css" />
  <style>
    [x-cloak] { display: none; }
    #map { width: 100%; height: 100%; }
    .map-wrap { flex: 1; position: relative; overflow: hidden; }
  </style>
</head>
<body>
<div class="layout" x-data="dashboardApp()" x-init="init()" x-cloak>

  <!-- Sidebar -->
  <aside class="sidebar" id="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-logo">A</div>
      <span class="sidebar-brand-text">AGUADA</span>
    </div>
    <nav class="sidebar-nav">
      <div class="sidebar-section">Operação</div>
      <a href="index.html" class="nav-link active">
        <span class="nav-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>
        </span>
        <span class="nav-label">Dashboard</span>
      </a>
      <a href="scada.html" class="nav-link">
        <span class="nav-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg>
        </span>
        <span class="nav-label">SCADA</span>
      </a>
      <div class="sidebar-section">Análise</div>
      <a href="analise.html" class="nav-link">
        <span class="nav-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>
        </span>
        <span class="nav-label">Análise</span>
      </a>
      <div class="sidebar-section">Gestão</div>
      <a href="report.html" class="nav-link">
        <span class="nav-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
        </span>
        <span class="nav-label">Relatório</span>
      </a>
      <a href="dispositivos.html" class="nav-link">
        <span class="nav-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/></svg>
        </span>
        <span class="nav-label">Dispositivos</span>
      </a>
      <a href="documentacao.html" class="nav-link">
        <span class="nav-icon">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>
        </span>
        <span class="nav-label">Documentação</span>
      </a>
    </nav>
    <div class="sidebar-footer">
      <span class="gw-dot" :class="gwStatus"></span>
      <span class="gw-label" x-text="gwLabel"></span>
    </div>
  </aside>

  <!-- Main -->
  <div class="main">
    <!-- Topbar -->
    <div class="topbar">
      <div>
        <button class="theme-btn" onclick="document.querySelector('#sidebar').classList.toggle('mobile-open')" style="display:none" id="sidebar-toggle">☰</button>
        <div class="topbar-title">Dashboard</div>
        <div class="topbar-sub">Monitoramento em tempo real</div>
      </div>
      <div class="topbar-right">
        <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text3)">
          <span class="ws-dot" :class="wsConnected ? 'connected' : 'disconnected'"></span>
          <span x-text="wsConnected ? 'Ao vivo' : 'Desconectado'"></span>
          <span x-show="lastUpdate" x-text="'· ' + timeAgo(lastUpdate)" style="color:var(--text3)"></span>
        </div>
        <button class="theme-btn" onclick="toggleTheme()" title="Alternar tema">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/></svg>
        </button>
      </div>
    </div>

    <!-- KPI Strip -->
    <div class="kpi-strip">
      <div class="kpi-item">
        <div>
          <div class="kpi-label">Reservatórios</div>
          <div class="kpi-value" x-text="reservoirs.length"></div>
        </div>
      </div>
      <div class="kpi-item">
        <div>
          <div class="kpi-label">Volume médio</div>
          <div class="kpi-value" style="color:var(--blue)" x-text="avgPct + '%'"></div>
        </div>
      </div>
      <div class="kpi-item">
        <div>
          <div class="kpi-label">Críticos</div>
          <div class="kpi-value" :style="critical > 0 ? 'color:var(--red)' : 'color:var(--green)'" x-text="critical"></div>
        </div>
      </div>
      <div class="kpi-item">
        <div>
          <div class="kpi-label">Online</div>
          <div class="kpi-value" x-text="onlineCount + '/' + reservoirs.length"></div>
        </div>
      </div>
    </div>

    <!-- Mapa -->
    <div class="map-wrap">
      <div id="map"></div>
    </div>
  </div>

  <!-- Modal lateral -->
  <div class="modal-side" :class="{ open: modal.open }" id="modal-side">
    <div class="modal-header">
      <div>
        <div style="display:flex;align-items:center;gap:8px">
          <span style="font-family:var(--mono);font-size:16px;font-weight:600" x-text="modal.alias"></span>
          <span class="badge" :class="modal.online ? 'badge-green' : 'badge-gray'" x-text="modal.online ? 'Online' : 'Offline'"></span>
        </div>
        <div style="font-size:11px;color:var(--text2);margin-top:2px" x-text="modal.name"></div>
      </div>
      <button class="theme-btn" @click="closeModal()">
        <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
      </button>
    </div>
    <div class="modal-body">
      <!-- Barra de nível -->
      <div class="tank-wrap" style="height:90px;margin-bottom:12px">
        <div class="tank-fill" :style="`height:${modal.pct}%;background:${statusColor(modal.pct, modal.online)}`"></div>
        <div class="tank-label" :style="modal.pct > 40 ? 'color:white' : 'color:var(--text)'" x-text="modal.pct + '%'"></div>
      </div>
      <!-- Métricas -->
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:16px">
        <div class="card" style="padding:10px">
          <div style="font-size:10px;color:var(--text3)">Volume</div>
          <div style="font-family:var(--mono);font-size:15px;margin-top:2px" x-text="modal.volume_l != null ? Math.round(modal.volume_l / 1000) + ' m³' : '—'"></div>
        </div>
        <div class="card" style="padding:10px">
          <div style="font-size:10px;color:var(--text3)">Nível</div>
          <div style="font-family:var(--mono);font-size:15px;margin-top:2px" x-text="modal.level_cm != null ? modal.level_cm + ' cm' : '—'"></div>
        </div>
        <div class="card" style="padding:10px">
          <div style="font-size:10px;color:var(--text3)">RSSI</div>
          <div style="font-family:var(--mono);font-size:15px;margin-top:2px" :style="`color:${rssiColor(modal.rssi)}`" x-text="modal.rssi != null ? modal.rssi + ' dBm' : '—'"></div>
        </div>
        <div class="card" style="padding:10px">
          <div style="font-size:10px;color:var(--text3)">Atualizado</div>
          <div style="font-size:11px;margin-top:2px;color:var(--text2)" x-text="timeAgo(modal.ts)"></div>
        </div>
      </div>
      <!-- Leitura manual -->
      <div class="section-title">Leitura Manual</div>
      <div style="display:flex;gap:6px;margin-bottom:8px">
        <button class="eq-btn" :class="{active: modal.manualMode==='pct'}" @click="modal.manualMode='pct'">%</button>
        <button class="eq-btn" :class="{active: modal.manualMode==='volume_l'}" @click="modal.manualMode='volume_l'">Litros</button>
      </div>
      <div style="display:flex;gap:8px">
        <input class="form-input" type="number" min="0" :max="modal.manualMode==='pct'?100:modal.volume_max_l" :placeholder="modal.manualMode==='pct'?'0–100 %':'Litros'" x-model="modal.manualValue" @keyup.enter="submitManual()" />
        <button class="btn btn-primary" @click="submitManual()" :disabled="modal.saving" x-text="modal.saving ? '...' : 'Salvar'"></button>
      </div>
      <div x-show="modal.feedback" x-text="modal.feedback" style="font-size:11px;margin-top:6px" :style="modal.feedbackOk ? 'color:var(--green)' : 'color:var(--red)'"></div>
    </div>
  </div>
  <!-- Overlay modal-side -->
  <div x-show="modal.open" @click="closeModal()" style="position:fixed;inset:0;z-index:99;background:rgba(0,0,0,0.4)" x-cloak></div>

</div>

<script src="assets/shared.js"></script>
<script src="assets/vendor/leaflet.min.js"></script>
<script defer src="assets/vendor/alpine.min.js"></script>
<script>
function dashboardApp() {
  return {
    reservoirs: [],
    gwStatus: 'off',
    gwLabel: 'GW offline',
    _map: null,
    _markers: {},

    get avgPct() {
      if (!this.reservoirs.length) return 0;
      const online = this.reservoirs.filter(r => r.online);
      if (!online.length) return 0;
      return Math.round(online.reduce((s, r) => s + (r.pct || 0), 0) / online.length);
    },
    get critical() { return this.reservoirs.filter(r => r.online && r.pct <= 20).length; },
    get onlineCount() { return this.reservoirs.filter(r => r.online).length; },

    ...wsMixin(),
    ...reservoirModalMixin(),

    async init() {
      // Buscar estado inicial
      const res = await fetch('/api/reservoirs');
      this.reservoirs = await res.json();
      // Gateway
      const gw = await fetch('/api/gateway').then(r => r.json()).catch(() => null);
      this._updateGw(gw);
      // Inicializar mapa
      this._initMap();
      // WebSocket ao vivo
      this.wsConnect((data) => {
        if (data.type === 'snapshot') {
          this.reservoirs = data.reservoirs;
          this._updateGw(data.gateway);
        } else if (data.type === 'reading') {
          const idx = this.reservoirs.findIndex(r => r.alias === data.alias);
          if (idx >= 0) this.reservoirs[idx] = { ...this.reservoirs[idx], ...data };
          else this.reservoirs.push(data);
          this.reservoirs = [...this.reservoirs];
        }
        this._updateMarkers();
        if (this.modal.open) {
          const r = this.reservoirs.find(r => r.alias === this.modal.alias);
          if (r) this._fillModal(r);
        }
      });
    },

    _updateGw(gw) {
      if (!gw) return;
      if (gw.sim_mode) { this.gwStatus = 'sim'; this.gwLabel = 'Simulação'; }
      else if (gw.connected) { this.gwStatus = 'on'; this.gwLabel = 'GW online'; }
      else { this.gwStatus = 'off'; this.gwLabel = 'GW offline'; }
    },

    _initMap() {
      const tileUrl = 'assets/leaflet-tiles/{z}/{x}/{y}.png';
      const tileUrlFallback = 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
      this._map = L.map('map').setView([-22.8390, -43.1080], 16);

      // Tentar tiles locais, fallback para OSM online
      const localLayer = L.tileLayer(tileUrl, { maxZoom: 19, attribution: '© OpenStreetMap' });
      localLayer.on('tileerror', () => {
        this._map.removeLayer(localLayer);
        L.tileLayer(tileUrlFallback, { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(this._map);
      });
      localLayer.addTo(this._map);

      this._updateMarkers();
    },

    _updateMarkers() {
      this.reservoirs.forEach(r => {
        if (!r.lat || !r.lng) return;
        const color = markerColor(r.pct, r.online);
        const pct = r.pct != null ? Math.round(r.pct) : '?';
        const icon = L.divIcon({
          className: '',
          html: `<div style="background:${color};border:2px solid rgba(0,0,0,0.4);border-radius:50%;width:36px;height:36px;display:flex;flex-direction:column;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 0 8px ${color}44">
                   <div style="font-size:8px;font-weight:700;color:white;line-height:1">${r.alias}</div>
                   <div style="font-size:9px;font-weight:700;color:white;line-height:1">${pct}%</div>
                 </div>`,
          iconSize: [36, 36],
          iconAnchor: [18, 18],
        });
        if (this._markers[r.alias]) {
          this._markers[r.alias].setIcon(icon);
        } else {
          const m = L.marker([r.lat, r.lng], { icon }).addTo(this._map);
          m.on('click', () => this.openModal(r.alias));
          this._markers[r.alias] = m;
        }
      });
    },
  };
}
</script>
</body>
</html>
```

- [ ] **Step 2: Verificar no browser que a página carrega**

```bash
# Com o backend rodando:
./tools/start_backend.sh
# Abrir http://localhost:8001
```

Esperado: sidebar com ícones, mapa centrado na CMASM, marcadores coloridos com alias e %.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: dashboard reescrito com Leaflet, sidebar colapsável, modal lateral"
```

---

## Task 5: SCADA (`scada.html`)

**Files:**
- Modify: `frontend/scada.html`

Reescrever baseado no SVG do `aguada2/scada.php`, adaptado para o backend aguada-web (WebSocket) e com painel lateral de controle.

- [ ] **Step 1: Reescrever scada.html**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Aguada — SCADA</title>
  <link rel="stylesheet" href="assets/aguada.css" />
  <style>
    [x-cloak] { display: none; }
    .scada-wrap { flex: 1; display: flex; overflow: hidden; }
    .scada-canvas { flex: 1; display: flex; align-items: center; justify-content: center; background: radial-gradient(circle at center, #1a2535 0%, #0b0f14 100%); overflow: hidden; padding: 16px; }
    .scada-svg { width: 100%; height: 100%; max-width: 1800px; max-height: 900px; }
    .scada-panel { width: 260px; flex-shrink: 0; background: var(--bg2); border-left: 1px solid var(--border); overflow-y: auto; display: flex; flex-direction: column; }
    .scada-panel-section { padding: 10px 12px; border-bottom: 1px solid var(--border); }
    .tank-group { cursor: pointer; transition: filter 0.2s; }
    .tank-group:hover { filter: brightness(1.15); }
    @keyframes flow { to { stroke-dashoffset: -20; } }
    @keyframes flow-slow { to { stroke-dashoffset: -30; } }
    .pipe-flow { stroke-dasharray: 10 5; animation: flow 1.2s linear infinite; }
    .pipe-flow-slow { stroke-dasharray: 12 6; animation: flow-slow 2.5s linear infinite; }
  </style>
</head>
<body>
<div class="layout" x-data="scadaApp()" x-init="init()" x-cloak>

  <!-- Sidebar (idêntica ao Dashboard) -->
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-logo">A</div>
      <span class="sidebar-brand-text">AGUADA</span>
    </div>
    <nav class="sidebar-nav">
      <div class="sidebar-section">Operação</div>
      <a href="index.html" class="nav-link">
        <span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg></span>
        <span class="nav-label">Dashboard</span>
      </a>
      <a href="scada.html" class="nav-link active">
        <span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg></span>
        <span class="nav-label">SCADA</span>
      </a>
      <div class="sidebar-section">Análise</div>
      <a href="analise.html" class="nav-link">
        <span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span>
        <span class="nav-label">Análise</span>
      </a>
      <div class="sidebar-section">Gestão</div>
      <a href="report.html" class="nav-link">
        <span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span>
        <span class="nav-label">Relatório</span>
      </a>
      <a href="dispositivos.html" class="nav-link">
        <span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/></svg></span>
        <span class="nav-label">Dispositivos</span>
      </a>
      <a href="documentacao.html" class="nav-link">
        <span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg></span>
        <span class="nav-label">Documentação</span>
      </a>
    </nav>
    <div class="sidebar-footer">
      <span class="gw-dot" :class="gwStatus"></span>
      <span class="gw-label" x-text="gwLabel"></span>
    </div>
  </aside>

  <div class="main">
    <div class="topbar">
      <div>
        <div class="topbar-title">SCADA — Diagrama Unifilar</div>
        <div class="topbar-sub" x-text="'Volume total: ' + totalVol + ' · Nodes: ' + onlineCount + '/8'"></div>
      </div>
      <div class="topbar-right">
        <div style="display:flex;align-items:center;gap:6px;font-size:11px;color:var(--text3)">
          <span class="ws-dot" :class="wsConnected ? 'connected' : 'disconnected'"></span>
          <span x-text="wsConnected ? 'Ao vivo' : 'Desconectado'"></span>
        </div>
        <button class="theme-btn" onclick="toggleTheme()">
          <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg>
        </button>
      </div>
    </div>

    <div class="scada-wrap">
      <!-- Diagrama SVG -->
      <div class="scada-canvas">
        <svg class="scada-svg" viewBox="0 0 1800 900" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="xMidYMid meet">
          <defs>
            <linearGradient id="water-blue" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" style="stop-color:#3b82f6;stop-opacity:0.85"/>
              <stop offset="100%" style="stop-color:#1e40af;stop-opacity:0.95"/>
            </linearGradient>
            <linearGradient id="water-red" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" style="stop-color:#ef4444;stop-opacity:0.85"/>
              <stop offset="100%" style="stop-color:#7f1d1d;stop-opacity:0.95"/>
            </linearGradient>
            <marker id="arrow" markerWidth="8" markerHeight="6" refX="8" refY="3" orient="auto">
              <polygon points="0 0, 8 3, 0 6" fill="#3b82f6" opacity="0.7"/>
            </marker>
          </defs>

          <!-- ILHA DAS FLORES -->
          <rect x="30" y="30" width="320" height="840" fill="rgba(245,158,11,0.05)" stroke="#f59e0b" stroke-width="1.5" stroke-dasharray="8,4" rx="12"/>
          <text x="190" y="60" font-size="16" fill="#f59e0b" text-anchor="middle" font-weight="700" font-family="monospace">ILHA DAS FLORES</text>

          <!-- CBIF1 -->
          <g class="tank-group" @click="openModal('CBIF1')">
            <rect x="90" y="90" width="120" height="120" fill="#0b0f14" stroke="#3b82f6" stroke-width="2" rx="6"/>
            <rect x="95" y="95" width="110"
              :height="(getR('CBIF1').pct/100)*110"
              :y="95+(110-(getR('CBIF1').pct/100)*110)"
              :fill="getR('CBIF1').online ? 'url(#water-blue)' : '#3d556e'" rx="3"/>
            <text x="150" y="155" font-size="22" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CBIF1').pct+'%'"/>
            <text x="150" y="230" font-size="13" fill="#6b82a0" text-anchor="middle">CBIF1</text>
          </g>

          <!-- CBIF2 -->
          <g class="tank-group" @click="openModal('CBIF2')">
            <rect x="240" y="90" width="120" height="120" fill="#0b0f14" stroke="#3b82f6" stroke-width="2" rx="6"/>
            <rect x="245" y="95" width="110"
              :height="(getR('CBIF2').pct/100)*110"
              :y="95+(110-(getR('CBIF2').pct/100)*110)"
              :fill="getR('CBIF2').online ? 'url(#water-blue)' : '#3d556e'" rx="3"/>
            <text x="300" y="155" font-size="22" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CBIF2').pct+'%'"/>
            <text x="300" y="230" font-size="13" fill="#6b82a0" text-anchor="middle">CBIF2</text>
          </g>

          <!-- Bombas IF -->
          <circle cx="140" cy="620" r="32" fill="#1e2d3d" stroke="#f59e0b" stroke-width="2"/>
          <text x="140" y="627" font-size="18" fill="#f59e0b" text-anchor="middle">⚙</text>
          <text x="140" y="670" font-size="11" fill="#c9d4e0" text-anchor="middle">BIF-ELE</text>
          <circle cx="240" cy="620" r="32" fill="#1e2d3d" stroke="#f59e0b" stroke-width="2"/>
          <text x="240" y="627" font-size="18" fill="#f59e0b" text-anchor="middle">⚙</text>
          <text x="240" y="670" font-size="11" fill="#c9d4e0" text-anchor="middle">BIF-DIE</text>

          <!-- Hidrômetro IF -->
          <circle cx="190" cy="760" r="24" fill="#1e2d3d" stroke="#06b6d4" stroke-width="2"/>
          <text x="190" y="767" font-size="14" fill="#06b6d4" text-anchor="middle" font-weight="700">H</text>
          <text x="190" y="800" font-size="11" fill="#6b82a0" text-anchor="middle">HID-IF</text>

          <!-- Linha submarina -->
          <path d="M 350 650 Q 550 700 730 650" stroke="#3b82f6" stroke-width="6" fill="none" stroke-dasharray="14,8" marker-end="url(#arrow)" class="pipe-flow-slow"/>
          <text x="540" y="720" font-size="14" fill="#3b82f6" text-anchor="middle">— submarina —</text>

          <!-- ILHA DO ENGENHO -->
          <rect x="720" y="30" width="1060" height="840" fill="rgba(16,185,129,0.04)" stroke="#10b981" stroke-width="1.5" stroke-dasharray="8,4" rx="12"/>
          <text x="1250" y="60" font-size="16" fill="#10b981" text-anchor="middle" font-weight="700" font-family="monospace">ILHA DO ENGENHO</text>

          <!-- CIE1 -->
          <g class="tank-group" @click="openModal('CIE1')">
            <rect x="780" y="90" width="140" height="140" fill="#0b0f14" stroke="#ef4444" stroke-width="2" rx="6"/>
            <rect x="785" y="95" width="130"
              :height="(getR('CIE1').pct/100)*130"
              :y="95+(130-(getR('CIE1').pct/100)*130)"
              :fill="getR('CIE1').online ? 'url(#water-red)' : '#3d556e'" rx="3"/>
            <text x="850" y="165" font-size="26" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CIE1').pct+'%'"/>
            <text x="850" y="255" font-size="13" fill="#ef4444" text-anchor="middle">CIE1 (Incêndio)</text>
          </g>

          <!-- CIE2 -->
          <g class="tank-group" @click="openModal('CIE2')">
            <rect x="960" y="90" width="140" height="140" fill="#0b0f14" stroke="#ef4444" stroke-width="2" rx="6"/>
            <rect x="965" y="95" width="130"
              :height="(getR('CIE2').pct/100)*130"
              :y="95+(130-(getR('CIE2').pct/100)*130)"
              :fill="getR('CIE2').online ? 'url(#water-red)' : '#3d556e'" rx="3"/>
            <text x="1030" y="165" font-size="26" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CIE2').pct+'%'"/>
            <text x="1030" y="255" font-size="13" fill="#ef4444" text-anchor="middle">CIE2 (Incêndio)</text>
          </g>

          <!-- CB31 e CB32 -->
          <g class="tank-group" @click="openModal('CB31')">
            <rect x="780" y="420" width="140" height="140" fill="#0b0f14" stroke="#7c3aed" stroke-width="2" rx="6"/>
            <rect x="785" y="425" width="130"
              :height="(getR('CB31').pct/100)*130"
              :y="425+(130-(getR('CB31').pct/100)*130)"
              fill="url(#water-blue)" rx="3"/>
            <text x="850" y="495" font-size="26" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CB31').pct+'%'"/>
            <text x="850" y="585" font-size="13" fill="#a78bfa" text-anchor="middle">CB31</text>
          </g>
          <g class="tank-group" @click="openModal('CB32')">
            <rect x="960" y="420" width="140" height="140" fill="#0b0f14" stroke="#7c3aed" stroke-width="2" rx="6"/>
            <rect x="965" y="425" width="130"
              :height="(getR('CB32').pct/100)*130"
              :y="425+(130-(getR('CB32').pct/100)*130)"
              fill="url(#water-blue)" rx="3"/>
            <text x="1030" y="495" font-size="26" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CB32').pct+'%'"/>
            <text x="1030" y="585" font-size="13" fill="#a78bfa" text-anchor="middle">CB32</text>
          </g>

          <!-- Bombas Engenho -->
          <circle cx="1200" cy="630" r="32" fill="#1e2d3d" stroke="#f59e0b" stroke-width="2"/>
          <text x="1200" y="637" font-size="18" fill="#f59e0b" text-anchor="middle">⚙</text>
          <text x="1200" y="678" font-size="11" fill="#c9d4e0" text-anchor="middle">B03-ELE</text>
          <circle cx="1310" cy="630" r="32" fill="#1e2d3d" stroke="#f59e0b" stroke-width="2"/>
          <text x="1310" y="637" font-size="18" fill="#f59e0b" text-anchor="middle">⚙</text>
          <text x="1310" y="678" font-size="11" fill="#c9d4e0" text-anchor="middle">B03-DIE</text>

          <!-- CON (Castelo Consumo) — forma trapezoidal -->
          <g class="tank-group" @click="openModal('CON')">
            <path d="M1430 300 L1470 100 L1630 100 L1670 300 Z" fill="#0b0f14" stroke="#22c55e" stroke-width="3"/>
            <clipPath id="clipCON"><path d="M1430 300 L1470 100 L1630 100 L1670 300 Z"/></clipPath>
            <rect x="1430" y="100" width="240" height="200" clip-path="url(#clipCON)"
              :height="(getR('CON').pct/100)*200"
              :y="100+(200-(getR('CON').pct/100)*200)"
              :fill="getR('CON').online ? '#22c55e' : '#3d556e'" opacity="0.7"/>
            <text x="1550" y="210" font-size="28" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CON').pct+'%'"/>
            <text x="1550" y="340" font-size="15" fill="#22c55e" text-anchor="middle" font-weight="700">CON</text>
            <text x="1550" y="358" font-size="11" fill="#6b82a0" text-anchor="middle">Consumo</text>
          </g>

          <!-- CAV (Castelo Incêndio) -->
          <g class="tank-group" @click="openModal('CAV')">
            <path d="M1570 700 L1610 500 L1770 500 L1810 700 Z" fill="#0b0f14" stroke="#ef4444" stroke-width="3"/>
            <clipPath id="clipCAV"><path d="M1570 700 L1610 500 L1770 500 L1810 700 Z"/></clipPath>
            <rect x="1570" y="500" width="240" height="200" clip-path="url(#clipCAV)"
              :height="(getR('CAV').pct/100)*200"
              :y="500+(200-(getR('CAV').pct/100)*200)"
              :fill="getR('CAV').online ? '#ef4444' : '#3d556e'" opacity="0.7"/>
            <text x="1690" y="610" font-size="28" fill="white" text-anchor="middle" font-weight="700" x-text="getR('CAV').pct+'%'"/>
            <text x="1690" y="740" font-size="15" fill="#ef4444" text-anchor="middle" font-weight="700">CAV</text>
            <text x="1690" y="758" font-size="11" fill="#6b82a0" text-anchor="middle">Incêndio</text>
          </g>

          <!-- Pipes principais -->
          <line x1="850" y1="560" x2="850" y2="620" stroke="#6b82a0" stroke-width="3" stroke-dasharray="6,3" class="pipe-flow"/>
          <line x1="1030" y1="560" x2="1030" y2="620" stroke="#6b82a0" stroke-width="3" stroke-dasharray="6,3" class="pipe-flow"/>
          <line x1="850" y1="620" x2="1200" y2="630" stroke="#3b82f6" stroke-width="4" stroke-dasharray="8,4" class="pipe-flow"/>
          <line x1="1200" y1="598" x2="1550" y2="300" stroke="#22c55e" stroke-width="4" stroke-dasharray="8,4" class="pipe-flow"/>
          <line x1="1310" y1="598" x2="1690" y2="500" stroke="#ef4444" stroke-width="4" stroke-dasharray="8,4" class="pipe-flow"/>

          <!-- Hidrômetro Praia -->
          <circle cx="1420" cy="800" r="24" fill="#1e2d3d" stroke="#06b6d4" stroke-width="2"/>
          <text x="1420" y="807" font-size="14" fill="#06b6d4" text-anchor="middle" font-weight="700">H</text>
          <text x="1420" y="840" font-size="11" fill="#6b82a0" text-anchor="middle">HID-PRAIA</text>
        </svg>
      </div>

      <!-- Painel lateral de controle -->
      <div class="scada-panel">
        <div class="scada-panel-section">
          <div class="section-title">Bombas</div>
          <template x-for="b in pumps" :key="b.id">
            <div class="eq-card" style="margin-bottom:8px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                  <div class="eq-codigo" x-text="b.name || b.id"></div>
                  <div class="eq-nome" x-text="b.location || '—'"></div>
                </div>
                <span class="badge" :class="b.status==='ligada'?'badge-green':b.status==='manutencao'?'badge-yellow':'badge-gray'" x-text="b.status || 'deslig.'"></span>
              </div>
              <div class="eq-controls">
                <button class="eq-btn" :class="{active:b.status==='ligada'}" @click="setEquip('pump',b.id,'ligada')">Ligar</button>
                <button class="eq-btn" :class="{active:b.status==='desligada'}" @click="setEquip('pump',b.id,'desligada')">Desligar</button>
                <button class="eq-btn" :class="{active:b.status==='manutencao'}" @click="setEquip('pump',b.id,'manutencao')">Manut.</button>
              </div>
            </div>
          </template>
        </div>
        <div class="scada-panel-section">
          <div class="section-title">Válvulas</div>
          <template x-for="v in valves" :key="v.id">
            <div class="eq-card" style="margin-bottom:8px">
              <div style="display:flex;justify-content:space-between;align-items:flex-start">
                <div>
                  <div class="eq-codigo" x-text="v.name || v.id"></div>
                </div>
                <span class="badge" :class="v.status==='aberta'?'badge-green':v.status==='parcial'?'badge-yellow':'badge-gray'" x-text="v.status || 'fechada'"></span>
              </div>
              <div class="eq-controls">
                <button class="eq-btn" :class="{active:v.status==='aberta'}" @click="setEquip('valve',v.id,'aberta')">Abrir</button>
                <button class="eq-btn" :class="{active:v.status==='parcial'}" @click="setEquip('valve',v.id,'parcial')">Parcial</button>
                <button class="eq-btn" :class="{active:v.status==='fechada'}" @click="setEquip('valve',v.id,'fechada')">Fechar</button>
              </div>
            </div>
          </template>
        </div>
        <div class="scada-panel-section" style="flex:1">
          <div class="section-title">Hidrômetros</div>
          <template x-for="h in hydrometers" :key="h.meter_name">
            <div class="hidro-card" style="margin-bottom:8px">
              <div class="hidro-head">
                <div class="eq-codigo" x-text="h.meter_name"></div>
              </div>
              <div class="hidro-body" style="display:flex;justify-content:space-between;align-items:center">
                <div class="hidro-valor" x-text="h.reading_m3 != null ? h.reading_m3 + ' m³' : '—'"></div>
                <div style="font-size:10px;color:var(--text3)" x-text="formatTs(h.ts)"></div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>

  <!-- Modal de reservatório (reutiliza reservoirModalMixin) -->
  <div class="modal-overlay" x-show="modal.open" @click.self="closeModal()" x-cloak>
    <div class="modal-box" @click.stop>
      <div class="modal-header">
        <div>
          <div style="display:flex;align-items:center;gap:8px">
            <span style="font-family:var(--mono);font-size:16px;font-weight:600" x-text="modal.alias"></span>
            <span class="badge" :class="modal.online?'badge-green':'badge-gray'" x-text="modal.online?'Online':'Offline'"></span>
          </div>
          <div style="font-size:11px;color:var(--text2)" x-text="modal.name"></div>
        </div>
        <button class="theme-btn" @click="closeModal()">✕</button>
      </div>
      <div class="modal-body">
        <div class="tank-wrap" style="height:70px;margin-bottom:12px">
          <div class="tank-fill" :style="`height:${modal.pct}%;background:${statusColor(modal.pct,modal.online)}`"></div>
          <div class="tank-label" x-text="modal.pct+'%'"></div>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-bottom:14px">
          <div class="card" style="padding:8px"><div style="font-size:10px;color:var(--text3)">Volume</div><div style="font-family:var(--mono);font-size:14px" x-text="modal.volume_l!=null?Math.round(modal.volume_l/1000)+' m³':'—'"></div></div>
          <div class="card" style="padding:8px"><div style="font-size:10px;color:var(--text3)">Nível</div><div style="font-family:var(--mono);font-size:14px" x-text="modal.level_cm!=null?modal.level_cm+' cm':'—'"></div></div>
        </div>
        <div class="section-title">Leitura Manual</div>
        <div style="display:flex;gap:6px;margin-bottom:8px">
          <button class="eq-btn" :class="{active:modal.manualMode==='pct'}" @click="modal.manualMode='pct'">%</button>
          <button class="eq-btn" :class="{active:modal.manualMode==='volume_l'}" @click="modal.manualMode='volume_l'">Litros</button>
        </div>
        <div style="display:flex;gap:8px">
          <input class="form-input" type="number" min="0" :placeholder="modal.manualMode==='pct'?'0–100 %':'Litros'" x-model="modal.manualValue" @keyup.enter="submitManual()"/>
          <button class="btn btn-primary" @click="submitManual()" x-text="modal.saving?'...':'Salvar'"></button>
        </div>
        <div x-show="modal.feedback" x-text="modal.feedback" style="font-size:11px;margin-top:6px" :style="modal.feedbackOk?'color:var(--green)':'color:var(--red)'"></div>
      </div>
    </div>
  </div>

</div>

<script src="assets/shared.js"></script>
<script defer src="assets/vendor/alpine.min.js"></script>
<script>
function scadaApp() {
  return {
    reservoirs: [],
    pumps: [],
    valves: [],
    hydrometers: [],
    gwStatus: 'off',
    gwLabel: 'GW offline',

    get totalVol() {
      const tot = this.reservoirs.filter(r=>r.online).reduce((s,r)=>s+(r.volume_l||0),0);
      return tot >= 1000 ? Math.round(tot/1000)+' m³' : Math.round(tot)+' L';
    },
    get onlineCount() { return this.reservoirs.filter(r=>r.online).length; },

    getR(alias) {
      return this.reservoirs.find(r=>r.alias===alias) || { pct:0, online:false };
    },

    ...wsMixin(),
    ...reservoirModalMixin(),

    async init() {
      const [resv, pumps, valves, hydros, gw] = await Promise.all([
        fetch('/api/reservoirs').then(r=>r.json()),
        fetch('/api/manual/pumps?limit=50').then(r=>r.json()).catch(()=>({items:[]})),
        fetch('/api/manual/valves?limit=50').then(r=>r.json()).catch(()=>({items:[]})),
        fetch('/api/manual/hydrometers?limit=50').then(r=>r.json()).catch(()=>({items:[]})),
        fetch('/api/gateway').then(r=>r.json()).catch(()=>null),
      ]);
      this.reservoirs = resv;
      this.pumps = pumps.items || [];
      this.valves = valves.items || [];
      this.hydrometers = hydros.items || [];
      this._updateGw(gw);

      this.wsConnect((data) => {
        if (data.type === 'snapshot') { this.reservoirs = data.reservoirs; this._updateGw(data.gateway); }
        else if (data.type === 'reading') {
          const idx = this.reservoirs.findIndex(r=>r.alias===data.alias);
          if (idx>=0) this.reservoirs[idx]={...this.reservoirs[idx],...data};
          this.reservoirs=[...this.reservoirs];
        }
      });
    },

    _updateGw(gw) {
      if (!gw) return;
      if (gw.sim_mode) { this.gwStatus='sim'; this.gwLabel='Simulação'; }
      else if (gw.connected) { this.gwStatus='on'; this.gwLabel='GW online'; }
      else { this.gwStatus='off'; this.gwLabel='GW offline'; }
    },

    async setEquip(type, id, status) {
      const url = type==='pump' ? '/api/manual/pumps' : '/api/manual/valves';
      await fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({name:id, status}) });
      if (type==='pump') { const i=this.pumps.findIndex(p=>p.id===id); if(i>=0) this.pumps[i]={...this.pumps[i],status}; this.pumps=[...this.pumps]; }
      else { const i=this.valves.findIndex(v=>v.id===id); if(i>=0) this.valves[i]={...this.valves[i],status}; this.valves=[...this.valves]; }
    },
  };
}
</script>
</body>
</html>
```

- [ ] **Step 2: Verificar no browser**

```bash
# Abrir http://localhost:8001/scada.html
```

Esperado: sidebar, diagrama SVG com reservatórios coloridos, barras de nível animadas, painel lateral com lista de bombas/válvulas.

- [ ] **Step 3: Commit**

```bash
git add frontend/scada.html
git commit -m "feat: SCADA reescrito — SVG topologia IF+IE, painel lateral, ISA-101"
```

---

## Task 6: Análise (`analise.html`)

**Files:**
- Create: `frontend/analise.html`

Consolida `history.html`, `consumption.html`, `abastecimento.html`, `dados.html` em uma página com 4 abas Alpine.js.

- [ ] **Step 1: Criar analise.html**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Aguada — Análise</title>
  <link rel="stylesheet" href="assets/aguada.css"/>
  <style>[x-cloak]{display:none}</style>
</head>
<body>
<div class="layout" x-data="analiseApp()" x-init="init()" x-cloak>

  <!-- Sidebar (idêntica) -->
  <aside class="sidebar">
    <div class="sidebar-brand"><div class="sidebar-logo">A</div><span class="sidebar-brand-text">AGUADA</span></div>
    <nav class="sidebar-nav">
      <div class="sidebar-section">Operação</div>
      <a href="index.html" class="nav-link"><span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg></span><span class="nav-label">Dashboard</span></a>
      <a href="scada.html" class="nav-link"><span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/><path d="M12 1v4M12 19v4M4.22 4.22l2.83 2.83M16.95 16.95l2.83 2.83M1 12h4M19 12h4M4.22 19.78l2.83-2.83M16.95 7.05l2.83-2.83"/></svg></span><span class="nav-label">SCADA</span></a>
      <div class="sidebar-section">Análise</div>
      <a href="analise.html" class="nav-link active"><span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg></span><span class="nav-label">Análise</span></a>
      <div class="sidebar-section">Gestão</div>
      <a href="report.html" class="nav-link"><span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></span><span class="nav-label">Relatório</span></a>
      <a href="dispositivos.html" class="nav-link"><span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><rect x="5" y="2" width="14" height="20" rx="2"/><line x1="12" y1="18" x2="12" y2="18"/></svg></span><span class="nav-label">Dispositivos</span></a>
      <a href="documentacao.html" class="nav-link"><span class="nav-icon"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg></span><span class="nav-label">Documentação</span></a>
    </nav>
    <div class="sidebar-footer"><span class="gw-dot off"></span><span class="gw-label">GW</span></div>
  </aside>

  <div class="main">
    <div class="topbar">
      <div><div class="topbar-title">Análise</div><div class="topbar-sub">Histórico, Consumo, Abastecimento, Dados</div></div>
      <div class="topbar-right">
        <button class="theme-btn" onclick="toggleTheme()"><svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/></svg></button>
      </div>
    </div>

    <!-- Abas -->
    <div class="tabs">
      <button class="tab-btn" :class="{active:tab==='historico'}" @click="switchTab('historico')">Histórico</button>
      <button class="tab-btn" :class="{active:tab==='consumo'}" @click="switchTab('consumo')">Consumo</button>
      <button class="tab-btn" :class="{active:tab==='abastecimento'}" @click="switchTab('abastecimento')">Abastecimento</button>
      <button class="tab-btn" :class="{active:tab==='dados'}" @click="switchTab('dados')">Dados</button>
    </div>

    <div class="content">

      <!-- ABA: Histórico -->
      <div x-show="tab==='historico'">
        <div style="display:flex;gap:10px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
          <select class="form-select" style="width:160px" x-model="hist.alias" @change="loadHistorico()">
            <option value="">Todos</option>
            <template x-for="a in aliases" :key="a"><option :value="a" x-text="a"></option></template>
          </select>
          <div style="display:flex;gap:4px">
            <template x-for="p in ['24h','7d','30d']" :key="p">
              <button class="eq-btn" :class="{active:hist.period===p}" @click="hist.period=p;loadHistorico()" x-text="p"></button>
            </template>
          </div>
          <span style="font-size:11px;color:var(--text3)" x-show="hist.loading">Carregando...</span>
        </div>
        <div class="card" style="padding:16px">
          <canvas id="histChart" height="80"></canvas>
        </div>
      </div>

      <!-- ABA: Consumo -->
      <div x-show="tab==='consumo'">
        <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap">
          <select class="form-select" style="width:160px" x-model="cons.alias" @change="loadConsumo()">
            <option value="">Todos</option>
            <template x-for="a in aliases" :key="a"><option :value="a" x-text="a"></option></template>
          </select>
          <input class="form-input" type="date" style="width:160px" x-model="cons.date" @change="loadConsumo()"/>
        </div>
        <div class="card" style="padding:16px">
          <canvas id="consChart" height="80"></canvas>
        </div>
      </div>

      <!-- ABA: Abastecimento -->
      <div x-show="tab==='abastecimento'">
        <div class="section-title" style="margin-bottom:12px">Registros de Abastecimento</div>
        <div class="card">
          <table style="width:100%;border-collapse:collapse;font-size:12px">
            <thead><tr style="border-bottom:1px solid var(--border)">
              <th style="padding:8px 12px;text-align:left;color:var(--text3);font-weight:500">Reservatório</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">Volume (m³)</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">Nota</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">Data</th>
            </tr></thead>
            <tbody>
              <template x-for="row in abast.items" :key="row.id">
                <tr style="border-bottom:1px solid var(--border)">
                  <td style="padding:7px 12px;font-family:var(--mono);color:var(--blue)" x-text="row.alias||row.reservoir_alias||'—'"></td>
                  <td style="padding:7px 12px;text-align:right;font-family:var(--mono)" x-text="row.volume_m3!=null?row.volume_m3+' m³':row.note||'—'"></td>
                  <td style="padding:7px 12px;text-align:right;color:var(--text2)" x-text="row.note||'—'"></td>
                  <td style="padding:7px 12px;text-align:right;color:var(--text3);font-size:11px" x-text="formatTs(row.ts)"></td>
                </tr>
              </template>
              <tr x-show="!abast.items.length"><td colspan="4" style="padding:20px;text-align:center;color:var(--text3)">Sem registros</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <!-- ABA: Dados -->
      <div x-show="tab==='dados'">
        <div style="display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center">
          <select class="form-select" style="width:140px" x-model="dados.alias">
            <option value="">Todos</option>
            <template x-for="a in aliases" :key="a"><option :value="a" x-text="a"></option></template>
          </select>
          <div style="display:flex;gap:4px">
            <template x-for="p in ['24h','7d','30d']" :key="p">
              <button class="eq-btn" :class="{active:dados.period===p}" @click="dados.period=p;loadDados()" x-text="p"></button>
            </template>
          </div>
          <button class="btn btn-secondary" @click="loadDados()">Atualizar</button>
          <button class="btn btn-secondary" @click="exportCsv()">Exportar CSV</button>
        </div>
        <div class="card">
          <table style="width:100%;border-collapse:collapse;font-size:12px">
            <thead><tr style="border-bottom:1px solid var(--border)">
              <th style="padding:8px 12px;text-align:left;color:var(--text3);font-weight:500">Alias</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">%</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">Volume (L)</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">Nível (cm)</th>
              <th style="padding:8px 12px;text-align:right;color:var(--text3);font-weight:500">Data/Hora</th>
            </tr></thead>
            <tbody>
              <template x-for="row in dados.rows" :key="row.ts+row.alias">
                <tr style="border-bottom:1px solid var(--border)">
                  <td style="padding:6px 12px;font-family:var(--mono);color:var(--blue)" x-text="row.alias"></td>
                  <td style="padding:6px 12px;text-align:right;font-family:var(--mono)" :style="`color:${statusColor(row.pct,true)}`" x-text="row.pct!=null?Math.round(row.pct)+'%':'—'"></td>
                  <td style="padding:6px 12px;text-align:right;font-family:var(--mono)" x-text="row.volume_l!=null?Math.round(row.volume_l):'—'"></td>
                  <td style="padding:6px 12px;text-align:right;font-family:var(--mono)" x-text="row.level_cm!=null?row.level_cm:'—'"></td>
                  <td style="padding:6px 12px;text-align:right;color:var(--text3);font-size:11px" x-text="formatTs(row.ts)"></td>
                </tr>
              </template>
              <tr x-show="!dados.rows.length"><td colspan="5" style="padding:20px;text-align:center;color:var(--text3)">Sem dados</td></tr>
            </tbody>
          </table>
        </div>
      </div>

    </div>
  </div>
</div>

<script src="assets/shared.js"></script>
<script src="assets/vendor/chart.min.js"></script>
<script defer src="assets/vendor/alpine.min.js"></script>
<script>
const CHART_DEFAULTS = {
  responsive: true, maintainAspectRatio: true,
  plugins: { legend: { labels: { color: '#c9d4e0', font: { size: 11 } } } },
  scales: {
    x: { ticks: { color: '#6b82a0', maxTicksLimit: 10 }, grid: { color: '#1e2d3d' } },
    y: { ticks: { color: '#6b82a0' }, grid: { color: '#1e2d3d' }, min: 0, max: 100 },
  }
};

function analiseApp() {
  return {
    tab: 'historico',
    aliases: ['CON','CAV','CB31','CB32','CIE1','CIE2','CBIF1','CBIF2'],
    hist:  { alias: '', period: '24h', loading: false },
    cons:  { alias: '', date: new Date().toISOString().slice(0,10) },
    abast: { items: [] },
    dados: { alias: '', period: '24h', rows: [] },
    _histChart: null,
    _consChart: null,

    async init() {
      await Promise.all([this.loadHistorico(), this.loadConsumo(), this.loadAbastecimento(), this.loadDados()]);
    },

    async switchTab(t) {
      this.tab = t;
      await this.$nextTick();
      if (t==='historico') this._renderHistChart(this._lastHistData||[]);
      if (t==='consumo')   this._renderConsChart(this._lastConsData||[]);
    },

    async loadHistorico() {
      this.hist.loading = true;
      const aliases = this.hist.alias ? [this.hist.alias] : this.aliases;
      const datasets = await Promise.all(aliases.map(async a => {
        const r = await fetch(`/api/history/${a}?period=${this.hist.period}`).then(r=>r.json()).catch(()=>[]);
        const color = ALIAS_FILL_COLORS[a] || '#3b82f6';
        return { label: a, data: r.map(p=>({x: new Date(p.ts*1000).toLocaleString('pt-BR'), y: Math.round(p.pct||0)})), borderColor: color, backgroundColor: color+'22', tension: 0.3, pointRadius: 0, fill: false };
      }));
      this._lastHistData = datasets;
      this.hist.loading = false;
      await this.$nextTick();
      this._renderHistChart(datasets);
    },

    _renderHistChart(datasets) {
      const ctx = document.getElementById('histChart');
      if (!ctx) return;
      if (this._histChart) this._histChart.destroy();
      this._histChart = new Chart(ctx, { type:'line', data:{ datasets }, options:{ ...CHART_DEFAULTS, parsing:{ xAxisKey:'x', yAxisKey:'y' } } });
    },

    async loadConsumo() {
      const alias = this.cons.alias || 'CON';
      const r = await fetch(`/api/consumption?alias=${alias}&date=${this.cons.date}`).then(r=>r.json()).catch(()=>[]);
      this._lastConsData = r;
      await this.$nextTick();
      this._renderConsChart(r);
    },

    _renderConsChart(data) {
      const ctx = document.getElementById('consChart');
      if (!ctx) return;
      if (this._consChart) this._consChart.destroy();
      const labels = data.map(d=>d.date||d.label||'');
      const vals = data.map(d=>d.volume_l||d.value||0);
      this._consChart = new Chart(ctx, { type:'bar', data:{ labels, datasets:[{ label:'Consumo (L)', data:vals, backgroundColor:'#3b82f644', borderColor:'#3b82f6', borderWidth:1 }] }, options:{ ...CHART_DEFAULTS, scales:{ x:{ticks:{color:'#6b82a0'},grid:{color:'#1e2d3d'}}, y:{ticks:{color:'#6b82a0'},grid:{color:'#1e2d3d'}} } } });
    },

    async loadAbastecimento() {
      const r = await fetch('/api/manual/reservoirs?limit=200').then(r=>r.json()).catch(()=>({items:[]}));
      this.abast.items = r.items || [];
    },

    async loadDados() {
      const aliases = this.dados.alias ? [this.dados.alias] : this.aliases;
      const all = await Promise.all(aliases.map(a => fetch(`/api/history/${a}?period=${this.dados.period}`).then(r=>r.json()).catch(()=>[])));
      this.dados.rows = all.flat().sort((a,b)=>b.ts-a.ts).slice(0,500);
    },

    exportCsv() {
      const header = 'alias,pct,volume_l,level_cm,ts\n';
      const rows = this.dados.rows.map(r=>`${r.alias},${r.pct||''},${r.volume_l||''},${r.level_cm||''},${r.ts||''}`).join('\n');
      const blob = new Blob([header+rows], { type:'text/csv' });
      const a = document.createElement('a'); a.href=URL.createObjectURL(blob); a.download='aguada-dados.csv'; a.click();
    },

    formatTs, statusColor,
  };
}
</script>
</body>
</html>
```

- [ ] **Step 2: Verificar no browser**

```bash
# Abrir http://localhost:8001/analise.html
```

Esperado: 4 abas funcionando, gráficos renderizando, tabela de dados com exportação CSV.

- [ ] **Step 3: Commit**

```bash
git add frontend/analise.html
git commit -m "feat: analise.html — Histórico, Consumo, Abastecimento e Dados em 4 abas"
```

---

## Task 7: Páginas Restantes (Relatório, Dispositivos, Documentação)

**Files:**
- Modify: `frontend/report.html`, `frontend/dispositivos.html`, `frontend/documentacao.html`

Migração de estilo: substituir header/navbar Tailwind pela sidebar + topbar do `aguada.css`. Lógica Alpine inalterada.

- [ ] **Step 1: Atualizar report.html — substituir `<head>` e navegação**

Localizar e substituir o bloco `<head>` em `frontend/report.html`:

```html
<!-- ANTES (remover): -->
<link rel="stylesheet" href="assets/tailwind.css?v=1" />
<script src="assets/shared.js"></script>
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3/dist/cdn.min.js"></script>

<!-- DEPOIS (adicionar): -->
<link rel="stylesheet" href="assets/aguada.css" />
<script src="assets/shared.js"></script>
<script defer src="assets/vendor/alpine.min.js"></script>
```

Substituir o `<header>` + `<main>` do Tailwind pelo layout sidebar:

```html
<div class="layout" x-data="reportApp()" x-init="init()" x-cloak>
  <!-- Sidebar -->
  <aside class="sidebar">
    <div class="sidebar-brand"><div class="sidebar-logo">A</div><span class="sidebar-brand-text">AGUADA</span></div>
    <nav class="sidebar-nav">
      <div class="sidebar-section">Operação</div>
      <a href="index.html" class="nav-link"><span class="nav-icon">📊</span><span class="nav-label">Dashboard</span></a>
      <a href="scada.html" class="nav-link"><span class="nav-icon">⚙</span><span class="nav-label">SCADA</span></a>
      <div class="sidebar-section">Análise</div>
      <a href="analise.html" class="nav-link"><span class="nav-icon">📈</span><span class="nav-label">Análise</span></a>
      <div class="sidebar-section">Gestão</div>
      <a href="report.html" class="nav-link active"><span class="nav-icon">📄</span><span class="nav-label">Relatório</span></a>
      <a href="dispositivos.html" class="nav-link"><span class="nav-icon">📡</span><span class="nav-label">Dispositivos</span></a>
      <a href="documentacao.html" class="nav-link"><span class="nav-icon">📚</span><span class="nav-label">Documentação</span></a>
    </nav>
    <div class="sidebar-footer"><span class="gw-dot off"></span><span class="gw-label">GW</span></div>
  </aside>
  <div class="main">
    <div class="topbar">
      <div><div class="topbar-title">Relatório Diário</div></div>
      <div class="topbar-right"><button class="theme-btn" onclick="toggleTheme()">☀</button></div>
    </div>
    <div class="content">
      <!-- conteúdo existente do reportApp() permanece aqui inalterado -->
    </div>
  </div>
</div>
```

Remover o `<body class="bg-gray-...">` e o `<header>` antigo.

- [ ] **Step 2: Aplicar o mesmo padrão em dispositivos.html**

Mesmo processo: trocar imports, trocar `<header>` + `<main>` pela sidebar + topbar, deixar Alpine app intacto. Página ativa na sidebar: `dispositivos.html`.

- [ ] **Step 3: Atualizar documentacao.html — migrar + expandir com accordion**

Trocar imports e navegação. Adicionar seções accordion Alpine ao conteúdo:

```html
<!-- Dentro do .content, após o conteúdo existente, adicionar: -->
<div class="section-title" style="margin-top:24px">Instruções Operacionais</div>
<div x-data="{open:null}">
  <template x-for="(sec, i) in docSections" :key="i">
    <div class="card" style="margin-bottom:8px">
      <div class="card-header" style="cursor:pointer" @click="open=open===i?null:i">
        <div style="font-weight:500" x-text="sec.title"></div>
        <span x-text="open===i?'▲':'▼'" style="color:var(--text3);font-size:11px"></span>
      </div>
      <div x-show="open===i" style="padding:14px 16px;font-size:13px;color:var(--text2);white-space:pre-wrap;line-height:1.7" x-text="sec.content"></div>
    </div>
  </template>
</div>
```

E no script Alpine:

```javascript
docSections: [
  { title: 'Manual de Operação', content: `// conteúdo do manual_operacao_aguada_web.md` },
  { title: 'Calibração de Sensores', content: `Procedimento de calibração:\n1. Verificar sensor ultrassônico HC-SR04\n2. Medir distância conhecida\n3. Ajustar offset no reservoirs.yaml\n4. Reiniciar bridge.py` },
  { title: 'Procedimentos de Emergência', content: `Em caso de falha de sensor:\n1. Registrar leitura manual no Dashboard\n2. Verificar conexão USB do gateway\n3. Consultar bridge.log` },
  { title: 'Formulário de Manutenção', content: `Data: ___/___/___\nTécnico: __________\nEquipamento: ______\nProblema: _________\nAção tomada: ______\nAssinatura: _______` },
]
```

- [ ] **Step 4: Verificar as 3 páginas no browser**

```bash
# report.html — seletor de data, tabela de resumo, botão PDF
# dispositivos.html — cards de nós, RSSI, status
# documentacao.html — accordion com seções
```

- [ ] **Step 5: Commit**

```bash
git add frontend/report.html frontend/dispositivos.html frontend/documentacao.html
git commit -m "feat: report, dispositivos e documentacao migrados para sidebar aguada.css"
```

---

## Task 8: Remover páginas obsoletas e polimento final

**Files:**
- Delete: `frontend/history.html`, `frontend/consumption.html`, `frontend/abastecimento.html`, `frontend/dados.html`
- Modify: todos os HTMLs (responsividade, revisão ISA-101)

- [ ] **Step 1: Remover páginas consolidadas**

```bash
rm frontend/history.html frontend/consumption.html frontend/abastecimento.html frontend/dados.html
git add -A
git commit -m "chore: remover páginas consolidadas em analise.html"
```

- [ ] **Step 2: Adicionar toggle sidebar mobile em todas as páginas**

Em todas as páginas, adicionar no topbar o botão de menu mobile e o script de toggle:

```html
<!-- No topbar-right de cada página, antes do theme-btn: -->
<button class="theme-btn" id="sidebar-toggle"
  onclick="document.querySelector('.sidebar').classList.toggle('mobile-open')"
  style="display:none">
  <svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
    <line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>
  </svg>
</button>
```

```html
<!-- Antes do </body> de cada página: -->
<script>
// Mostrar toggle mobile em telas pequenas
if (window.innerWidth <= 1024) {
  document.getElementById('sidebar-toggle').style.display = 'flex';
}
window.addEventListener('resize', () => {
  const btn = document.getElementById('sidebar-toggle');
  if (btn) btn.style.display = window.innerWidth <= 1024 ? 'flex' : 'none';
});
</script>
```

- [ ] **Step 3: Verificar responsividade**

Redimensionar o browser para 768px e verificar:
- Sidebar some (posição fixed fora da tela)
- Botão ☰ aparece no topbar
- Clicar ☰ abre sidebar como overlay

- [ ] **Step 4: Revisão ISA-101 — verificar cores em todos os estados**

No Dashboard, confirmar que:
- Marcador verde: `pct > 35 && online`
- Marcador amarelo: `pct <= 35 && pct > 20 && online`
- Marcador vermelho: `pct <= 20 && online`
- Marcador cinza: `!online`

No SCADA, confirmar que as barras de nível nos reservatórios usam a cor correspondente ao percentual.

- [ ] **Step 5: Verificar tiles Leaflet offline**

```bash
ls frontend/assets/leaflet-tiles/16/
# deve ter subdiretórios x/y.png
```

Abrir Dashboard sem internet e confirmar que o mapa carrega dos tiles locais.

- [ ] **Step 6: Commit final**

```bash
git add -A
git commit -m "feat: polimento final — sidebar mobile, ISA-101, tiles OSM verificados"
```

---

## Self-Review

**Spec coverage:**

| Requisito do spec | Task |
|---|---|
| CSS aguada.css com variáveis escuro/claro | Task 2 |
| Vendors offline (Alpine, Chart.js, Leaflet) | Task 1 |
| Script download vendors + tiles OSM | Task 1 |
| Ícones PNG (pump, valve, hydrometer) | Task 1 |
| shared.js: toggleTheme, wsMixin, sidebarState | Task 3 |
| Dashboard: KPI strip + Leaflet + marcadores coloridos | Task 4 |
| Dashboard: modal lateral com leitura manual | Task 4 |
| Dashboard: WebSocket ao vivo nos marcadores | Task 4 |
| SCADA: SVG topologia IF+IE baseado no aguada2 | Task 5 |
| SCADA: painel lateral bombas/válvulas/hidrômetros | Task 5 |
| SCADA: ISA-101 cores | Task 5 |
| Análise: 4 abas (Histórico, Consumo, Abastecimento, Dados) | Task 6 |
| Análise: exportação CSV | Task 6 |
| Relatório: migrado com novo layout | Task 7 |
| Dispositivos: migrado com novo layout | Task 7 |
| Documentação: migrado + accordion expandido | Task 7 |
| Remover páginas obsoletas | Task 8 |
| Responsividade mobile | Task 8 |
| Sidebar colapsável hover/toggle | Task 2 (CSS) + Task 4/5/6/7 (HTML) |
| lat/lng em reservoirs.yaml + API | Já implementado ✓ |

**Verificações de consistência:**
- `wsMixin()` definido em Task 3 (shared.js), usado em Task 4 e 5 ✓
- `reservoirModalMixin()` definido em Task 3, usado em Task 4 e 5 ✓
- `statusColor()` e `markerColor()` definidos em Task 3, usados em Task 4, 5, 6 ✓
- `formatTs()` e `timeAgo()` mantidos em Task 3, referenciados nos templates ✓
- `ALIAS_FILL_COLORS` definido em Task 3, usado em Task 6 ✓
- Classes CSS `.sidebar`, `.nav-link`, `.eq-card`, `.badge-*`, `.tank-wrap` definidas em Task 2, usadas em Tasks 4-8 ✓
- `getR(alias)` definido dentro de `scadaApp()` em Task 5 ✓
