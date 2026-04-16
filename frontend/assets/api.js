/**
 * api.js — Camada de API para o backend AGUADA (FastAPI)
 * Funciona local sem internet. Usa URLs relativas ao origin atual.
 */

const aguadaAPI = (() => {
  // Quando servido pelo FastAPI (porta 8001) ou nginx (porta 80), usa origin relativo.
  // Quando aberto via file://, usa localhost:8001 como fallback.
  const BASE = location.protocol === 'file:' ? 'http://localhost:8001' : '';
  const WS_BASE = (() => {
    if (location.protocol === 'file:') return 'ws://localhost:8001';
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    return `${proto}://${location.host}`;
  })();

  async function _get(path) {
    const r = await fetch(BASE + path);
    if (!r.ok) throw new Error(`HTTP ${r.status} — ${path}`);
    return r.json();
  }

  return {
    BASE,
    WS_BASE,

    /** GET /api/reservoirs → [{alias, name, pct, volume_l, level_cm, ts, online, ...}] */
    getReservoirs() { return _get('/api/reservoirs'); },

    /** GET /api/history/{alias}?period=24h|7d|30d → [{ts, level_cm, volume_l, pct, rssi}] */
    getHistory(alias, period = '24h') { return _get(`/api/history/${alias}?period=${period}`); },

    /** GET /api/consumption?alias=X&date=YYYY-MM-DD → {summary, events} */
    getConsumption(alias, date) { return _get(`/api/consumption?alias=${alias}&date=${date}`); },

    /** GET /api/gateway → {connected, port, mac, fw, sim_mode, last_seen} */
    getGateway() { return _get('/api/gateway'); },

    /** GET /api/nodes → [{node_id, alias, name, online, rssi, ...}] */
    getNodes() { return _get('/api/nodes'); },

    /** GET /api/equip/current → equipment state */
    getEquipCurrent() { return _get('/api/equip/current'); },

    getManualHydrometers(limit = 200) { return _get(`/api/manual/hydrometers?limit=${limit}`); },
    getManualPumps(limit = 200) { return _get(`/api/manual/pumps?limit=${limit}`); },
    getManualValves(limit = 200) { return _get(`/api/manual/valves?limit=${limit}`); },

    /**
     * Conecta ao WebSocket /ws com reconexão automática.
     * onMessage recebe o objeto já parseado.
     * Retorna função para desconectar.
     */
    connectWS(onMessage) {
      let ws, dead = false;

      function connect() {
        if (dead) return;
        try {
          ws = new WebSocket(`${WS_BASE}/ws`);
          ws.onmessage = e => { try { onMessage(JSON.parse(e.data)); } catch {} };
          ws.onclose = () => { if (!dead) setTimeout(connect, 5000); };
          ws.onerror = () => ws.close();
        } catch {}
      }

      connect();
      return () => { dead = true; ws && ws.close(); };
    },

    /** Hoje no formato YYYY-MM-DD (horário local) */
    today() {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`;
    },

    /** Formata timestamp unix em string legível */
    fmtTs(ts) {
      if (!ts) return '—';
      return new Date(ts * 1000).toLocaleString('pt-BR', {day:'2-digit',month:'2-digit',year:'2-digit',hour:'2-digit',minute:'2-digit'});
    },

    /** Cor de status baseada em pct */
    pctColor(pct) {
      if (pct == null) return '#6b7280';
      if (pct <= 20) return '#ef4444';
      if (pct <= 35) return '#f59e0b';
      return '#10b981';
    },

    /** Classe CSS de gauge baseada em pct */
    gaugeClass(pct) {
      if (pct == null) return 'gauge-warn';
      if (pct <= 20) return 'gauge-crit';
      if (pct <= 35) return 'gauge-warn';
      return 'gauge-ok';
    },

    /** Classe CSS de texto baseada em pct */
    textClass(pct) {
      if (pct == null) return '';
      if (pct <= 20) return 'text-crit';
      if (pct <= 35) return 'text-warn';
      return 'text-ok';
    },

    /**
     * Ordena reservatórios na ordem padrão: CON → CAV → CIE → CB3 → CBIF
     * Aliases desconhecidos vão ao final, ordenados alfabeticamente.
     */
    sortReservoirs(data) {
      const ORDER = ['CON', 'CAV', 'CIE1', 'CIE2', 'CB31', 'CB32', 'CBIF1', 'CBIF2'];
      return [...data].sort((a, b) => {
        const ia = ORDER.indexOf(a.alias);
        const ib = ORDER.indexOf(b.alias);
        if (ia === -1 && ib === -1) return a.alias.localeCompare(b.alias);
        if (ia === -1) return 1;
        if (ib === -1) return -1;
        return ia - ib;
      });
    },

    /**
     * Gera o HTML do admin-header com o link ativo marcado.
     * Uso: document.getElementById('topbar').innerHTML = aguadaAPI.navHTML('dados.html');
     */
    navHTML(active) {
      const links = [
        ['painel.html',   'Painel'],
        ['scada.html',    'SCADA'],
        ['dados.html',    'Dados'],
        ['report.html',   'Relatório'],
        ['alerts.html',   'Alertas'],
        ['manutencao.html','Manutenção'],
        ['qualidade.html','Qualidade'],
        ['ete.html',      'Esgoto'],
        ['documentacao.html','Documentação']
      ];
      const navItems = links.map(([href, label]) =>
        `<a href="${href}"${href === active ? ' class="active"' : ''}>${label}</a>`
      ).join('');
      return `
        <span class="admin-header-brand">💧 AGUADA</span>
        <nav class="admin-nav">${navItems}</nav>
        <div class="admin-status">
          <div class="status-dot" id="statusDot"></div>
          <span id="statusText">Conectando...</span>
        </div>`;
    },
  };
})();
