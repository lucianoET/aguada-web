/**
 * AGUADA API Service
 * Centraliza todas as chamadas HTTP ao backend
 */

class ApiService {
  constructor() {
    this.baseURL = this._getBaseURL();
    this.wsURL = this._getWebSocketURL();
    this.timeout = 10000; // 10s timeout
    this.retryAttempts = 3;
    this.retryDelay = 1000; // 1s
    this.ws = null;
    this.wsReconnectInterval = null;
    this.wsCallbacks = [];
    this.lastDataSource = 'network';
    this.dbPromise = null;

    this._initOfflineStore();
  }

  /**
   * Detecta URL base do backend
   */
  _getBaseURL() {
    const env = window.location.hostname;
    
    // Produção (Docker ou deploy)
    if (env === 'aguada.local') {
      return 'http://192.168.0.100:3000/api';
    }
    
    // Desenvolvimento local
    return 'http://localhost:3000/api';
  }

  /**
   * Detecta URL do WebSocket
   */
  _getWebSocketURL() {
    const env = window.location.hostname;
    
    if (env === 'aguada.local') {
      return 'ws://192.168.0.100:3000/ws';
    }
    
    return 'ws://localhost:3000/ws';
  }

  /**
   * Fetch com timeout e retry
   */
  async _fetchWithRetry(url, options = {}, attempt = 1) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), this.timeout);

    try {
      const response = await fetch(url, {
        ...options,
        signal: controller.signal,
        headers: {
          'Content-Type': 'application/json',
          ...options.headers,
        },
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    } catch (error) {
      clearTimeout(timeoutId);

      // Retry lógica
      if (attempt < this.retryAttempts) {
        console.warn(`[API] Tentativa ${attempt} falhou, tentando novamente em ${this.retryDelay}ms...`);
        await new Promise(resolve => setTimeout(resolve, this.retryDelay));
        return this._fetchWithRetry(url, options, attempt + 1);
      }

      console.error('[API] Erro após todas as tentativas:', error);
      throw error;
    }
  }

  /**
   * GET /api/readings/latest
   * Últimas leituras de todos os sensores
   */
  async getLatestReadings() {
    try {
      console.log('[API] Buscando leituras de:', `${this.baseURL}/readings/latest`);
      const data = await this._fetchWithRetry(`${this.baseURL}/readings/latest`);
      console.log('[API] Resposta recebida:', data);
      
      // Normalizar formato para o frontend
      const normalized = this._normalizeReadings(data.data);
      this.lastDataSource = 'network';
      console.log('[API] Dados normalizados:', normalized);
      return normalized;
    } catch (error) {
      console.error('[API] Erro ao buscar leituras:', error);
      
      // Fallback: retornar cache ou dados vazios
      const cached = await this._getCachedReadings();
      if (cached) {
        this.lastDataSource = 'offline-cache';
        console.warn('[API] Usando dados do cache offline');
        return cached;
      }
      
      return null;
    }
  }

  /**
   * GET /api/readings/history/:sensor_id
   * Histórico de leituras de um sensor
   */
  async getReadingHistory(sensorId, days = 7, variavel = null) {
    try {
      let url = `${this.baseURL}/readings/history/${sensorId}?days=${days}`;
      if (variavel) {
        url += `&variavel=${variavel}`;
      }

      const data = await this._fetchWithRetry(url);
      return data.data || [];
    } catch (error) {
      console.error(`[API] Erro ao buscar histórico de ${sensorId}:`, error);
      return [];
    }
  }

  /**
   * GET /api/sensors/status
   * Status de todos os sensores (online/offline)
   */
  async getSensorsStatus() {
    try {
      const data = await this._fetchWithRetry(`${this.baseURL}/sensors/status`);
      return data.data || [];
    } catch (error) {
      console.error('[API] Erro ao buscar status dos sensores:', error);
      return [];
    }
  }

  /**
   * GET /api/alerts
   * Lista de alertas com filtros opcionais
   */
  async getAlerts(filters = {}) {
    try {
      const params = new URLSearchParams(filters);
      const data = await this._fetchWithRetry(`${this.baseURL}/alerts?${params}`);
      return data.data || [];
    } catch (error) {
      console.error('[API] Erro ao buscar alertas:', error);
      return [];
    }
  }

  /**
   * GET /api/stats/daily
   * Estatísticas diárias
   */
  async getDailyStats() {
    try {
      const data = await this._fetchWithRetry(`${this.baseURL}/stats/daily`);
      return data.data || {};
    } catch (error) {
      console.error('[API] Erro ao buscar estatísticas:', error);
      return {};
    }
  }

  /**
   * GET /api/system/health
   * Health check do sistema
   */
  async getSystemHealth() {
    try {
      const data = await this._fetchWithRetry(`${this.baseURL}/system/health`);
      return data;
    } catch (error) {
      console.error('[API] Sistema offline:', error);
      return { status: 'offline' };
    }
  }

  /**
   * POST /api/telemetry
   * Enviar telemetria (usado para testes ou simulação)
   */
  async sendTelemetry(payload) {
    try {
      const data = await this._fetchWithRetry(`${this.baseURL}/telemetry`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      return data;
    } catch (error) {
      console.error('[API] Erro ao enviar telemetria:', error);
      throw error;
    }
  }

  /**
   * Normaliza formato de leituras para o frontend
   */
  _normalizeReadings(rawData) {
    if (!rawData) return {};

    const normalized = {};

    Object.entries(rawData).forEach(([sensorId, sensorData]) => {
      // Mapear sensor_id para elemento_id (RCON, RCAV, etc.)
      const elementoId = sensorData.elemento_id || this._mapSensorToElemento(sensorId);
      
      const variables = sensorData.variables || {};

      normalized[elementoId] = {
        sensor_id: sensorId,
        elemento_id: elementoId,
        mac_address: sensorData.mac_address,
        distance_cm: this._parseValue(variables.distance_cm?.valor, 0),
        valve_in: this._parseValue(variables.valve_in?.valor, 0),
        valve_out: this._parseValue(variables.valve_out?.valor, 0),
        sound_in: this._parseValue(variables.sound_in?.valor, 0),
        battery: this._parseValue(variables.battery?.valor, 5000),
        rssi: this._parseValue(variables.rssi?.valor, -50),
        timestamp: variables.distance_cm?.datetime || new Date().toISOString(),
      };
    });

    // Cache no localStorage
    this._cacheReadings(normalized);

    return normalized;
  }

  /**
   * Mapeia sensor_id para elemento_id
   */
  _mapSensorToElemento(sensorId) {
    const mapping = {
      'SEN_CON_01': 'RCON',
      'SEN_CAV_01': 'RCAV',
      'SEN_B03_01': 'RB03',
      'SEN_IE01_01': 'IE01',
      'SEN_IE02_01': 'IE02',
    };
    return mapping[sensorId] || sensorId;
  }

  /**
   * Parse valor com fallback
   */
  _parseValue(value, fallback = 0) {
    if (value === null || value === undefined) return fallback;
    const parsed = Number(value);
    return isNaN(parsed) ? fallback : parsed;
  }

  /**
   * Cache leituras no localStorage
   */
  _cacheReadings(readings) {
    this._saveOfflineReadings(readings).catch((error) => {
      console.warn('[Offline] Erro ao salvar em IndexedDB:', error);
    });

    this._setLocalCache(readings);
  }

  async _getCachedReadings() {
    const offline = await this._getOfflineReadings();
    if (offline) {
      return offline;
    }
    return this._getLocalCache();
  }

  _setLocalCache(readings) {
    try {
      localStorage.setItem('aguada_readings_cache', JSON.stringify({
        data: readings,
        timestamp: Date.now(),
      }));
    } catch (error) {
      console.warn('[Cache] Erro ao salvar cache:', error);
    }
  }

  _getLocalCache() {
    try {
      const cached = localStorage.getItem('aguada_readings_cache');
      if (!cached) return null;

      const { data, timestamp } = JSON.parse(cached);
      if (Date.now() - timestamp > 5 * 60 * 1000) {
        return null;
      }
      return data;
    } catch (error) {
      return null;
    }
  }

  _initOfflineStore() {
    if (typeof window === 'undefined' || !('indexedDB' in window)) {
      console.warn('[Offline] IndexedDB não suportado neste navegador');
      return;
    }

    this.dbPromise = new Promise((resolve, reject) => {
      const request = indexedDB.open('aguada_offline', 1);

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        if (!db.objectStoreNames.contains('latest_readings')) {
          db.createObjectStore('latest_readings', { keyPath: 'id' });
        }
      };

      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    }).catch((error) => {
      console.warn('[Offline] Falha ao iniciar IndexedDB:', error);
      return null;
    });
  }

  async _saveOfflineReadings(readings) {
    if (!this.dbPromise) return;
    try {
      const db = await this.dbPromise;
      if (!db) return;
      const tx = db.transaction(['latest_readings'], 'readwrite');
      const store = tx.objectStore('latest_readings');
      store.put({ id: 'latest', data: readings, timestamp: Date.now() });

      return new Promise((resolve, reject) => {
        tx.oncomplete = () => resolve(true);
        tx.onerror = () => reject(tx.error);
        tx.onabort = () => reject(tx.error);
      });
    } catch (error) {
      console.warn('[Offline] Erro ao salvar IndexedDB:', error);
    }
  }

  async _getOfflineReadings() {
    if (!this.dbPromise) return null;
    try {
      const db = await this.dbPromise;
      if (!db) return null;

      const tx = db.transaction(['latest_readings'], 'readonly');
      const store = tx.objectStore('latest_readings');
      const request = store.get('latest');

      return await new Promise((resolve, reject) => {
        request.onsuccess = () => {
          const result = request.result;
          resolve(result ? result.data : null);
        };
        request.onerror = () => reject(request.error);
      });
    } catch (error) {
      console.warn('[Offline] Erro ao ler IndexedDB:', error);
      return null;
    }
  }

  /**
   * Conecta ao WebSocket para atualizações em tempo real
   */
  connectWebSocket(onMessage) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      console.log('[WS] Já conectado');
      return;
    }

    try {
      this.ws = new WebSocket(this.wsURL);

      this.ws.onopen = () => {
        console.log('[WS] Conectado ao servidor');
        
        // Limpar intervalo de reconexão
        if (this.wsReconnectInterval) {
          clearInterval(this.wsReconnectInterval);
          this.wsReconnectInterval = null;
        }
      };

      this.ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data);
          
          // Chamar callback
          if (onMessage && typeof onMessage === 'function') {
            onMessage(message);
          }

          // Chamar callbacks registrados
          this.wsCallbacks.forEach(callback => callback(message));
        } catch (error) {
          console.error('[WS] Erro ao processar mensagem:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('[WS] Erro:', error);
      };

      this.ws.onclose = () => {
        console.warn('[WS] Desconectado, tentando reconectar em 5s...');
        
        // Tentar reconectar
        if (!this.wsReconnectInterval) {
          this.wsReconnectInterval = setInterval(() => {
            console.log('[WS] Tentando reconectar...');
            this.connectWebSocket(onMessage);
          }, 5000);
        }
      };
    } catch (error) {
      console.error('[WS] Erro ao conectar:', error);
    }
  }

  /**
   * Adiciona callback para mensagens WebSocket
   */
  onWebSocketMessage(callback) {
    if (typeof callback === 'function') {
      this.wsCallbacks.push(callback);
    }
  }

  /**
   * Desconecta WebSocket
   */
  disconnectWebSocket() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    if (this.wsReconnectInterval) {
      clearInterval(this.wsReconnectInterval);
      this.wsReconnectInterval = null;
    }

    this.wsCallbacks = [];
  }

  /**
   * Checa se está conectado ao backend
   */
  async isOnline() {
    try {
      const health = await this.getSystemHealth();
      return health.status === 'ok';
    } catch (error) {
      return false;
    }
  }
}

// Exportar instância global
window.apiService = new ApiService();
