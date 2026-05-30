# Frontend HA-Restyle Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Padronizar todas as páginas web (exceto o esquemático SCADA) sobre um único token system e um kit de componentes com a linguagem visual do Home Assistant, preservando a paleta Aguada.

**Architecture:** Adicionar uma "HA component layer" em `aguada.css` (cards arredondados, stat big-number, gauge SVG, listas de entidade, headers de seção). Converter o `:root` de `style.css` em aliases de compatibilidade para os tokens canônicos. Migrar cada página para os componentes `.ha-*`, trocando classes legadas, emojis por SVG e hex fixos por tokens. SCADA recebe só a unificação de token. Sem mudança de backend.

**Tech Stack:** HTML puro + Alpine.js + Tailwind compilado (`tailwind.css`) + Chart.js e Leaflet vendorizados. `aguada.css`/`style.css` são CSS escritos à mão (sem build step). Gauges em SVG vanilla; séries temporais em Chart.js.

---

## Verificação visual (vale para todas as tasks)

Não há testes unitários para CSS. A verificação é visual, em **tema claro E escuro**, com a página servida pelo backend:

1. Subir backend (serve o frontend): `./tools/start_backend.sh` (ou `python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8001`).
2. Usar a skill `webapp-testing` (Playwright) para abrir `http://127.0.0.1:8001/<página>` e tirar screenshot.
3. Alternar tema: o toggle persiste via `localStorage` chave `theme`. Para forçar dark antes de abrir: `localStorage.setItem('theme','dark')` e recarregar; para claro: `localStorage.setItem('theme','light')`.
4. Critério: layout correto, cores corretas nos dois temas, sem hex que ignore o tema, sem regressão de conteúdo.

## Component Mapping Reference (legado → HA)

Tabela única consultada pelas tasks de página:

| Legado (style.css) | Substituir por | Observação |
|---|---|---|
| `.box` + `.box-header`+`h2` + `.box-body` | `.ha-card` + `.ha-card-header`>`.ha-card-title` + `.ha-card-body` | título no `.ha-card-title` |
| `.page-box` | `.ha-card` + `.ha-card-body` | wrapper de conteúdo |
| `.page-title` | `.ha-card-header` com `.ha-card-title` + ações à direita | |
| `.param-grid` / `.param-card` (`.lbl`/`.val`/`.norma`) | `.ha-stat-grid` / `.ha-stat` (`.ha-stat-label`/`.ha-stat-value`/`.ha-stat-delta`) | `.norma` vira `.ha-stat-delta` |
| `.res-cards-grid` / `.res-card` (gradientes `.rc-*`) | `.ha-card` + `.ha-stat` + `renderGauge` | elimina gradientes roxos `#667eea`... |
| `.sum-row` (alerts) | `.ha-entities` / `.ha-entity-row` | |
| `.abadge*` / `.badge-online/offline/warn/danger/ok` | `.badge` + `.badge-{green,yellow,red,blue,gray}` (aguada.css) | |
| tabelas `.admin-main table` cruas | `class="table"` (aguada.css) | |
| `.btn-primary`/`.btn-upload` (roxo) | `.btn .btn-primary` / `.btn .btn-secondary` (aguada.css) | usa `--blue` |
| Emojis (🚨💧🏭🏰⚙️📊✅🔴🟡) em títulos | SVG inline 16px no padrão do painel | manter dentro de `.ha-section`/`.ha-card-title` |
| Hex fixo (`#fef2f2`, `#10b981`, `#667eea`, `#991b1b`...) | token (`--red-dim`, `--green`, `--blue`, `--red`...) | |

SVGs de ícone: reaproveitar os já presentes em `painel.html` (gota, mapa, bomba, válvula, raio, triângulo). Para "alerta" usar o triângulo de aviso; para "ok" o check.

---

### Task 1: HA component layer (CSS)

**Files:**
- Modify: `frontend/assets/aguada.css` (append no fim do arquivo)
- Create (temporário): `frontend/_kit-demo.html`

- [ ] **Step 1: Append o HA component layer em `aguada.css`**

Adicionar ao final de `frontend/assets/aguada.css`:

```css
/* ===================== HA COMPONENT LAYER ===================== */
/* Linguagem visual Home Assistant sobre tokens Aguada. */

.ha-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: var(--card-shadow);
  overflow: hidden;
}
.ha-card-header {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 14px 16px; border-bottom: 1px solid var(--border);
}
.ha-card-title {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 15px; font-weight: 500; color: var(--text);
}
.ha-card-title svg { color: var(--text3); flex-shrink: 0; }
.ha-card-body { padding: 16px; }

/* Stat big-number */
.ha-stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }
.ha-stat { display: flex; flex-direction: column; gap: 4px; padding: 14px 16px; background: var(--card); border: 1px solid var(--border); border-radius: 12px; }
.ha-stat-label { font-size: 10px; text-transform: uppercase; letter-spacing: .08em; font-weight: 600; color: var(--text3); }
.ha-stat-value { font-family: var(--mono); font-size: 28px; font-weight: 700; line-height: 1.05; color: var(--text); }
.ha-stat-unit { font-size: 13px; font-weight: 600; color: var(--text3); margin-left: 2px; }
.ha-stat-delta { font-size: 11px; font-weight: 600; font-family: var(--mono); color: var(--text3); }
.ha-stat-delta.up { color: var(--green); }
.ha-stat-delta.down { color: var(--red); }

/* Entities list (estilo type: entities do HA) */
.ha-entities { display: flex; flex-direction: column; }
.ha-entity-row { display: flex; align-items: center; gap: 10px; padding: 10px 0; border-bottom: 1px solid var(--border); }
.ha-entity-row:last-child { border-bottom: none; }
.ha-entity-row > svg { color: var(--text3); flex-shrink: 0; }
.ha-entity-name { flex: 1; min-width: 0; font-size: 13px; color: var(--text2); }
.ha-entity-value { font-family: var(--mono); font-size: 13px; font-weight: 600; color: var(--text); white-space: nowrap; }
.ha-divider { height: 1px; background: var(--border); margin: 6px 0; }

/* Section header com ícone */
.ha-section { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; color: var(--text); margin: 18px 0 10px; }
.ha-section svg { color: var(--text3); flex-shrink: 0; }

/* Gauge radial (preenchido por renderGauge em ha-ui.js) */
.ha-gauge { display: inline-flex; flex-direction: column; align-items: center; gap: 2px; }
.ha-gauge svg { display: block; }
.ha-gauge-value { font-family: var(--mono); font-size: 20px; font-weight: 700; color: var(--text); margin-top: -8px; }
.ha-gauge-name { font-size: 11px; color: var(--text3); }
```

- [ ] **Step 2: Criar `frontend/_kit-demo.html` para exercitar os componentes**

```html
<!DOCTYPE html>
<html lang="pt-BR"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kit Demo</title>
<link rel="stylesheet" href="assets/aguada.css?v=2">
<link rel="stylesheet" href="assets/style.css">
</head><body class="admin-page"><div class="admin-main" style="display:flex;flex-direction:column;gap:16px;">
  <div class="ha-stat-grid">
    <div class="ha-stat"><span class="ha-stat-label">Volume Total</span><span class="ha-stat-value">648 <span class="ha-stat-unit">m³</span></span><span class="ha-stat-delta up">+27 hoje</span></div>
    <div class="ha-stat"><span class="ha-stat-label">Consumo</span><span class="ha-stat-value">315 <span class="ha-stat-unit">m³</span></span><span class="ha-stat-delta down">-12%</span></div>
  </div>
  <div class="ha-card">
    <div class="ha-card-header"><span class="ha-card-title">Reservatório CON</span><span class="badge badge-green">Normal</span></div>
    <div class="ha-card-body">
      <div class="ha-entities">
        <div class="ha-entity-row"><span class="ha-entity-name">Nível</span><span class="ha-entity-value">68 m³</span></div>
        <div class="ha-entity-row"><span class="ha-entity-name">Percentual</span><span class="ha-entity-value">85%</span></div>
      </div>
      <div class="ha-gauge" id="g1" style="margin-top:12px"></div>
    </div>
  </div>
  <button class="theme-btn" onclick="document.documentElement.dataset.theme=document.documentElement.dataset.theme==='dark'?'light':'dark'">toggle</button>
</div>
<script src="assets/ha-ui.js"></script>
<script>if(window.renderGauge)renderGauge(document.getElementById('g1'),{value:85,severity:{green:40,yellow:20,red:10},unit:'%'});</script>
</body></html>
```

(O gauge fica vazio até a Task 3 criar `ha-ui.js` — esperado.)

- [ ] **Step 3: Verificar visualmente (claro e escuro)**

Subir backend, abrir `http://127.0.0.1:8001/_kit-demo.html`, screenshot em claro e escuro.
Esperado: `.ha-card` com canto 12px e sombra suave (claro) / borda (escuro); `.ha-stat` big-number; badge verde; linhas de entidade com divisórias. Cores corretas nos dois temas. Gauge ainda vazio.

- [ ] **Step 4: Commit**

```bash
git add frontend/assets/aguada.css frontend/_kit-demo.html
git commit -m "feat(css): HA component layer (ha-card, ha-stat, ha-entities, ha-gauge, ha-section)"
```

---

### Task 2: Consolidar tokens — `style.css` :root vira aliases

**Files:**
- Modify: `frontend/assets/style.css:6-26` (bloco `:root`)

- [ ] **Step 1: Substituir o bloco `:root` (linhas 6-26) por aliases canônicos**

Trocar o `:root { ... }` atual por:

```css
:root {
    /* Aliases de compatibilidade → tokens canônicos de aguada.css.
       Mantidos para não quebrar marcação legada durante a migração. */
    --primary-blue: var(--blue);
    --primary-light: var(--blue);
    --accent-purple: var(--blue);
    --accent-pink: var(--cyan);
    --success-green: var(--green);
    --warning-orange: var(--yellow);
    --danger-red: var(--red);

    /* Escala tipográfica (conveniência) */
    --font-base: 14px;
    --font-sm:   12px;
    --font-xs:   11px;
    --font-xxs:  10px;
    --font-lg:   16px;
    --font-xl:   20px;

    --background-light: var(--bg);
    --border-color: var(--border);
    --text-dark: var(--text);
    --text-muted: var(--text3);
}
```

- [ ] **Step 2: Verificar páginas ainda-legadas (claro e escuro)**

Abrir `http://127.0.0.1:8001/qualidade.html` e `.../alerts.html`, screenshot claro e escuro.
Esperado: `.param-card`/`.box`/`.btn-primary` agora usam o azul Aguada (não mais roxo `#667eea`); nada quebrado; dark correto. Pequena mudança de cor de acento é esperada e desejada.

- [ ] **Step 3: Commit**

```bash
git add frontend/assets/style.css
git commit -m "refactor(css): tokens de style.css viram aliases dos canônicos de aguada.css"
```

---

### Task 3: Gauge SVG reutilizável (`ha-ui.js`)

**Files:**
- Create: `frontend/assets/ha-ui.js`

- [ ] **Step 1: Criar `frontend/assets/ha-ui.js`**

```javascript
// Aguada — HA UI utils. Gauge radial estilo Home Assistant (arco 270°) com bandas de severidade.
(function (global) {
  const NS = 'http://www.w3.org/2000/svg';

  function polar(cx, cy, r, deg) {
    const rad = (deg - 90) * Math.PI / 180;
    return [cx + r * Math.cos(rad), cy + r * Math.sin(rad)];
  }
  function arcPath(cx, cy, r, startDeg, endDeg) {
    const [x1, y1] = polar(cx, cy, r, startDeg);
    const [x2, y2] = polar(cx, cy, r, endDeg);
    const large = (endDeg - startDeg) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}`;
  }
  // severity: thresholds em % { green, yellow, red } — abaixo de red=vermelho, abaixo de yellow=amarelo, senão verde
  function colorFor(pct, severity) {
    if (!severity) return 'var(--blue)';
    if (pct <= severity.red) return 'var(--red)';
    if (pct <= severity.yellow) return 'var(--yellow)';
    return 'var(--green)';
  }

  function renderGauge(el, opts) {
    if (!el) return;
    const o = opts || {};
    const value = Number(o.value) || 0;
    const min = o.min != null ? o.min : 0;
    const max = o.max != null ? o.max : 100;
    const unit = o.unit || '';
    const severity = o.severity || null;
    const size = o.size || 120;
    const cx = size / 2, cy = size / 2, r = size / 2 - 10;
    const START = -135, SWEEP = 270;
    const frac = Math.max(0, Math.min(1, (value - min) / (max - min || 1)));
    const endDeg = START + SWEEP * frac;
    const pct = ((value - min) / (max - min || 1)) * 100;

    el.classList.add('ha-gauge');
    el.innerHTML = '';

    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', `0 0 ${size} ${size * 0.72}`);
    svg.setAttribute('width', size);

    const track = document.createElementNS(NS, 'path');
    track.setAttribute('d', arcPath(cx, cy, r, START, START + SWEEP));
    track.setAttribute('fill', 'none');
    track.setAttribute('stroke', 'var(--bg3)');
    track.setAttribute('stroke-width', '10');
    track.setAttribute('stroke-linecap', 'round');
    svg.appendChild(track);

    if (frac > 0) {
      const val = document.createElementNS(NS, 'path');
      val.setAttribute('d', arcPath(cx, cy, r, START, endDeg));
      val.setAttribute('fill', 'none');
      val.setAttribute('stroke', colorFor(pct, severity));
      val.setAttribute('stroke-width', '10');
      val.setAttribute('stroke-linecap', 'round');
      svg.appendChild(val);
    }
    el.appendChild(svg);

    const label = document.createElement('div');
    label.className = 'ha-gauge-value';
    label.textContent = Math.round(value) + (unit ? ' ' + unit : '');
    el.appendChild(label);
  }

  global.renderGauge = renderGauge;
})(window);
```

- [ ] **Step 2: Verificar o gauge no demo (claro e escuro)**

`_kit-demo.html` já inclui `ha-ui.js` e chama `renderGauge` com value 85, severity {40,20,10}.
Abrir `http://127.0.0.1:8001/_kit-demo.html`, screenshot claro e escuro.
Esperado: arco 270° com track cinza e arco verde (85% > 40), número "85 %" centralizado. Trocar mentalmente value→15 deveria dar vermelho (validar mudando o value no console se desejar).

- [ ] **Step 3: Commit**

```bash
git add frontend/assets/ha-ui.js
git commit -m "feat(js): renderGauge — gauge SVG 270° com bandas de severidade"
```

---

### Task 4: Migrar `painel.html` (referência → forma HA)

**Files:**
- Modify: `frontend/painel.html`

- [ ] **Step 1: Ler a página inteira** (`frontend/painel.html`, 1649 linhas) para mapear os blocos `<style>` internos e a marcação.

- [ ] **Step 2: Aplicar forma HA aos blocos existentes**

- Hero strip: converter os `.hero-kpi` para `.ha-stat` (label/value/unit/delta), mantendo os bindings Alpine existentes (`volumeTotal`, `aporte`, `consumo`, `retencao`, alertas). Acrescentar **um gauge de sistema** ao lado: incluir `<script src="assets/ha-ui.js"></script>` e, no `init()`, chamar `renderGauge(<el>, {value: avgPct, min:0, max:100, unit:'%', severity:{green:40,yellow:20,red:10}})` (re-render quando os dados atualizarem via WS).
- `.cell` (linha 104-105): `border-radius` 12px; aplicar `box-shadow: var(--card-shadow)`.
- `.tank-card` (linha 149+): já é 12px; envolver no vocabulário `.ha-card` mantendo o `.tank-water`/`.tank-content`; confirmar sombra suave no hover via tokens (sem hex novos).
- Não trocar a lógica Alpine nem os data bindings, só a marcação/classes de apresentação. Espaçamento das grids `dash-grid`/`tanks-grid` mín. 12px.
- Trocar qualquer hex fixo encontrado nos `<style>` por token equivalente.

- [ ] **Step 3: Verificar (claro e escuro)**

Abrir `http://127.0.0.1:8001/painel.html`, screenshot claro e escuro.
Esperado: cards mais arredondados/respirados, idênticos em comportamento; dados de fallback aparecem; dark e claro corretos; mapa Leaflet intacto.

- [ ] **Step 4: Commit**

```bash
git add frontend/painel.html
git commit -m "style(painel): forma HA — rounding 12px, sombra suave, espaçamento"
```

---

### Task 5: Migrar `alerts.html`

**Files:**
- Modify: `frontend/alerts.html` (141 linhas — bloco `<style>` 10-27, marcação 32-46, render JS 103-115)

- [ ] **Step 1: Remover o `<style>` interno (linhas 10-27)** e substituir as classes na marcação e no JS conforme a tabela de mapeamento:
  - `.box`/`.box-header`/`h2`/`.box-body` → `.ha-card`/`.ha-card-header`/`.ha-card-title`/`.ha-card-body`.
  - Itens de alerta: substituir `.alert-item.alert-{crit,warn,info,ok}` por um card de notificação com borda à esquerda usando tokens. Adicionar ao `aguada.css` (HA layer) um bloco de notificação:

```css
.ha-alert { border-left: 4px solid; border-radius: 8px; padding: 11px 14px; margin-bottom: 10px; font-size: 13px; background: var(--bg2); }
.ha-alert strong { display: block; margin-bottom: 3px; }
.ha-alert-crit { border-color: var(--red);    background: var(--red-dim); }
.ha-alert-warn { border-color: var(--yellow); background: var(--yellow-dim); }
.ha-alert-info { border-color: var(--blue);   background: var(--blue-dim); }
.ha-alert-ok   { border-color: var(--green);  background: var(--green-dim); }
.ha-alert-meta { font-size: 10px; opacity: .7; margin-top: 4px; }
```

  - No JS `render()` (linha 103-108): trocar `alert-item alert-${a.level}` por `ha-alert ha-alert-${a.level}` e `.alert-meta` por `.ha-alert-meta`.
  - Resumo (`#summary`, linha 110-115): trocar `.sum-row` por `.ha-entity-row` dentro de um `.ha-entities`; `.abadge*` → `.badge .badge-{red,yellow,green,blue}`.
  - Título "🚨 Alertas Ativos"/"📊 Resumo": emoji → SVG (triângulo de aviso / gráfico) dentro de `.ha-card-title`.

- [ ] **Step 2: Verificar (claro e escuro)**

Abrir `http://127.0.0.1:8001/alerts.html`, screenshot claro e escuro.
Esperado: alertas como cards de notificação com cor por severidade via token (corretos no dark); resumo em lista de entidades; sem emoji.

- [ ] **Step 3: Commit**

```bash
git add frontend/alerts.html frontend/assets/aguada.css
git commit -m "style(alerts): cards HA + tokens (conserta dark), remove style interno"
```

---

### Task 6: Migrar `qualidade.html`

**Files:**
- Modify: `frontend/qualidade.html` (83 linhas)

- [ ] **Step 1: Aplicar mapeamento**
  - `.tab-bar`/`.tab-btn` (linhas 18-21): manter — já estilizado em style.css; ok.
  - `.page-box` (24, 48) → `.ha-card`+`.ha-card-body`.
  - `.page-title` (25, 49) → `.ha-card-header` com `.ha-card-title` + botão "+ Nova Análise" como `.btn .btn-primary`.
  - `.param-grid`/`.param-card`(`.lbl`/`.val`/`.norma`) (30-35, 54-58) → `.ha-stat-grid`/`.ha-stat`(`.ha-stat-label`/`.ha-stat-value`/`.ha-stat-delta`). `✓ Normal`/`⚠ Atenção` → `.ha-stat-delta` (verde/amarelo via classe `.up`/sem classe + cor amarela inline-token), trocando emoji ✓/⚠ por SVG check/triângulo.
  - `<table>` cru → `class="table"`.
  - Emoji 💧/🏭 nas abas: opcional manter (são labels de aba, não título de card); preferir SVG gota/indústria — se não houver SVG de indústria no painel, manter o emoji da aba.
  - `var(--success-green)` (41,42,65) → `var(--green)`; `var(--font-sm)`/`var(--text-muted)` continuam válidos (agora aliases).

- [ ] **Step 2: Verificar (claro e escuro)**

Abrir `http://127.0.0.1:8001/qualidade.html`, screenshot claro e escuro, alternar abas Água/Esgoto.
Esperado: indicadores como `.ha-stat`; tabelas no estilo `.table`; abas funcionam; dark correto.

- [ ] **Step 3: Commit**

```bash
git add frontend/qualidade.html
git commit -m "style(qualidade): ha-stat + ha-card + table, remove emoji de título"
```

---

### Task 7: Migrar `ete.html`

**Files:**
- Modify: `frontend/ete.html` (162 linhas)

- [ ] **Step 1: Ler `frontend/ete.html`** e mapear (esperado: `.page-box`/`.page-title`/`.param-card`/`.box`).

- [ ] **Step 2: Aplicar a tabela de mapeamento** (page-box→ha-card, param-card→ha-stat, box→ha-card, table cru→`.table`, badges→`.badge-*`, emoji→SVG, hex→token).

- [ ] **Step 3: Verificar (claro e escuro)** — `http://127.0.0.1:8001/ete.html`, screenshot claro e escuro.

- [ ] **Step 4: Commit**

```bash
git add frontend/ete.html
git commit -m "style(ete): migra para componentes HA + tokens"
```

---

### Task 8: Migrar `manutencao.html`

**Files:**
- Modify: `frontend/manutencao.html` (322 linhas; usa `.maint-item`/`.checklist`/`.sys-card`/`.frow` — ver overrides dark em style.css:283-292)

- [ ] **Step 1: Ler `frontend/manutencao.html`** e mapear classes legadas (`.box`, `.page-box`, `.maint-*`, `.sys-card`, `.frow`, `.checklist`).

- [ ] **Step 2: Aplicar mapeamento**
  - `.box`/`.page-box` → `.ha-card`.
  - `.frow` (linha rótulo→valor) → `.ha-entity-row` dentro de `.ha-entities`.
  - `.maint-item`/`.sys-card`: envolver em `.ha-card`; manter classes específicas só para o conteúdo interno que não tem equivalente.
  - tabelas cruas → `.table`; badges → `.badge-*`; emoji→SVG; hex→token.

- [ ] **Step 3: Verificar (claro e escuro)** — `http://127.0.0.1:8001/manutencao.html`, screenshot claro e escuro.

- [ ] **Step 4: Commit**

```bash
git add frontend/manutencao.html
git commit -m "style(manutencao): migra para componentes HA + tokens"
```

---

### Task 9: Migrar `dados.html`

**Files:**
- Modify: `frontend/dados.html` (422 linhas; usa Chart.js)

- [ ] **Step 1: Ler `frontend/dados.html`** e mapear (esperado: `.box`/`.kpi-card`/`.chart-wrap`/`.tbl-wrap` + `.tab-bar`).

- [ ] **Step 2: Aplicar mapeamento**
  - Wrappers de gráfico/KPI/tabela → `.ha-card` (header `.ha-card-title`, corpo `.ha-card-body`). **Não** alterar a config do Chart.js nem os `<canvas>`.
  - KPIs → `.ha-stat`; tabelas → `.table`; `.tab-bar` mantém.
  - hex→token; emoji→SVG.

- [ ] **Step 3: Verificar (claro e escuro)** — `http://127.0.0.1:8001/dados.html`, screenshot claro e escuro; confirmar que os gráficos Chart.js renderizam nos dois temas.

- [ ] **Step 4: Commit**

```bash
git add frontend/dados.html
git commit -m "style(dados): cards HA ao redor dos gráficos/KPIs + tokens"
```

---

### Task 10: Migrar `relatorio_tabelas.html`

**Files:**
- Modify: `frontend/relatorio_tabelas.html` (1409 linhas)

- [ ] **Step 1: Ler `frontend/relatorio_tabelas.html`** e inventariar classes legadas e hex (34 ocorrências de hex/token-legado, 8 de classe legada).

- [ ] **Step 2: Aplicar mapeamento** seção por seção: wrappers → `.ha-card`; tabelas cruas → `.table`; KPIs → `.ha-stat`; badges → `.badge-*`; botões → `.btn .btn-primary`/`.btn-secondary`; emoji→SVG; hex→token. Não alterar lógica de geração/dados.

- [ ] **Step 3: Verificar (claro e escuro)** — `http://127.0.0.1:8001/relatorio_tabelas.html`, screenshot claro e escuro; conferir que as tabelas de relatório seguem legíveis e densas.

- [ ] **Step 4: Commit**

```bash
git add frontend/relatorio_tabelas.html
git commit -m "style(relatorio): componentes HA + tokens"
```

---

### Task 11: Migrar `documentacao.html`

**Files:**
- Modify: `frontend/documentacao.html` (482 linhas)

- [ ] **Step 1: Ler `frontend/documentacao.html`** e mapear classes legadas (esperado: `.box`/`.page-box`/`.card`).

- [ ] **Step 2: Aplicar mapeamento** (box/page-box→ha-card; tabelas→`.table`; badges→`.badge-*`; emoji→SVG; hex→token).

- [ ] **Step 3: Verificar (claro e escuro)** — `http://127.0.0.1:8001/documentacao.html`, screenshot claro e escuro.

- [ ] **Step 4: Commit**

```bash
git add frontend/documentacao.html
git commit -m "style(documentacao): componentes HA + tokens"
```

---

### Task 12: SCADA — só unificação de token (sem mudar o esquemático)

**Files:**
- Modify: `frontend/scada.html` (2689 linhas; 58 ocorrências de hex/token-legado)

- [ ] **Step 1: Inventariar** em `frontend/scada.html` os hex fixos e tokens legados que não usam as variáveis `--scada-*` de `aguada.css`.

- [ ] **Step 2: Substituir hex fixos por tokens** existentes (`--scada-*`, ou `--blue`/`--red`/`--green`/`--text*`/`--border*`). **NÃO** alterar a topologia, SVGs de tubulação, posicionamento, nem a estrutura do diagrama ISA-101. Apenas garantir que cor venha de token para o dark ficar consistente.

- [ ] **Step 3: Verificar (claro e escuro)** — `http://127.0.0.1:8001/scada.html`, screenshot claro e escuro; o esquemático deve estar visualmente idêntico em estrutura, só com cores coerentes por tema.

- [ ] **Step 4: Commit**

```bash
git add frontend/scada.html
git commit -m "style(scada): cores via token para consistência de tema (esquemático intacto)"
```

---

### Task 13: Limpeza — remover CSS legado morto

**Files:**
- Modify: `frontend/assets/style.css`
- Delete: `frontend/_kit-demo.html`

- [ ] **Step 1: Buscar uso remanescente de cada classe legada** antes de remover:

Para cada classe candidata (`.box`, `.page-box`, `.page-title`, `.param-card`, `.param-grid`, `.res-card*`, `.rc-*`, `.btn-upload`, `.sum-row`, `.abadge*`, `.badge-online/offline/warn/danger/ok`, `.alert-item`, `.maint-*`, `.sys-card`, `.frow`, `.checklist`), rodar busca no `frontend/`:

```bash
grep -rn "param-card" frontend/*.html
```

Remover de `style.css` (incluindo overrides `[data-theme="dark"]` correspondentes nas linhas 240-298) **somente** as classes sem nenhuma ocorrência restante nas páginas. Manter `.admin-header`/`.admin-nav`/`.admin-status`/`.admin-main`/`.status-dot`/`.loader` (infra de layout ainda usada).

- [ ] **Step 2: Remover o arquivo de demo**

```bash
rm frontend/_kit-demo.html
```

- [ ] **Step 3: Verificação final — todas as páginas, claro e escuro**

Abrir cada página (`painel, dados, alerts, qualidade, manutencao, relatorio_tabelas, ete, documentacao, scada`) em `http://127.0.0.1:8001/<página>` e screenshot claro+escuro. Esperado: nenhuma regressão visual, consistência de cards/headers/botões/badges/tipografia entre páginas, dark e claro corretos em todas.

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "chore(css): remove componentes legados mortos do style.css; remove demo"
```

---

## Notas de execução

- **Sem build step** para `aguada.css`/`style.css` (CSS à mão). `tailwind.css` é gerado à parte e não é tocado.
- Cache-busting: páginas referenciam `aguada.css?v=2`. Se o navegador cachear, forçar reload (Ctrl+F5) ou subir o `?v=`.
- Backend serve o frontend e tem fallback de dados (sensores offline) — suficiente para verificação visual.
- Páginas que usam gauge devem incluir `<script src="assets/ha-ui.js"></script>` (adicionar quando a página passar a chamar `renderGauge`; nas tasks acima só o painel/dados podem querer — incluir conforme necessidade real ao migrar).
