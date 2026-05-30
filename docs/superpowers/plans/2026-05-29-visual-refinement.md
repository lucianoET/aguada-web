# Visual Refinement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refinar visualmente o sistema sem tocar lógica de negócio — tipografia, paleta, header adaptável ao tema, cards de reservatório com água como background e dados em sobreposição.

**Architecture:** Mudanças exclusivamente em CSS (aguada.css, style.css) e na seção `<style>` + template HTML do painel.html. A função `init()` do Alpine.js recebe fetch adicional de `/api/consumption` para preencher consumo diário e taxa nos cards. Nenhuma rota nova, nenhuma mudança no banco.

**Tech Stack:** CSS custom properties, Alpine.js x-data, FastAPI existente, pytest para smoke test de rotas.

---

## File Map

| Arquivo | O que muda |
|---|---|
| `frontend/assets/aguada.css` | `--mono`, `--sans`, `--bg` (claro), `--card-shadow` (novo token) |
| `frontend/assets/style.css` | `.admin-header` sem gradiente hardcoded; `.admin-nav a.active` usa `var(--blue)`; remove vars duplicadas |
| `frontend/painel.html` | CSS inline: `.tank-card` reescrito; `.hero-kpi` com shadow; JS: `init()` + `tankWaterStyle()` + `tankCardClass()` novo |

---

## Task 1: Variáveis de fonte e paleta — `aguada.css`

**Files:**
- Modify: `frontend/assets/aguada.css:31-32` (vars --mono e --sans no :root)
- Modify: `frontend/assets/aguada.css:11` (--bg tema claro)

- [ ] **Step 1: Localizar as linhas alvo**

```bash
grep -n "\-\-mono\|\-\-sans\|\-\-bg:" frontend/assets/aguada.css
```

Esperado: linhas com `--mono: 'Courier New'`, `--sans: system-ui`, `--bg: #f1f5f9`.

- [ ] **Step 2: Substituir --mono e --sans no :root**

No bloco `:root { ... }` de `frontend/assets/aguada.css`, alterar:

```css
/* de: */
--mono: 'Courier New', Courier, monospace;
--sans: system-ui, -apple-system, 'Segoe UI', sans-serif;

/* para: */
--mono: 'JetBrains Mono', 'Courier New', monospace;
--sans: 'DM Sans', system-ui, -apple-system, sans-serif;
```

- [ ] **Step 3: Ajustar --bg e adicionar --card-shadow no :root**

```css
/* de: */
--bg: #f1f5f9;

/* para: */
--bg: #f0f4f8;
```

Após a linha `--radius: 8px;` no `:root`, adicionar:

```css
--card-shadow: 0 1px 3px rgba(0,0,0,.06), 0 2px 8px rgba(0,0,0,.04);
```

No bloco `[data-theme="dark"]`, adicionar (sem mudar `--bg` do dark):

```css
--card-shadow: none;
```

- [ ] **Step 4: Verificar que pytest passa**

```bash
pytest tests/ -q
```

Esperado: todos os testes passam (mudança é só CSS).

- [ ] **Step 5: Commit**

```bash
git add frontend/assets/aguada.css
git commit -m "style: wire DM Sans and JetBrains Mono to CSS vars, refine light bg"
```

---

## Task 2: Header adaptável ao tema — `style.css`

**Files:**
- Modify: `frontend/assets/style.css` — `.admin-header`, `.admin-header-brand`, `.admin-nav a`, `.admin-nav a.active`

- [ ] **Step 1: Localizar o bloco admin-header**

```bash
grep -n "admin-header\|gradient" frontend/assets/style.css | head -20
```

- [ ] **Step 2: Substituir o bloco .admin-header**

Localizar e substituir:

```css
/* DE: */
.admin-header {
    background: linear-gradient(135deg, #1e3a5f 0%, #2d4a6f 100%);
    color: white; box-shadow: 0 2px 10px rgba(0,0,0,.2);
    position: sticky; top: 0; z-index: 1000;
    display: flex; align-items: center; height: 46px;
}

/* PARA: */
.admin-header {
    background: var(--bg2);
    border-bottom: 1px solid var(--border);
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
    position: sticky; top: 0; z-index: 1000;
    display: flex; align-items: center; height: 48px;
}
```

- [ ] **Step 3: Atualizar cores do brand e nav**

```css
/* DE: */
.admin-header-brand {
    padding: 0 18px; font-size: 15px; font-weight: 700; color: white;
    ...
}

/* PARA: */
.admin-header-brand {
    padding: 0 18px; font-size: 14px; font-weight: 700; color: var(--text);
    white-space: nowrap; letter-spacing: -.01em; height: 100%;
    display: flex; align-items: center;
    border-right: 1px solid var(--border); flex-shrink: 0;
    font-family: var(--sans);
}
```

```css
/* DE: */
.admin-nav a {
    padding: 0 13px; color: rgba(255,255,255,.75); ...
}
.admin-nav a:hover { background: rgba(255,255,255,.1); color: white; }
.admin-nav a.active { border-bottom-color: #10b981; color: white; background: rgba(255,255,255,.08); }

/* PARA: */
.admin-nav a {
    padding: 0 13px; color: var(--text3); text-decoration: none;
    font-size: var(--font-sm); font-weight: 500; border-bottom: 2px solid transparent;
    display: flex; align-items: center; white-space: nowrap; transition: all .15s;
    font-family: var(--sans);
}
.admin-nav a:hover { color: var(--text2); }
.admin-nav a.active { border-bottom-color: var(--blue); color: var(--text); background: transparent; }
```

- [ ] **Step 4: Remover variáveis CSS duplicadas do topo de style.css**

No bloco `:root { ... }` de `style.css`, remover as seguintes linhas (são redefinições que conflitam com `aguada.css`):

```css
/* REMOVER: */
--background-light: #f8f9fa;
--border-color: #e5e7eb;
--text-dark: #1f2937;
--text-muted: #6b7280;
--success-green: #10b981;
--warning-orange: #f59e0b;
--danger-red: #ef4444;
```

Manter: `--primary-blue`, `--primary-light`, `--accent-purple`, `--accent-pink`, `--font-*` (usados em componentes de outras páginas).

- [ ] **Step 5: Pytest**

```bash
pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add frontend/assets/style.css
git commit -m "style: make admin header theme-aware, fix nav active color, remove duplicate vars"
```

---

## Task 3: CSS dos tank cards — `painel.html`

**Files:**
- Modify: `frontend/painel.html` — bloco `<style>` interno, seção dos seletores `.tank-*`

- [ ] **Step 1: Localizar CSS inline dos tanks**

```bash
grep -n "tank-card\|tank-water\|tank-visual\|tank-name\|tank-values" frontend/painel.html | head -30
```

- [ ] **Step 2: Substituir todo o bloco de CSS dos tank cards**

No `<style>` interno do painel.html, localizar e substituir **todos** os seletores `.tank-card`, `.tank-name`, `.tank-visual`, `.tank-water`, `.tank-overlay`, `.tank-status-corner`, `.tank-status-dot`, `.tank-values`, `.tank-alias`, `.tank-pct-line`, `.tank-pct-value`, `.tank-pct-unit`, `.tank-volume-line`, `.tank-datetime` pelo seguinte bloco:

```css
/* ── Tank Cards redesign ── */
.tank-card {
  position: relative;
  overflow: hidden;
  border-radius: 12px;
  border: 1px solid var(--border2);
  background: var(--bg2);
  height: 240px;
  cursor: pointer;
  transition: border-color .2s, box-shadow .2s;
  display: flex;
  flex-direction: column;
}
.tank-card:hover { border-color: var(--blue); box-shadow: 0 4px 16px rgba(37,99,235,.1); }
.tank-card.state-warn { border-color: #fde68a; }
[data-theme="dark"] .tank-card.state-warn { border-color: #2a2010; }
.tank-card.state-critical { border-color: var(--red-dim); }
.tank-card.state-offline { opacity: .7; }

/* Water background — no text inside */
.tank-water {
  position: absolute;
  left: 0; right: 0; bottom: 0;
  border-top: 2px solid;
  transition: height .5s ease;
  pointer-events: none;
}

/* Content overlay */
.tank-content {
  position: absolute;
  inset: 0;
  padding: 11px 12px;
  z-index: 2;
  display: flex;
  flex-direction: column;
}

/* Header: name + alias + dot */
.tank-hdr {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 8px;
}
.tank-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
  font-family: var(--sans);
  letter-spacing: -.01em;
  line-height: 1.2;
}
.tank-alias {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  color: var(--text3);
  letter-spacing: .1em;
  margin-top: 2px;
}
.tank-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-top: 3px;
  flex-shrink: 0;
}

/* Main KPI: volume m³ + % */
.tank-kpi {
  display: flex;
  align-items: flex-end;
  gap: 6px;
  margin-bottom: 4px;
  flex-wrap: wrap;
}
.tank-vol {
  font-family: var(--mono);
  font-size: 28px;
  font-weight: 700;
  line-height: 1;
  letter-spacing: -.03em;
}
.tank-vol-unit {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  padding-bottom: 3px;
  opacity: .6;
}
.tank-pct-sep {
  width: 1px;
  height: 20px;
  background: var(--border2);
  margin: 0 2px 3px;
  flex-shrink: 0;
}
.tank-pct {
  font-family: var(--mono);
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
  padding-bottom: 1px;
  letter-spacing: -.02em;
  opacity: .75;
}

/* Spacer pushes detail to bottom */
.tank-spacer { flex: 1; }

/* Detail grid: 2x2 */
.tank-detail {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 5px 10px;
}
.tank-d-lbl {
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: .09em;
  font-weight: 600;
  color: var(--text3);
  font-family: var(--sans);
  opacity: .7;
}
.tank-d-val {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--text2);
  margin-top: 1px;
}
.tank-d-val.accent { color: var(--yellow); }
[data-theme="dark"] .tank-d-val.accent { color: #fcd34d; }
```

- [ ] **Step 3: Verificar que nenhum CSS antigo permaneceu**

```bash
grep -n "tank-visual\|tank-overlay\|tank-pct-value\|tank-volume-line" frontend/painel.html
```

Esperado: nenhuma linha retornada.

- [ ] **Step 4: Pytest**

```bash
pytest tests/ -q
```

- [ ] **Step 5: Commit**

```bash
git add frontend/painel.html
git commit -m "style: rewrite tank card CSS — water background, data overlay"
```

---

## Task 4: HTML do template de tank cards — `painel.html`

**Files:**
- Modify: `frontend/painel.html` — `<template x-for="r in sortedReservoirs">` (aprox. linha 380)

- [ ] **Step 1: Localizar o template atual**

```bash
grep -n "x-for.*sortedReservoirs\|tank-card\|tank-visual\|tank-overlay" frontend/painel.html | head -20
```

- [ ] **Step 2: Substituir o template completo do card**

Localizar `<template x-for="r in sortedReservoirs" :key="r.alias">` e substituir o conteúdo interno (o `<div class="tank-card">` e tudo dentro até o `</div>` correspondente) por:

```html
<template x-for="r in sortedReservoirs" :key="r.alias">
  <div class="tank-card"
       :class="tankCardClass(r)"
       @click="openResModal(r.alias)">

    <!-- água sobe do fundo — sem texto dentro -->
    <div class="tank-water" :style="tankWaterStyle(r)"></div>

    <!-- conteúdo em z-index 2 -->
    <div class="tank-content">

      <!-- header: nome + alias + dot -->
      <div class="tank-hdr">
        <div>
          <div class="tank-name" x-text="r.name || r.alias || '—'"></div>
          <div class="tank-alias" x-text="r.alias"></div>
        </div>
        <span class="tank-status-dot"
              :style="`background:${r.online ? 'var(--green)' : 'var(--red)'};
                       box-shadow:0 0 7px ${r.online ? 'rgba(34,197,94,.6)' : 'rgba(220,38,38,.5)'}`">
        </span>
      </div>

      <!-- KPI principal: volume m³ + % — cor pelo estado -->
      <div class="tank-kpi">
        <span class="tank-vol"
              :style="tankKpiColor(r)"
              x-text="r.volume_l != null ? (r.volume_l / 1000).toFixed(1) : '—'"></span>
        <span class="tank-vol-unit" x-show="r.volume_l != null" :style="tankKpiColor(r)">m³</span>
        <span class="tank-pct-sep" x-show="r.pct != null && r.volume_l != null"></span>
        <span class="tank-pct"
              :style="tankKpiColor(r)"
              x-text="r.pct != null ? Math.round(r.pct) + '%' : ''"></span>
      </div>

      <div class="tank-spacer"></div>

      <!-- detalhes rodapé -->
      <div class="tank-detail">
        <div>
          <div class="tank-d-lbl">Capacidade</div>
          <div class="tank-d-val"
               x-text="r.capacity_l ? (r.capacity_l / 1000).toFixed(0) + ' m³' : '—'"></div>
        </div>
        <div>
          <div class="tank-d-lbl">Cons. diário</div>
          <div class="tank-d-val"
               x-text="r.consumed_l != null ? Math.round(r.consumed_l).toLocaleString('pt-BR') + ' L' : '—'"></div>
        </div>
        <div>
          <div class="tank-d-lbl">Taxa cons.</div>
          <div class="tank-d-val"
               :class="r.rate_lh > 60 ? 'accent' : ''"
               x-text="r.rate_lh != null ? r.rate_lh + ' L/h' : '—'"></div>
        </div>
        <div>
          <div class="tank-d-lbl">Última leit.</div>
          <div class="tank-d-val" x-text="tankDateTime(r.ts)"></div>
        </div>
      </div>
    </div>
  </div>
</template>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/painel.html
git commit -m "feat: update tank card template — name, volume m³, %, detail grid overlay"
```

---

## Task 5: Funções JS — `tankWaterStyle()`, `tankCardClass()` — `painel.html`

**Files:**
- Modify: `frontend/painel.html` — bloco `x-data="painelApp()"`, função `tankWaterStyle(r)` (aprox. linha 873) e nova função `tankCardClass(r)`

- [ ] **Step 1: Localizar tankWaterStyle**

```bash
grep -n "tankWaterStyle" frontend/painel.html
```

- [ ] **Step 2: Substituir tankWaterStyle(r)**

```javascript
tankWaterStyle(r) {
  const pct = Math.max(0, Number(r?.pct) || 0);
  const minVisible = pct > 0 ? Math.max(pct, 2) : 0;
  const online = r?.online ?? true;

  let bg, borderColor;
  if (!online) {
    bg = 'linear-gradient(180deg, rgba(100,116,139,.15) 0%, rgba(100,116,139,.38) 100%)';
    borderColor = 'rgba(100,116,139,.4)';
  } else if (pct <= 20) {
    bg = 'linear-gradient(180deg, rgba(220,38,38,.15) 0%, rgba(220,38,38,.42) 100%)';
    borderColor = 'rgba(248,113,113,.6)';
  } else if (pct <= 35) {
    bg = 'linear-gradient(180deg, rgba(245,158,11,.15) 0%, rgba(245,158,11,.42) 100%)';
    borderColor = 'rgba(251,191,36,.55)';
  } else {
    bg = 'linear-gradient(180deg, rgba(37,99,235,.18) 0%, rgba(37,99,235,.46) 100%)';
    borderColor = 'rgba(96,165,250,.55)';
  }

  return `height:${minVisible}%; background:${bg}; border-color:${borderColor};`;
},
```

- [ ] **Step 3: Adicionar tankCardClass(r) e tankKpiColor(r) após tankWaterStyle**

```javascript
tankCardClass(r) {
  const pct = Number(r?.pct) || 0;
  const online = r?.online ?? true;
  if (!online) return 'state-offline';
  if (pct <= 20) return 'state-critical';
  if (pct <= 35) return 'state-warn';
  return '';
},

tankKpiColor(r) {
  const pct = Number(r?.pct) || 0;
  if (!r?.online) return 'color:var(--text3)';
  if (pct <= 20) return 'color:var(--red)';
  if (pct <= 35) return 'color:var(--yellow)';
  return 'color:var(--blue)';
},
```

- [ ] **Step 4: Atualizar cores dos valores .tank-vol e .tank-pct no CSS (completar task 3)**

No CSS da Task 3, os seletores `.tank-vol` e `.tank-pct` precisam de cores por estado. As cores são aplicadas via Alpine diretamente no template usando `:style` — não é necessário CSS adicional. Os valores já herdam `color: var(--text)` do card. Verificar visualmente no browser que os números ficam legíveis sobre a água.

- [ ] **Step 5: Pytest**

```bash
pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add frontend/painel.html
git commit -m "feat: state-based tankWaterStyle and tankCardClass (ok/warn/critical/offline)"
```

---

## Task 6: Fetch de dados de consumo no `init()` — `painel.html`

**Files:**
- Modify: `frontend/painel.html` — função `async init()` (aprox. linha 982)

O endpoint `/api/consumption?alias=X&date=YYYY-MM-DD` já existe e retorna:
```json
{
  "summary": { "consumed_l": 1240.5, "supplied_l": 0, "balance_l": -1240.5 },
  "events": [...]
}
```

Taxa de consumo = `consumed_l / horas_decorridas_hoje` onde `horas_decorridas = hora_atual + minuto/60` (mínimo 1h para evitar divisão por zero na madrugada).

- [ ] **Step 1: Localizar o Promise.all no init()**

```bash
grep -n "Promise.all\|getReservoirs\|consumed_l" frontend/painel.html
```

- [ ] **Step 2: Adicionar helper de data e hora ao topo do script**

Antes do `function painelApp()`, adicionar (ou verificar se já existe):

```javascript
function todayDateStr() {
  const d = new Date();
  return d.toISOString().slice(0, 10); // YYYY-MM-DD
}

function hoursElapsedToday() {
  const now = new Date();
  return Math.max(1, now.getHours() + now.getMinutes() / 60);
}
```

- [ ] **Step 3: Adicionar fetchConsumption após init dos reservoirs**

Dentro de `async init()`, após a linha `this.reservoirs = Array.isArray(resData) ? resData : [];`, adicionar:

```javascript
// Buscar consumo de hoje para cada reservatório
const today = todayDateStr();
const consumptionResults = await Promise.allSettled(
  this.reservoirs.map(r =>
    fetch(`/api/consumption?alias=${r.alias}&date=${today}`)
      .then(res => res.json())
      .catch(() => null)
  )
);

const hoursElapsed = hoursElapsedToday();
this.reservoirs = this.reservoirs.map((r, i) => {
  const result = consumptionResults[i];
  if (result.status !== 'fulfilled' || !result.value?.summary) return r;
  const consumed_l = result.value.summary.consumed_l ?? 0;
  const rate_lh = Math.round(consumed_l / hoursElapsed);
  return { ...r, consumed_l, rate_lh };
});
```

- [ ] **Step 4: Verificar que o endpoint responde corretamente**

Com o backend rodando:

```bash
curl "http://localhost:8001/api/consumption?alias=CON&date=$(date +%Y-%m-%d)"
```

Esperado: JSON com `summary.consumed_l` numérico.

- [ ] **Step 5: Pytest**

```bash
pytest tests/ -q
```

- [ ] **Step 6: Commit**

```bash
git add frontend/painel.html
git commit -m "feat: fetch daily consumption and rate for each reservoir on init"
```

---

## Task 7: Hero KPI strip — `painel.html`

**Files:**
- Modify: `frontend/painel.html` — CSS inline `.hero-kpi`, `.hero-kpi-lbl`, `.hero-kpi-val`, `.hero-kpi-side`

- [ ] **Step 1: Localizar CSS do hero-kpi**

```bash
grep -n "hero-kpi" frontend/painel.html | head -20
```

- [ ] **Step 2: Adicionar box-shadow e fontes explícitas**

Localizar e modificar os seletores:

```css
/* hero-kpi: adicionar shadow e font */
.hero-kpi {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 10px 12px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-height: 76px;
  box-shadow: var(--card-shadow);   /* NOVO */
}

/* labels: DM Sans explícito */
.hero-kpi-lbl {
  color: var(--text3);
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 0.09em;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  font-family: var(--sans);   /* NOVO */
}

/* valores: JetBrains Mono explícito */
.hero-kpi-val {
  color: var(--text);
  font-family: var(--mono);   /* era var(--mono) já, confirmar */
  font-size: 22px;
  font-weight: 700;
  line-height: 1.05;
  white-space: nowrap;
}

/* side tag: pill estilo */
.hero-kpi-side {
  font-size: 10px;
  font-weight: 600;
  font-family: var(--sans);   /* NOVO */
  color: var(--text3);
  background: var(--bg3);
  border: 1px solid var(--border2);
  border-radius: 999px;
  padding: 3px 8px;
  white-space: nowrap;
  flex-shrink: 0;
  text-align: center;
}
```

- [ ] **Step 3: Pytest**

```bash
pytest tests/ -q
```

- [ ] **Step 4: Commit**

```bash
git add frontend/painel.html
git commit -m "style: hero KPI strip — card shadow, explicit fonts, pill side tags"
```

---

## Task 8: Verificação visual e smoke test

**Files:** nenhum (só verificação)

- [ ] **Step 1: Rodar backend**

```bash
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8001
```

Ou via script: `./tools/start_backend.sh`

- [ ] **Step 2: Abrir o painel e verificar tema claro**

Abrir `http://localhost:8001/painel.html`

Checklist visual:
- [ ] Header usa fundo do tema (branco no claro, escuro no escuro) — sem gradiente azul fixo
- [ ] Fontes dos números são JetBrains Mono (serifas quadradas, não Courier)
- [ ] Labels em DM Sans (rounded, sans-serif)
- [ ] Tank cards mostram água subindo do fundo sem texto dentro da água
- [ ] Nome do reservatório visível e em negrito no topo do card
- [ ] Volume em m³ e % grandes abaixo do nome
- [ ] Grade de detalhes (capacidade, consumo, taxa, última leit.) no rodapé do card
- [ ] Cards com pct ≤ 35 mostram borda âmbar
- [ ] Cards com pct ≤ 20 mostram borda vermelha

- [ ] **Step 3: Alternar para tema escuro e reverificar**

Clicar no botão de tema (se existir no topbar) ou adicionar `data-theme="dark"` ao `<html>` via DevTools.

- [ ] **Step 4: Rodar pytest final**

```bash
pytest tests/ -v
```

Esperado: todos os testes passam.

- [ ] **Step 5: Commit final de verificação (se houver ajustes)**

```bash
git add -u
git commit -m "fix: visual adjustments after smoke test"
```

---

## Critérios de Aceitação (do spec)

1. Ambos os temas funcionam — header adapta ao tema ✓
2. JetBrains Mono nos números, DM Sans nas labels ✓
3. Cards exibem: nome, volume m³, %, capacidade, consumo diário, taxa, última leitura ✓
4. Água preenche card sem texto sobreposto ✓
5. Estado warn/critical acende borda colorida e cores de alerta ✓
6. `pytest tests/ -q` sem falhas ✓
