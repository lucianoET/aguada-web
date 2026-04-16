/**
 * AGUADA UI Utilities
 * Loading states, toasts, skeletons e error handling
 */

/**
 * Loading Overlay
 */
const LoadingOverlay = {
  element: null,

  init() {
    if (this.element) return;

    this.element = document.createElement('div');
    this.element.className = 'loading-overlay';
    this.element.innerHTML = `
      <div class="loading-spinner"></div>
      <div class="loading-text">Carregando...</div>
    `;
    document.body.appendChild(this.element);
  },

  show(text = 'Carregando...') {
    this.init();
    this.element.querySelector('.loading-text').textContent = text;
    this.element.classList.add('active');
  },

  hide() {
    if (this.element) {
      this.element.classList.remove('active');
    }
  }
};

/**
 * Toast Notifications
 */
const Toast = {
  container: null,
  toasts: [],

  init() {
    if (this.container) return;

    this.container = document.createElement('div');
    this.container.className = 'toast-container';
    document.body.appendChild(this.container);
  },

  show(message, type = 'info', title = null, duration = 5000) {
    this.init();

    const icons = {
      success: '✅',
      error: '❌',
      warning: '⚠️',
      info: 'ℹ️'
    };

    const titles = {
      success: 'Sucesso',
      error: 'Erro',
      warning: 'Atenção',
      info: 'Informação'
    };

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <div class="toast-icon">${icons[type] || icons.info}</div>
      <div class="toast-content">
        ${title ? `<div class="toast-title">${title}</div>` : `<div class="toast-title">${titles[type] || titles.info}</div>`}
        <div class="toast-message">${message}</div>
      </div>
      <button class="toast-close" aria-label="Fechar">×</button>
    `;

    const closeBtn = toast.querySelector('.toast-close');
    closeBtn.addEventListener('click', () => this.remove(toast));

    this.container.appendChild(toast);
    this.toasts.push(toast);

    // Auto-remove após duração
    if (duration > 0) {
      setTimeout(() => this.remove(toast), duration);
    }

    return toast;
  },

  remove(toast) {
    toast.style.animation = 'toast-slide-in 0.3s ease reverse';
    setTimeout(() => {
      toast.remove();
      this.toasts = this.toasts.filter(t => t !== toast);
    }, 300);
  },

  success(message, title = null, duration = 5000) {
    return this.show(message, 'success', title, duration);
  },

  error(message, title = null, duration = 7000) {
    return this.show(message, 'error', title, duration);
  },

  warning(message, title = null, duration = 6000) {
    return this.show(message, 'warning', title, duration);
  },

  info(message, title = null, duration = 5000) {
    return this.show(message, 'info', title, duration);
  }
};

/**
 * Skeleton Loaders
 */
const Skeleton = {
  /**
   * Renderiza skeleton para dashboard
   */
  renderDashboard(container, count = 5) {
    if (!container) return;

    const html = Array(count).fill(0).map(() => `
      <div class="card card-skeleton">
        <div class="card-skeleton-header"></div>
        <div class="card-skeleton-body">
          <div class="skeleton skeleton-gauge"></div>
          <div class="skeleton-data-row">
            <div class="skeleton skeleton-data-item"></div>
            <div class="skeleton skeleton-data-item"></div>
          </div>
          <div class="skeleton-data-row">
            <div class="skeleton skeleton-data-item"></div>
            <div class="skeleton skeleton-data-item"></div>
          </div>
          <div class="skeleton skeleton-text" style="width: 60%; margin-top: 15px;"></div>
        </div>
      </div>
    `).join('');

    container.innerHTML = html;
  },

  /**
   * Renderiza skeleton para tabela
   */
  renderTable(container, rows = 10, cols = 5) {
    if (!container) return;

    const html = `
      <div class="table-skeleton">
        ${Array(rows).fill(0).map(() => `
          <div class="table-skeleton-row">
            ${Array(cols).fill(0).map(() => `
              <div class="skeleton table-skeleton-cell"></div>
            `).join('')}
          </div>
        `).join('')}
      </div>
    `;

    container.innerHTML = html;
  },

  /**
   * Renderiza skeleton para mapa
   */
  renderMap(container) {
    if (!container) return;

    container.innerHTML = `
      <div class="map-skeleton">
        <div class="loading-text">Carregando mapa...</div>
      </div>
    `;
  }
};

/**
 * Error States
 */
const ErrorState = {
  /**
   * Renderiza estado de erro
   */
  render(container, options = {}) {
    if (!container) return;

    const {
      icon = '⚠️',
      title = 'Erro ao carregar dados',
      message = 'Não foi possível conectar ao servidor. Verifique sua conexão e tente novamente.',
      actions = [
        { text: 'Tentar novamente', onClick: () => window.location.reload() }
      ]
    } = options;

    const actionsHtml = actions.map((action, index) => `
      <button class="btn-primary" data-action="${index}">${action.text}</button>
    `).join('');

    const html = `
      <div class="error-state">
        <div class="error-state-icon">${icon}</div>
        <div class="error-state-title">${title}</div>
        <div class="error-state-message">${message}</div>
        <div class="error-state-actions">
          ${actionsHtml}
        </div>
      </div>
    `;

    container.innerHTML = html;

    // Adicionar event listeners
    actions.forEach((action, index) => {
      const btn = container.querySelector(`[data-action="${index}"]`);
      if (btn && action.onClick) {
        btn.addEventListener('click', action.onClick);
      }
    });
  },

  /**
   * Renderiza estado offline
   */
  renderOffline(container, onRetry) {
    this.render(container, {
      icon: '📡',
      title: 'Sistema Offline',
      message: 'O servidor AGUADA está offline ou não pode ser alcançado. Verifique a conexão de rede.',
      actions: [
        { text: 'Tentar reconectar', onClick: onRetry || (() => window.location.reload()) },
        { text: 'Usar dados em cache', onClick: () => Toast.info('Modo offline ativado') }
      ]
    });
  },

  /**
   * Renderiza estado de sem dados
   */
  renderEmpty(container, options = {}) {
    if (!container) return;

    const {
      icon = '📭',
      title = 'Nenhum dado disponível',
      message = 'Não há dados para exibir no momento.'
    } = options;

    const html = `
      <div class="empty-state">
        <div class="empty-state-icon">${icon}</div>
        <div class="empty-state-title">${title}</div>
        <div class="empty-state-message">${message}</div>
      </div>
    `;

    container.innerHTML = html;
  }
};

/**
 * Progress Bar
 */
const ProgressBar = {
  /**
   * Cria progress bar determinada
   */
  create(container, progress = 0) {
    if (!container) return null;

    const bar = document.createElement('div');
    bar.className = 'progress-bar';
    bar.innerHTML = `<div class="progress-bar-fill" style="width: ${progress}%"></div>`;
    
    container.appendChild(bar);
    
    return {
      setProgress(value) {
        const fill = bar.querySelector('.progress-bar-fill');
        fill.style.width = `${Math.min(100, Math.max(0, value))}%`;
      },
      remove() {
        bar.remove();
      }
    };
  },

  /**
   * Cria progress bar indeterminada
   */
  createIndeterminate(container) {
    if (!container) return null;

    const bar = document.createElement('div');
    bar.className = 'progress-bar';
    bar.innerHTML = `<div class="progress-bar-indeterminate"></div>`;
    
    container.appendChild(bar);
    
    return {
      remove() {
        bar.remove();
      }
    };
  }
};

/**
 * Retry Logic Helper
 */
async function retryAsync(fn, retries = 3, delay = 1000) {
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (i === retries - 1) throw error;
      console.warn(`[Retry] Tentativa ${i + 1} falhou, tentando novamente em ${delay}ms...`);
      await new Promise(resolve => setTimeout(resolve, delay));
    }
  }
}

/**
 * Debounce Helper
 */
function debounce(func, wait = 300) {
  let timeout;
  return function executedFunction(...args) {
    const later = () => {
      clearTimeout(timeout);
      func(...args);
    };
    clearTimeout(timeout);
    timeout = setTimeout(later, wait);
  };
}

/**
 * Throttle Helper
 */
function throttle(func, limit = 300) {
  let inThrottle;
  return function(...args) {
    if (!inThrottle) {
      func.apply(this, args);
      inThrottle = true;
      setTimeout(() => inThrottle = false, limit);
    }
  };
}

// Exportar para window (global)
window.LoadingOverlay = LoadingOverlay;
window.Toast = Toast;
window.Skeleton = Skeleton;
window.ErrorState = ErrorState;
window.ProgressBar = ProgressBar;
window.retryAsync = retryAsync;
window.debounce = debounce;
window.throttle = throttle;
