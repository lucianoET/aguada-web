// shared.js — constantes, helpers e mixins comuns a todas as páginas
// Versão offline: sem referências a CDN

// Sincroniza o indicador de status do topbar unificado (navHTML)
function _syncTopbarStatus(online) {
  const dot = document.getElementById('statusDot');
  const txt = document.getElementById('statusText');
  if (dot) dot.className = 'status-dot ' + (online ? 'online' : 'offline');
  if (txt) txt.textContent = online ? 'Ao vivo' : 'Desconectado';
}

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

function normalizeWsMessage(message) {
  const type = message?.type;
  const envelopeData = message && typeof message === 'object' && 'data' in message ? message.data : message;

  if (type === 'snapshot') {
    return {
      type,
      reservoirs: Array.isArray(envelopeData)
        ? envelopeData
        : (Array.isArray(envelopeData?.reservoirs) ? envelopeData.reservoirs : []),
      gateway: message?.gateway ?? envelopeData?.gateway ?? null,
    };
  }

  if (type === 'reading') {
    const reading = envelopeData?.alias
      ? envelopeData
      : (message?.reading?.alias ? message.reading : null);
    return { type, reading };
  }

  return {
    type,
    payload: envelopeData,
    gateway: message?.gateway ?? envelopeData?.gateway ?? null,
  };
}

// ── Tema claro/escuro ──────────────────────────────────────────
function getTheme() {
  return localStorage.getItem('aguada-theme') || 'light';
}

function applyTheme(theme) {
  if (theme === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
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
      const isFile = location.protocol === 'file:';
      const proto = location.protocol === 'https:' ? 'wss' : 'ws';
      const host = location.host || 'localhost:8001';
      const url = `${proto}://${host}/ws`;
      this._ws = new WebSocket(url);
      this._ws.onopen  = () => { this.wsConnected = true;  _syncTopbarStatus(true); };
      this._ws.onclose = () => { this.wsConnected = false; _syncTopbarStatus(false); setTimeout(() => this.wsConnect(onMessage), 5000); };
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
      const reservoirs = Array.isArray(this.reservoirs) ? this.reservoirs : [];
      const r = reservoirs.find(r => r.alias === alias);
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
        else body.volume_l = val * 1000;
        const res = await fetch(aguadaAPI.BASE + '/api/readings/manual', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const json = await res.json();
        if (!res.ok) throw new Error(json.detail || 'Erro ao salvar');
        const reservoirs = Array.isArray(this.reservoirs) ? [...this.reservoirs] : [];
        const idx = reservoirs.findIndex(r => r.alias === this.modal.alias);
        const updated = { ...(reservoirs[idx] || {}), alias: json.alias, pct: json.pct, volume_l: json.volume_l, level_cm: json.level_cm, ts: Math.floor(Date.now() / 1000), online: true };
        if (idx >= 0) reservoirs[idx] = updated;
        else reservoirs.push(updated);
        this.reservoirs = reservoirs;
        this._fillModal(updated);
        this.modal.feedback = `Salvo: ${json.pct}% · ${(json.volume_l / 1000).toFixed(1)} m³`;
        this.modal.feedbackOk = true;
        this.modal.manualValue = '';
      } catch (e) {
        this.modal.feedback = e.message || 'Erro ao salvar';
        this.modal.feedbackOk = false;
      } finally {
        this.modal.saving = false;
      }
    },

    formatTs, timeAgo, rssiColor, statusColor,
  };
}
