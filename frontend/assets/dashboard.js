/**
 * dashboard.js — página Análise (níveis, volume e consumo).
 * Monta em <main id="dash">. Dados: window.DASH_DATA (HTML autocontido gerado por
 * tools/build_dashboard.py) ou GET /api/dashboard. Requer Chart.js.
 */
(() => {
  const root = document.getElementById('dash');
  const STANDALONE = !!window.DASH_DATA;

  root.innerHTML = `
  <header class="d-top">
    <div><h1>Análise — níveis e consumo</h1><p class="d-sub" id="dSubtitle">Carregando dados…</p></div>
    ${STANDALONE ? `<button class="d-theme-btn" id="dThemeBtn" type="button" aria-label="Alternar tema claro/escuro" title="Alternar tema">
      <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg></button>` : ''}
  </header>
  <div id="dState"></div>
  <section class="d-filters" aria-label="Filtros">
    <div class="d-fgroup"><span id="lblPeriod">Período</span><div class="d-seg" id="presets" role="group" aria-labelledby="lblPeriod"></div></div>
    <div class="d-fgroup"><span>Intervalo</span>
      <div class="d-dates"><input type="date" id="dFrom" aria-label="Data inicial"><span aria-hidden="true">–</span><input type="date" id="dTo" aria-label="Data final"></div>
    </div>
    <div class="d-fgroup"><span id="lblUnit">Unidade</span><div class="d-seg" id="unitSeg" role="group" aria-labelledby="lblUnit">
      <button type="button" data-unit="pct">%</button><button type="button" data-unit="m3">m³</button></div></div>
    <div class="d-fgroup"><label for="selRes">Reservatório</label><select id="selRes"><option value="">Todos</option></select></div>
  </section>
  <section class="d-kpis" aria-label="Indicadores">
    <div class="d-kpi"><div class="d-kpi-label" id="kLevelLbl">Nível médio</div><div class="d-kpi-value" id="kLevel">—</div><div class="d-kpi-note" id="kLevelNote"></div></div>
    <div class="d-kpi"><div class="d-kpi-label">Consumido</div><div class="d-kpi-value" id="kCons">—</div><div class="d-kpi-note" id="kConsNote"></div></div>
    <div class="d-kpi"><div class="d-kpi-label">Abastecido</div><div class="d-kpi-value" id="kSupp">—</div><div class="d-kpi-note" id="kBal"></div></div>
    <div class="d-kpi"><div class="d-kpi-label">Horas abaixo de 20%</div><div class="d-kpi-value" id="kCrit">—</div><div class="d-kpi-note" id="kCritNote"></div></div>
  </section>
  <section class="d-card">
    <h2 id="lvlTitle">Nível por reservatório</h2>
    <p class="d-sub"><span id="lvlSub"></span> Lacunas maiores que 6 h ficam sem linha; leitura isolada aparece como ponto.</p>
    <div class="d-legend"><span><i class="d-thr"></i><span id="thrLbl"></span></span></div>
    <div class="d-multiples" id="multiples"></div>
  </section>
  <div class="d-row2">
    <section class="d-card">
      <h2>Abastecimento e consumo por dia</h2>
      <p class="d-sub">m³ por dia com leitura. Abastecido acima do eixo, consumido abaixo.</p>
      <div class="d-legend"><span><i style="background:var(--s-supply)"></i>Abastecido</span><span><i style="background:var(--s-cons)"></i>Consumido</span></div>
      <div class="d-chart-box"><canvas id="cDaily" role="img" aria-label="Abastecimento e consumo diário em metros cúbicos; valores na tabela abaixo"></canvas></div>
    </section>
    <section class="d-card" id="byResCard">
      <h2>Consumido por reservatório</h2>
      <p class="d-sub">m³ no período</p>
      <div class="d-chart-box"><canvas id="cByRes" role="img" aria-label="Consumo por reservatório em metros cúbicos; valores na tabela abaixo"></canvas></div>
    </section>
  </div>
  <section class="d-card">
    <h2>Resumo diário</h2>
    <p class="d-sub">Nível e volume a partir das medianas horárias. Clique no cabeçalho para ordenar.</p>
    <div class="d-tbl-wrap"><table class="d-table" id="tbl"><thead><tr></tr></thead><tbody></tbody></table></div>
    <div class="d-pager"><span id="pgInfo"></span><span><button type="button" id="pgPrev">Anterior</button> <button type="button" id="pgNext">Próxima</button></span></div>
  </section>
  <p class="d-foot">Consumo e abastecimento: medianas horárias de volume com deadband de ruído (<code>backend/calc.py</code>, mesmo cálculo da API).
    Variação abaixo do ruído do sensor conta 0.</p>`;

  const $ = id => document.getElementById(id);
  const DAY = 86400000;
  const nf1 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 1 });
  const nf0 = new Intl.NumberFormat('pt-BR', { maximumFractionDigits: 0 });
  const fmtDay = iso => iso.slice(8, 10) + '/' + iso.slice(5, 7);
  const fmtTs = ms => { const d = new Date(ms); return `${String(d.getDate()).padStart(2, '0')}/${String(d.getMonth() + 1).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}h`; };
  const css = v => getComputedStyle(root).getPropertyValue(v).trim();
  const localMs = iso => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d).getTime(); };
  const el = (tag, props = {}, kids = []) => { const e = Object.assign(document.createElement(tag), props); kids.forEach(k => e.append(k)); return e; };
  const avg = a => a.reduce((x, y) => x + y, 0) / a.length;

  // ── tema: na página do app quem troca é o botão do header (api.js); aqui só re-renderiza
  let rerender = () => {};
  new MutationObserver(() => rerender()).observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
  if (STANDALONE) {
    try {
      const t = localStorage.getItem('aguada-theme');
      if (t === 'dark' || (!t && matchMedia('(prefers-color-scheme: dark)').matches)) document.documentElement.dataset.theme = 'dark';
    } catch {}
    $('dThemeBtn').onclick = () => {
      const dark = document.documentElement.dataset.theme !== 'dark';
      if (dark) document.documentElement.dataset.theme = 'dark'; else delete document.documentElement.dataset.theme;
      try { localStorage.setItem('aguada-theme', dark ? 'dark' : 'light'); } catch {}
    };
  }

  // ── plugins Chart.js: crosshair, limite crítico, valor na ponta da barra
  const crosshair = { id: 'crosshair', afterDatasetsDraw(c) {
    const a = c.tooltip?.getActiveElements?.(); if (!a?.length) return;
    const x = a[0].element.x, { top, bottom } = c.chartArea, g = c.ctx;
    g.save(); g.strokeStyle = css('--d-axis'); g.lineWidth = 1; g.beginPath(); g.moveTo(x, top); g.lineTo(x, bottom); g.stroke(); g.restore();
  } };
  const threshold = { id: 'threshold', beforeDatasetsDraw(c, _a, opts) {
    const y = c.scales.y.getPixelForValue(opts.value), { left, right } = c.chartArea, g = c.ctx;
    g.save(); g.strokeStyle = css('--critical'); g.lineWidth = 1.5; g.setLineDash([4, 3]);
    g.beginPath(); g.moveTo(left, y); g.lineTo(right, y); g.stroke(); g.restore();
  } };
  const tipLabels = { id: 'tipLabels', afterDatasetsDraw(c) {
    const g = c.ctx, meta = c.getDatasetMeta(0);
    g.save(); g.fillStyle = css('--text2'); g.font = `12px ${css('--sans') || 'system-ui'}`; g.textBaseline = 'middle';
    meta.data.forEach((bar, i) => g.fillText(nf1.format(c.data.datasets[0].data[i]), bar.x + 6, bar.y));
    g.restore();
  } };
  const baseOpts = () => ({
    responsive: true, maintainAspectRatio: false, animation: false,
    interaction: { mode: 'index', intersect: false },
    plugins: { legend: { display: false }, tooltip: {
      backgroundColor: css('--card'), borderColor: css('--border2'), borderWidth: 1,
      titleColor: css('--text2'), bodyColor: css('--text'), titleFont: { weight: '500' }, bodyFont: { weight: '600' },
      padding: 10, displayColors: true, boxWidth: 12, boxHeight: 2,
    } },
  });
  const axis = () => ({ grid: { color: css('--d-grid'), drawTicks: false }, border: { color: css('--d-axis') }, ticks: { color: css('--text3'), font: { size: 11 }, padding: 6 } });

  function start(DATA) {
    const RES = DATA.reservoirs;
    const NAME = Object.fromEntries(RES.map(r => [r.alias, r.name]));
    const CAP = Object.fromEntries(RES.map(r => [r.alias, r.cap_m3]));
    const days = [...new Set(DATA.daily.map(r => r.d))].sort();
    if (!days.length) { $('dSubtitle').textContent = 'Sem leituras no banco.'; root.classList.remove('is-loading'); return; }

    // períodos: blocos contínuos de dias com dados (lacuna > 7 dias separa)
    const clusters = [];
    days.forEach(d => {
      const last = clusters.at(-1);
      if (last && localMs(d) - localMs(last.to) <= 7 * DAY) last.to = d; else clusters.push({ from: d, to: d });
    });
    const PRESETS = [...clusters.map(c => ({ ...c, label: c.from === c.to ? fmtDay(c.from) : `${fmtDay(c.from)} – ${fmtDay(c.to)}` })),
                     ...(clusters.length > 1 ? [{ from: days[0], to: days.at(-1), label: 'Tudo' }] : [])];
    const main = clusters.reduce((a, c) => (localMs(c.to) - localMs(c.from) > localMs(a.to) - localMs(a.from) ? c : a), clusters[0]);
    const state = { from: main.from, to: main.to, res: '', unit: 'pct', sort: { key: 'd', dir: -1 }, page: 0 };
    const isPct = () => state.unit === 'pct';
    const val = p => isPct() ? p[1] : p[2];   // ponto horário [ts, pct, m³] na unidade escolhida

    $('dSubtitle').textContent =
      `${RES.length} reservatórios · dados de ${fmtDay(days[0])}/${days[0].slice(0, 4)} a ${fmtDay(days.at(-1))}/${days.at(-1).slice(0, 4)} · atualizado ${DATA.generated}`;

    const presetsEl = $('presets');
    PRESETS.forEach(p => presetsEl.append(el('button', { type: 'button', textContent: p.label, onclick: () => { state.from = p.from; state.to = p.to; update(); } })));
    const dFrom = $('dFrom'), dTo = $('dTo'), selRes = $('selRes'), unitSeg = $('unitSeg');
    [dFrom, dTo].forEach(i => { i.min = days[0]; i.max = days.at(-1); });
    dFrom.onchange = () => { if (dFrom.value) { state.from = dFrom.value; if (state.to < state.from) state.to = state.from; update(); } };
    dTo.onchange = () => { if (dTo.value) { state.to = dTo.value; if (state.from > state.to) state.from = state.to; update(); } };
    RES.forEach(r => selRes.append(el('option', { value: r.alias, textContent: `${r.name} (${r.alias})` })));
    selRes.onchange = () => { state.res = selRes.value; update(); };
    unitSeg.querySelectorAll('button').forEach(b => b.onclick = () => { state.unit = b.dataset.unit; update(); });

    const slice = () => {
      const t0 = localMs(state.from), t1 = localMs(state.to) + DAY;
      const aliases = state.res ? [state.res] : RES.map(r => r.alias);
      const daily = DATA.daily.filter(r => r.d >= state.from && r.d <= state.to && aliases.includes(r.a));
      const hourly = Object.fromEntries(aliases.map(a => [a, (DATA.hourly[a] || []).filter(p => p[0] >= t0 && p[0] < t1)]));
      return { t0, t1, aliases, daily, hourly };
    };

    const charts = [];
    function update() {
      charts.splice(0).forEach(c => c.destroy());
      presetsEl.querySelectorAll('button').forEach((b, i) => b.setAttribute('aria-pressed', String(PRESETS[i].from === state.from && PRESETS[i].to === state.to)));
      unitSeg.querySelectorAll('button').forEach(b => b.setAttribute('aria-pressed', String(b.dataset.unit === state.unit)));
      dFrom.value = state.from; dTo.value = state.to; selRes.value = state.res;
      $('lvlTitle').textContent = isPct() ? 'Nível por reservatório' : 'Volume por reservatório';
      $('kLevelLbl').textContent = isPct() ? 'Nível médio' : 'Volume médio armazenado';
      $('lvlSub').textContent = isPct() ? 'Mediana horária do nível (%).'
        : 'Mediana horária do volume (m³); o eixo de cada gráfico vai até a capacidade do reservatório.';
      $('thrLbl').textContent = isPct() ? 'Limite crítico 20%' : 'Limite crítico (20% da capacidade)';
      state.page = 0;
      const s = slice();
      renderKpis(s); renderMultiples(s); renderDaily(s); renderByRes(s); renderTable(s);
    }
    rerender = update;

    function renderKpis(s) {
      const pts = Object.values(s.hourly).flat();
      const cons = s.daily.reduce((a, r) => a + r.c, 0), supp = s.daily.reduce((a, r) => a + r.s, 0);
      const crit = pts.filter(p => p[1] < 20).length;
      const nDays = new Set(s.daily.map(r => r.d)).size;
      const set = (id, v, unit) => { const e = $(id); e.textContent = v; if (unit) e.append(el('small', { textContent: unit })); };
      if (isPct()) {
        set('kLevel', pts.length ? nf0.format(avg(pts.map(p => p[1]))) : '—', pts.length ? '%' : '');
        $('kLevelNote').textContent = 'média das medianas horárias';
      } else {
        // soma, por reservatório, do volume médio no período
        const withVol = s.aliases.filter(a => s.hourly[a].some(p => p[2] != null));
        const vol = withVol.reduce((t, a) => t + avg(s.hourly[a].filter(p => p[2] != null).map(p => p[2])), 0);
        set('kLevel', withVol.length ? nf1.format(vol) : '—', withVol.length ? 'm³' : '');
        $('kLevelNote').textContent = `de ${nf0.format(withVol.reduce((t, a) => t + (CAP[a] || 0), 0))} m³ de capacidade`;
      }
      set('kCons', nf1.format(cons), 'm³');
      set('kSupp', nf1.format(supp), 'm³');
      set('kCrit', nf0.format(crit), 'h');
      $('kConsNote').textContent = `${nDays} ${nDays === 1 ? 'dia' : 'dias'} com leitura`;
      const bal = supp - cons;
      $('kBal').textContent = `saldo ${bal >= 0 ? '+' : '−'}${nf1.format(Math.abs(bal))} m³`;
      const note = $('kCritNote');
      note.replaceChildren();
      note.className = 'd-kpi-note' + (crit ? ' crit' : '');
      if (crit) {
        const who = s.aliases.filter(a => s.hourly[a].some(p => p[1] < 20));
        note.append(el('span', { innerHTML: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M12 9v4M12 17h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/></svg>' }),
                    el('span', { textContent: 'Crítico: ' + who.join(', ') }));
      } else note.textContent = 'nenhuma hora crítica';
    }

    function renderMultiples(s) {
      const box = $('multiples');
      box.replaceChildren();
      box.classList.toggle('single', s.aliases.length === 1);
      const color = css('--s-supply');
      s.aliases.forEach(a => {
        const pts = s.hourly[a].filter(p => val(p) != null), cap = CAP[a];
        const vs = pts.map(val);
        const stat = !pts.length ? 'sem dados' : isPct()
          ? `méd ${nf0.format(avg(vs))}% · mín ${nf0.format(Math.min(...vs))}%`
          : `méd ${nf0.format(avg(vs))} · mín ${nf0.format(Math.min(...vs))} de ${nf0.format(cap)} m³`;
        const canvas = el('canvas', { role: 'img' });
        canvas.setAttribute('aria-label', `${isPct() ? 'Nível' : 'Volume'} de ${NAME[a]}: ${stat}`);
        box.append(el('div', { className: 'd-mini' }, [
          el('div', { className: 'd-mini-hd' }, [el('div', { className: 'd-mini-name', textContent: NAME[a], title: NAME[a] }, [el('span', { textContent: a })]),
                                                el('div', { className: 'd-mini-stat', textContent: stat })]),
          pts.length ? el('div', { className: 'd-mini-box' }, [canvas]) : el('div', { className: 'd-empty', textContent: 'Sem leituras no período' }),
        ]));
        if (!pts.length) return;
        // quebra a linha em lacunas > 6 h (dados de comissionamento são esparsos)
        const data = [];
        pts.forEach((p, i) => { if (i && p[0] - pts[i - 1][0] > 6 * 3600000) data.push({ x: pts[i - 1][0] + 3600000, y: null }); data.push({ x: p[0], y: val(p), p: p[1], v: p[2] }); });
        const o = baseOpts();
        // tooltip sempre mostra as duas unidades
        o.plugins.tooltip.callbacks = { title: it => fmtTs(it[0].parsed.x), label: it => ` ${nf1.format(it.raw.p)}% · ${it.raw.v == null ? '—' : nf1.format(it.raw.v)} m³` };
        o.plugins.threshold = { value: isPct() ? 20 : cap * 0.2 };
        o.scales = {
          x: { ...axis(), type: 'linear', min: s.t0, max: s.t1, grid: { display: false }, ticks: { ...axis().ticks, maxTicksLimit: 5, callback: v => fmtTs(v).slice(0, 5) } },
          y: isPct()
            ? { ...axis(), min: 0, suggestedMax: 100, ticks: { ...axis().ticks, stepSize: 50, callback: v => v + '%' } }
            : { ...axis(), min: 0, suggestedMax: cap, ticks: { ...axis().ticks, stepSize: cap / 2, callback: v => nf0.format(v) } },
        };
        charts.push(new Chart(canvas, {
          type: 'line', plugins: [threshold, crosshair],
          data: { datasets: [{ data, borderColor: color, backgroundColor: color, fill: false, borderWidth: 2,
            // ponto sem vizinhos não desenha linha: mostra marcador
            pointRadius: c => (c.dataset.data[c.dataIndex - 1]?.y == null && c.dataset.data[c.dataIndex + 1]?.y == null) ? 2.5 : 0,
            pointHoverRadius: 4, pointHoverBorderWidth: 2, pointHoverBorderColor: css('--card'), tension: 0, spanGaps: false, borderJoinStyle: 'round', borderCapStyle: 'round' }] },
          options: o,
        }));
      });
    }

    function renderDaily(s) {
      const byDay = {};
      s.daily.forEach(r => { (byDay[r.d] ||= { c: 0, s: 0 }); byDay[r.d].c += r.c; byDay[r.d].s += r.s; });
      const keys = Object.keys(byDay).sort();
      const o = baseOpts();
      o.plugins.tooltip.callbacks = { title: it => fmtDay(keys[it[0].dataIndex]), label: it => ` ${it.dataset.label}: ${nf1.format(Math.abs(it.parsed.y))} m³` };
      o.scales = {
        x: { ...axis(), stacked: true, grid: { display: false }, ticks: { ...axis().ticks, autoSkip: true, maxRotation: 0 } },
        y: { ...axis(), stacked: true, grid: { color: c => c.tick.value === 0 ? css('--text3') : css('--d-grid') }, ticks: { ...axis().ticks, callback: v => nf0.format(Math.abs(v)) } },
      };
      const bar = { borderRadius: 4, borderSkipped: 'start', maxBarThickness: 24, categoryPercentage: .8, barPercentage: .9 };
      charts.push(new Chart($('cDaily'), {
        type: 'bar', plugins: [crosshair],
        data: { labels: keys.map(fmtDay), datasets: [
          { label: 'Abastecido', data: keys.map(k => byDay[k].s), backgroundColor: css('--s-supply'), ...bar },
          { label: 'Consumido', data: keys.map(k => -byDay[k].c), backgroundColor: css('--s-cons'), ...bar },
        ] },
        options: o,
      }));
    }

    function renderByRes(s) {
      const card = $('byResCard');
      card.hidden = s.aliases.length === 1;   // um reservatório: o KPI já é o número
      if (card.hidden) return;
      const tot = Object.fromEntries(s.aliases.map(a => [a, 0]));
      s.daily.forEach(r => tot[r.a] += r.c);
      const rows = Object.entries(tot).sort((a, b) => b[1] - a[1]);
      const o = baseOpts();
      o.indexAxis = 'y';
      o.interaction = { mode: 'nearest', axis: 'y', intersect: false };
      o.layout = { padding: { right: 44 } };
      o.plugins.tooltip.callbacks = { title: it => NAME[rows[it[0].dataIndex][0]], label: it => ` ${nf1.format(it.parsed.x)} m³` };
      o.scales = {
        x: { ...axis(), beginAtZero: true, ticks: { ...axis().ticks, maxTicksLimit: 5, callback: v => nf0.format(v) } },
        y: { ...axis(), grid: { display: false } },
      };
      charts.push(new Chart($('cByRes'), {
        type: 'bar', plugins: [tipLabels],
        data: { labels: rows.map(r => r[0]), datasets: [{ label: 'Consumido', data: rows.map(r => r[1]), backgroundColor: css('--s-cons'), borderRadius: 4, borderSkipped: 'start', maxBarThickness: 18 }] },
        options: o,
      }));
    }

    const COLS = [
      { key: 'd', label: 'Data', fmt: r => fmtDay(r.d) + '/' + r.d.slice(2, 4) },
      { key: 'a', label: 'Reservatório', get: r => NAME[r.a], fmt: r => `${NAME[r.a]} (${r.a})` },
      { key: 'n', label: 'Leituras', num: true, fmt: r => nf0.format(r.n) },
      ...[['min', 'mín'], ['avg', 'méd'], ['max', 'máx']].map(([k, l]) => ({
        key: k, num: true, label: () => isPct() ? `Nível ${l}` : `Volume ${l} (m³)`,
        get: r => r[(isPct() ? 'p' : 'v') + k],
        fmt: r => { const v = r[(isPct() ? 'p' : 'v') + k]; return v == null ? '—' : isPct() ? nf1.format(v) + '%' : nf1.format(v); },
      })),
      { key: 'c', label: 'Consumido (m³)', num: true, fmt: r => nf1.format(r.c) },
      { key: 's', label: 'Abastecido (m³)', num: true, fmt: r => nf1.format(r.s) },
      { key: 'bal', label: 'Saldo (m³)', num: true, get: r => r.s - r.c, fmt: r => (r.s - r.c > 0 ? '+' : r.s - r.c < 0 ? '−' : '') + nf1.format(Math.abs(r.s - r.c)) },
    ];
    const PAGE = 25;
    let tblRows = [];
    function renderTable(s) {
      const { key, dir } = state.sort;
      const col = COLS.find(c => c.key === key);
      const get = r => col.get ? col.get(r) : r[key];
      tblRows = [...s.daily].sort((x, y) => {
        const a = get(x), b = get(y);
        if (a == null) return 1; if (b == null) return -1;
        return (a < b ? -1 : a > b ? 1 : 0) * dir || (x.d < y.d ? 1 : -1);
      });
      $('tbl').querySelector('thead tr').replaceChildren(...COLS.map((c, i) => {
        const th = el('th', { className: c.num ? 'num' : '' });
        th.setAttribute('aria-sort', key === c.key ? (dir > 0 ? 'ascending' : 'descending') : 'none');
        th.append(el('button', { type: 'button', textContent: (typeof c.label === 'function' ? c.label() : c.label) + (key === c.key ? (dir > 0 ? ' ▲' : ' ▼') : ''),
          onclick: () => { state.sort = { key: c.key, dir: key === c.key ? -dir : (c.num ? -1 : 1) }; state.page = 0; renderTable(slice()); $('tbl').querySelectorAll('th button')[i].focus(); } }));
        return th;
      }));
      renderPage();
    }
    function renderPage() {
      const start = state.page * PAGE, rows = tblRows.slice(start, start + PAGE);
      $('tbl').querySelector('tbody').replaceChildren(...(rows.length
        ? rows.map(r => el('tr', {}, COLS.map(c => el('td', { className: c.num ? 'num' : '', textContent: c.fmt(r) }))))
        : [el('tr', {}, [el('td', { colSpan: COLS.length, className: 'd-empty', textContent: 'Nenhum dia com leitura no período' })])]));
      $('pgInfo').textContent = tblRows.length ? `Mostrando ${start + 1}–${start + rows.length} de ${tblRows.length}` : '';
      $('pgPrev').disabled = state.page === 0;
      $('pgNext').disabled = start + PAGE >= tblRows.length;
    }
    $('pgPrev').onclick = () => { state.page--; renderPage(); };
    $('pgNext').onclick = () => { state.page++; renderPage(); };

    root.classList.remove('is-loading');
    update();
  }

  function load() {
    root.classList.add('is-loading');
    root.classList.remove('has-error');
    $('dState').replaceChildren();
    const base = location.protocol === 'file:' ? 'http://localhost:8001' : '';
    fetch(base + '/api/dashboard')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then(start)
      .catch(e => {
        root.classList.remove('is-loading');
        root.classList.add('has-error');
        $('dSubtitle').textContent = 'Dados indisponíveis';
        $('dState').replaceChildren(el('div', { className: 'd-state err', role: 'alert' }, [
          el('span', { textContent: `Não foi possível carregar a análise (${e.message}).` }),
          el('button', { type: 'button', className: 'btn btn-secondary', textContent: 'Tentar novamente', onclick: load }),
        ]));
      });
  }

  if (STANDALONE) start(window.DASH_DATA); else load();
})();
