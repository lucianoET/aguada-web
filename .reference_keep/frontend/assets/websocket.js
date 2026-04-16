/* AGUADA - WebSocket Client com fallback */

class WebSocketClient {
    constructor(url) {
        this.url = url || WebSocketClient.detectUrl();
        this.ws = null;
        this.reconnectInterval = 5000; // base 5s
        this.reconnectTimer = null;
        this.listeners = {};
        this.isConnecting = false;
        this.maxReconnectAttempts = 10;
        this.reconnectAttempts = 0;
        this.fallbackTimer = null;
        this.httpFallbackInterval = 15000; // 15s
    }

    static detectUrl() {
        if (typeof window === 'undefined') {
            return 'ws://localhost:3000/ws';
        }
        const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
        const host = window.location.hostname || 'localhost';
        const port = window.location.port || '3000';
        return `${protocol}://${host}:${port}/ws`;
    }

    connect() {
        if (this.isConnecting || (this.ws && this.ws.readyState === WebSocket.OPEN)) {
            return;
        }

        this.isConnecting = true;
        console.log('[WebSocket] Connecting to:', this.url);

        try {
            this.ws = new WebSocket(this.url);
            this.ws.binaryType = 'arraybuffer';

            this.ws.onopen = () => {
                console.log('[WebSocket] Connected');
                this.isConnecting = false;
                this.reconnectAttempts = 0;
                this.emit('connected');
                this.stopFallback();

                if (this.reconnectTimer) {
                    clearTimeout(this.reconnectTimer);
                    this.reconnectTimer = null;
                }
            };

            this.ws.onmessage = (event) => {
                const payload = WebSocketClient.parseMessage(event.data);
                if (!payload) return;

                const messages = WebSocketClient.normalizePayload(payload);
                messages.forEach((data) => {
                    if (data.type) {
                        this.emit(data.type, data);
                    }
                    this.emit('message', data);
                });
            };

            this.ws.onerror = (error) => {
                console.error('[WebSocket] Error:', error);
                this.isConnecting = false;
                this.emit('error', error);
            };

            this.ws.onclose = (event) => {
                console.log('[WebSocket] Disconnected:', event.code, event.reason);
                this.isConnecting = false;
                this.emit('disconnected', event);

                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.scheduleReconnect();
                } else {
                    console.error('[WebSocket] Max reconnect attempts reached');
                    this.emit('maxReconnectAttemptsReached');
                    this.startFallback();
                }
            };
        } catch (error) {
            console.error('[WebSocket] Connection error:', error);
            this.isConnecting = false;
            this.scheduleReconnect();
        }
    }

    static parseMessage(data) {
        try {
            if (typeof data === 'string') {
                return JSON.parse(data);
            }

            if (data instanceof ArrayBuffer) {
                const text = new TextDecoder().decode(data);
                return JSON.parse(text);
            }

            return null;
        } catch (error) {
            console.error('[WebSocket] Error parsing payload:', error);
            return null;
        }
    }

    static normalizePayload(payload) {
        if (!payload) return [];

        if (payload.type === 'readings_batch' && Array.isArray(payload.data)) {
            return payload.data.map(item => ({
                type: 'reading',
                data: item,
                timestamp: payload.timestamp,
                batch: true,
            }));
        }

        return [payload];
    }

    scheduleReconnect() {
        if (this.reconnectTimer) return;

        this.reconnectAttempts++;
        const baseDelay = this.reconnectInterval * Math.min(this.reconnectAttempts, 5);
        const jitter = Math.random() * 1000;

        console.log(`[WebSocket] Reconnecting in ${(baseDelay + jitter)/1000}s (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, baseDelay + jitter);
    }

    send(data) {
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.ws.send(JSON.stringify(data));
            return true;
        }
        console.warn('[WebSocket] Cannot send - not connected');
        return false;
    }

    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
    }

    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }

    emit(event, data) {
        if (!this.listeners[event]) return;
        this.listeners[event].forEach(callback => {
            try {
                callback(data);
            } catch (error) {
                console.error(`[WebSocket] Error in ${event} listener:`, error);
            }
        });
    }

    disconnect() {
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }

        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }

        this.reconnectAttempts = this.maxReconnectAttempts;
        console.log('[WebSocket] Disconnected by user');
    }

    getState() {
        if (!this.ws) return 'CLOSED';
        switch (this.ws.readyState) {
            case WebSocket.CONNECTING: return 'CONNECTING';
            case WebSocket.OPEN: return 'OPEN';
            case WebSocket.CLOSING: return 'CLOSING';
            case WebSocket.CLOSED: return 'CLOSED';
            default: return 'UNKNOWN';
        }
    }

    isConnected() {
        return this.ws && this.ws.readyState === WebSocket.OPEN;
    }

    startFallback() {
        if (this.fallbackTimer || typeof window === 'undefined') return;

        console.warn('[WebSocket] Starting HTTP fallback polling');
        this.emit('fallback:start');

        const poll = async () => {
            try {
                let readings = null;

                if (window.apiService?.getLatestReadings) {
                    readings = await window.apiService.getLatestReadings();
                } else {
                    const response = await fetch('/api/readings/latest');
                    const result = await response.json();
                    readings = result.data;
                }

                if (readings) {
                    this.emit('fallback:data', {
                        type: 'reading',
                        data: readings,
                        timestamp: new Date().toISOString(),
                    });
                }
            } catch (error) {
                console.error('[WebSocket] Fallback polling failed:', error);
                this.emit('fallback:error', error);
            }
        };

        poll();
        this.fallbackTimer = setInterval(poll, this.httpFallbackInterval);
    }

    stopFallback() {
        if (this.fallbackTimer) {
            clearInterval(this.fallbackTimer);
            this.fallbackTimer = null;
            this.emit('fallback:stop');
            console.log('[WebSocket] HTTP fallback stopped');
        }
    }
}

// Instância global
const wsClient = new WebSocketClient();

if (typeof window !== 'undefined') {
    setTimeout(() => wsClient.connect(), 1000);

    document.addEventListener('visibilitychange', () => {
        if (!document.hidden && !wsClient.isConnected()) {
            wsClient.connect();
        }
    });
}

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { WebSocketClient, wsClient };
}
