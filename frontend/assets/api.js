/**
 * api.js — Camada de API para o backend AGUADA (FastAPI)
 * Funciona local sem internet. Usa URLs relativas ao origin atual.
 */

// Escrita sem sessão volta 401: manda para o login e retorna à página depois (Normas §12.4)
if (!window.__aguadaFetch) {
  window.__aguadaFetch = window.fetch.bind(window);
  window.fetch = async (input, init = {}) => {
    const res = await window.__aguadaFetch(input, init);
    const url = typeof input === 'string' ? input : input.url;
    const method = (init.method || (typeof input === 'string' ? 'GET' : input.method) || 'GET').toUpperCase();
    if (res.status === 401 && method !== 'GET' && url.includes('/api/') && !url.includes('/api/auth/')) {
      location.href = `login.html?next=${encodeURIComponent((location.pathname.split('/').pop() || 'painel.html') + location.search)}`;
    }
    return res;
  };
}

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

    /** GET /api/history/{alias}?period=24h|7d|30d&since_ts=&until_ts= → [{ts, level_cm, volume_l, pct, rssi}] */
    getHistory(alias, period = '24h', options = {}) {
      const params = new URLSearchParams();
      if (options.since_ts != null) params.set('since_ts', String(options.since_ts));
      if (options.until_ts != null) params.set('until_ts', String(options.until_ts));
      if (!params.has('since_ts')) params.set('period', period);
      return _get(`/api/history/${alias}?${params.toString()}`);
    },

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
     * Gera o HTML do admin-header com o link ativo marcado e o toggle de temas.
     * Uso: document.getElementById('topbar').innerHTML = aguadaAPI.navHTML('dados.html');
     */
    navHTML(active) {
      const links = [
        ['dashboard.html','Dashboard'],
        ['painel.html',   'Painel'],
        ['scada.html',    'SCADA'],
        ['planta.html',   'Planta'],
        ['dados.html',    'Dados'],
        ['analise.html',  'Análise'],
        ['indicadores.html', 'Indicadores'],
        ['relatorio_tabelas.html', 'Relatório'],
        ['alerts.html',   'Alertas'],
        ['manutencao.html','Manutenção'],
        ['qualidade.html','Qualidade'],
        ['rede.html?r=agua',     'Água'],
        ['rede.html?r=incendio', 'Incêndio'],
        ['ete.html',      'Esgoto'],
        ['documentacao.html','Documentação']
      ];
      const navItems = links.map(([href, label]) =>
        `<a href="${href}"${href === active ? ' class="active"' : ''}>${label}</a>`
      ).join('');
      // Páginas sem WebSocket/status próprio ficavam em "Buscando rede..." para sempre:
      // reflete /api/gateway. Páginas que atualizam o indicador prevalecem.
      setTimeout(async () => {
        const gw = await _get('/api/gateway').catch(() => null);
        const txt = document.getElementById('statusText');
        if (!txt || txt.textContent !== 'Buscando rede...') return;
        const ok = !!(gw?.connected || gw?.sim_mode);
        document.getElementById('statusDot').className = 'status-dot ' + (ok ? 'online' : 'offline');
        txt.textContent = ok ? 'Online' : 'Offline';
      }, 0);
      // Quem está logado (ou link para entrar); admin ganha atalho para Usuários
      setTimeout(async () => {
        const el = document.getElementById('navUser');
        if (!el) return;
        const me = await _get('/api/auth/me').catch(() => null);
        const next = encodeURIComponent((location.pathname.split('/').pop() || 'painel.html') + location.search);
        if (!me?.user) { el.innerHTML = `<a href="login.html?next=${next}">Entrar</a>`; return; }
        const u = me.user;
        el.innerHTML = `<span class="nav-user-name" title="${u.name} · ${u.role}">${u.name}</span>`
          + (u.role === 'admin' ? `<a href="users.html">Usuários</a>` : '')
          + `<button type="button" onclick="aguadaAPI.logout()">Sair</button>`;
      }, 0);
      // No celular a aba ativa pode ficar fora da área visível da nav
      setTimeout(() => document.querySelector('.admin-nav a.active')?.scrollIntoView({ inline: 'center', block: 'nearest' }), 0);
      return `
        <a href="painel.html" class="admin-header-brand" aria-label="AGUADA — Painel"><svg width="16" height="16" viewBox="0 0 24 24" fill="var(--cyan)" aria-hidden="true" style="margin-right:6px"><path d="M12 2.69l5.66 5.66a8 8 0 11-11.31 0z"/></svg><span class="brand-text">AGUADA</span></a>
        <nav class="admin-nav">${navItems}</nav>
        <div class="admin-status" style="display:flex; align-items:center; gap:16px;">
          <button onclick="aguadaAPI.toggleTheme()" title="Alternar Tema Claro/Escuro" aria-label="Alternar tema claro/escuro" style="color:var(--text); cursor:pointer; background:none; border:none; display:flex; align-items:center;">
             <svg width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z"></path></svg>
          </button>
          <div style="display:flex; align-items:center; gap:6px;">
             <svg width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M5 12.55a11 11 0 0114.08 0M1.42 9a16 16 0 0121.16 0M8.53 16.11a6 6 0 016.95 0"></path><line x1="12" y1="20" x2="12.01" y2="20"></line></svg>
             <div class="status-dot" id="statusDot" role="img" aria-label="Status da rede"></div>
             <span id="statusText">Buscando rede...</span>
          </div>
          <div class="nav-user" id="navUser"></div>
        </div>`;
    },

    async logout() {
      await fetch(BASE + '/api/auth/logout', { method: 'POST' }).catch(() => null);
      location.reload();
    },

    /** Usuário logado ou null (cache por página) */
    me() { return this._me ??= _get('/api/auth/me').then((r) => r.user).catch(() => null); },

    toggleTheme() {
      const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
      if (isDark) {
        document.documentElement.removeAttribute('data-theme');
        localStorage.setItem('aguada-theme', 'light');
      } else {
        document.documentElement.setAttribute('data-theme', 'dark');
        localStorage.setItem('aguada-theme', 'dark');
      }
    },

    initTheme() {
      const savedTheme = localStorage.getItem('aguada-theme') || 'light';
      if (savedTheme === 'dark') {
        document.documentElement.setAttribute('data-theme', 'dark');
      } else {
        document.documentElement.removeAttribute('data-theme');
      }
    }
  };
})();

// Auto-init fallback theme
aguadaAPI.initTheme();
