/**
 * 币钱袋 Web API 客户端 v2
 * 封装所有后端 API 调用，自动处理认证和刷新
 */
const API_BASE = '/api/v1';

class ApiClient {
  constructor() {
    this.accessToken = localStorage.getItem('access_token') || '';
    this.refreshToken = localStorage.getItem('refresh_token') || '';
  }

  // ===== 认证 =====
  get headers() {
    const h = { 'Content-Type': 'application/json', 'Accept': 'application/json' };
    if (this.accessToken) h['Authorization'] = `Bearer ${this.accessToken}`;
    return h;
  }

  async request(method, path, body = null) {
    const opts = { method, headers: this.headers };
    if (body && method !== 'GET') opts.body = JSON.stringify(body);

    let res = await fetch(`${API_BASE}${path}`, opts);

    // 401 → 尝试刷新 Token
    if (res.status === 401 && this.refreshToken) {
      const refreshed = await this._refreshAccessToken();
      if (refreshed) {
        opts.headers = this.headers;
        res = await fetch(`${API_BASE}${path}`, opts);
      } else {
        this.logout();
        throw new Error('认证已过期，请重新登录');
      }
    }

    if (!res.ok) {
      const err = await res.json().catch(() => ({ message: `请求失败 (${res.status})` }));
      throw new Error(err.message || err.error?.message || `请求失败 (${res.status})`);
    }

    return res.json();
  }

  async _refreshAccessToken() {
    try {
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: this.refreshToken }),
      });
      if (!res.ok) return false;
      const json = await res.json();
      const data = json.data || json;
      this.accessToken = data.access_token;
      if (data.refresh_token) this.refreshToken = data.refresh_token;
      localStorage.setItem('access_token', this.accessToken);
      localStorage.setItem('refresh_token', this.refreshToken);
      return true;
    } catch {
      return false;
    }
  }

  async login(email, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: new URLSearchParams({ username: email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '登录失败');
    }
    const json = await res.json();
    this.accessToken = json.access_token;
    this.refreshToken = json.refresh_token;
    localStorage.setItem('access_token', this.accessToken);
    localStorage.setItem('refresh_token', this.refreshToken);
    return json;
  }

  async register(email, password, name) {
    const res = await fetch(`${API_BASE}/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email, password, name }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '注册失败');
    }
    const json = await res.json();
    this.accessToken = json.access_token;
    this.refreshToken = json.refresh_token;
    localStorage.setItem('access_token', this.accessToken);
    localStorage.setItem('refresh_token', this.refreshToken);
    return json;
  }

  logout() {
    this.accessToken = '';
    this.refreshToken = '';
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
  }

  get isLoggedIn() {
    return !!this.accessToken;
  }

  // ===== 便捷方法 =====
  async get(path) { return this.request('GET', path); }
  async post(path, body) { return this.request('POST', path, body); }
  async put(path, body) { return this.request('PUT', path, body); }
  async del(path) { return this.request('DELETE', path); }

  // ===== 业务 API =====
  async getAssetSummary(exchange = 'all') {
    const json = await this.get(`/asset/summary?exchange=${exchange}`);
    return json.data || json;
  }

  async getPositions(exchange = 'all', side = 'all') {
    const json = await this.get(`/asset/positions?exchange=${exchange}&side=${side}`);
    return json.data || json;
  }

  async getEquityCurve(days = 30, exchange = 'all') {
    const json = await this.get(`/asset/equity-curve?days=${days}&exchange=${exchange}`);
    return json.data || json;
  }

  async getStrategyTemplates() {
    const json = await this.get('/strategies/templates');
    return json.data || json;
  }

  async getStrategyInstances(status = 'all') {
    const json = await this.get(`/strategies/instances?status=${status}`);
    return json.data || json;
  }

  async createStrategyInstance({ name, templateId, exchange, symbol, accountId, params }) {
    const body = { name, templateId, exchange, symbol, params };
    if (accountId) body.accountId = accountId;
    const json = await this.post('/strategies/instances', body);
    return json.data || json;
  }

  async startStrategy(instanceId) {
    const json = await this.post(`/strategies/instances/${instanceId}/start`);
    return json.data || json;
  }

  async stopStrategy(instanceId) {
    const json = await this.post(`/strategies/instances/${instanceId}/stop`);
    return json.data || json;
  }

  async deleteStrategy(instanceId) {
    return this.del(`/strategies/instances/${instanceId}`);
  }

  async runBacktest(params) {
    const json = await this.post('/backtest/run', params);
    return json.data || json;
  }

  async getBacktestResults(backtestId) {
    const json = await this.get(`/backtest/${backtestId}`);
    return json.data || json;
  }

  async getBacktestHistory(limit = 20) {
    const json = await this.get(`/backtest/history?limit=${limit}`);
    return json.data || [];
  }

  // ===== 行情数据 =====
  async getTicker(symbol, exchange = 'binance') {
    const json = await this.get(`/market/ticker/${symbol}?exchange=${exchange}`);
    return json.data || json;
  }

  async getKline(symbol, interval = '1h', limit = 100, exchange = 'binance') {
    const json = await this.get(`/market/kline/${symbol}?interval=${interval}&limit=${limit}&exchange=${exchange}`);
    return json.data || json;
  }

  async getOrderbook(symbol, limit = 20, exchange = 'binance') {
    const json = await this.get(`/market/orderbook/${symbol}?limit=${limit}&exchange=${exchange}`);
    return json.data || json;
  }

  async getSymbols() {
    const json = await this.get('/market/symbols');
    return json.data || json;
  }

  async getBatchTickers(symbols = 'BTC,ETH,SOL,BNB,DOGE') {
    const json = await this.get(`/market/tickers?symbols=${symbols}`);
    return json.data || json || [];
  }

  // ===== 交易所账户管理 =====
  async getExchangeAccounts() {
    const json = await this.get('/trading/accounts');
    return json.data || json || [];
  }

  async createExchangeAccount(data) {
    const json = await this.post('/trading/accounts', data);
    return json.data || json;
  }

  async syncExchangeAccount(accountId) {
    const json = await this.post(`/trading/accounts/${accountId}/sync`);
    return json.data || json;
  }

  async deleteExchangeAccount(accountId) {
    return this.del(`/trading/accounts/${accountId}`);
  }

  // ===== 交易/订单 =====
  async createOrder({ accountId, symbol, side, orderType, quantity, price, strategyInstanceId }) {
    const body = {
      account_id: accountId,
      symbol,
      side,
      order_type: orderType,
      quantity: String(quantity),
    };
    if (price) body.price = String(price);
    if (strategyInstanceId) body.strategy_instance_id = strategyInstanceId;
    const json = await this.post('/trading', body);
    return json.data || json;
  }

  async getOrders({ accountId, symbol, limit } = {}) {
    const params = new URLSearchParams();
    if (accountId) params.set('account_id', accountId);
    if (symbol) params.set('symbol', symbol);
    if (limit) params.set('limit', limit);
    const qs = params.toString();
    const json = await this.get(`/trading${qs ? '?' + qs : ''}`);
    return json.data || json || [];
  }

  async cancelOrder(orderId) {
    const json = await this.post(`/trading/${orderId}/cancel`);
    return json.data || json;
  }

  async getPositions(accountId) {
    const qs = accountId ? `?account_id=${accountId}` : '';
    const json = await this.get(`/trading/positions${qs}`);
    return json.data || json || [];
  }

  async setStopLoss(positionId, accountId, stopPrice) {
    const json = await this.post(`/trading/${positionId}/stop-loss`, {
      account_id: accountId,
      stop_price: String(stopPrice),
    });
    return json.data || json;
  }

  async setTakeProfit(positionId, accountId, takeProfitPrice) {
    const json = await this.post(`/trading/${positionId}/take-profit`, {
      account_id: accountId,
      take_profit_price: String(takeProfitPrice),
    });
    return json.data || json;
  }

  async closePosition(positionId) {
    const json = await this.post(`/trading/${positionId}/close`);
    return json.data || json;
  }

  async emergencyCloseAll(accountId) {
    const qs = accountId ? `?account_id=${accountId}` : '';
    const json = await this.post(`/trading/emergency-close-all${qs}`);
    return json.data || json;
  }

  async getUserInfo() {
    const json = await this.get('/auth/me');
    return json.data || json;
  }

  // ===== 策略详情/绩效/编辑 =====
  async getStrategyDetail(instanceId) {
    const json = await this.get(`/strategies/instances/${instanceId}`);
    return json.data || json;
  }

  async getStrategyPerformance(instanceId) {
    const json = await this.get(`/strategies/instances/${instanceId}/performance`);
    return json.data || json;
  }

  async updateStrategy(instanceId, data) {
    const json = await this.put(`/strategies/instances/${instanceId}`, data);
    return json.data || json;
  }
}

// 全局单例
const api = new ApiClient();
