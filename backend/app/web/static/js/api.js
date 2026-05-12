/**
 * 币钱袋 Web API 客户端 v2
 * 封装所有后端 API 调用，自动处理认证和刷新
 */
const API_BASE = '/api/v1';

/** HTML转义，防止XSS（全局工具函数，所有JS模块共享） */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

class ApiClient {
  constructor() {
    // 使用 sessionStorage 替代 localStorage，降低 XSS 风险（页面关闭时自动清除）
    this.accessToken = sessionStorage.getItem('access_token') || '';
    this.refreshToken = sessionStorage.getItem('refresh_token') || '';
  }

  _normalizeExchangeAccount(raw) {
    if (!raw) return raw;
    return {
      ...raw,
      account_name: raw.account_name ?? raw.accountName ?? '',
      accountName: raw.accountName ?? raw.account_name ?? '',
      is_active: raw.is_active ?? raw.isActive ?? false,
      isActive: raw.isActive ?? raw.is_active ?? false,
      is_demo: raw.is_demo ?? raw.isDemo ?? false,
      isDemo: raw.isDemo ?? raw.is_demo ?? false,
      is_testnet: raw.is_testnet ?? raw.isTestnet ?? false,
      isTestnet: raw.isTestnet ?? raw.is_testnet ?? false,
      is_paper: raw.is_paper ?? raw.isPaper ?? false,
      isPaper: raw.isPaper ?? raw.is_paper ?? false,
      frozen_balance: raw.frozen_balance ?? raw.frozenBalance ?? '0',
      frozenBalance: raw.frozenBalance ?? raw.frozen_balance ?? '0',
      error_message: raw.error_message ?? raw.errorMessage ?? '',
      errorMessage: raw.errorMessage ?? raw.error_message ?? '',
      last_sync_at: raw.last_sync_at ?? raw.lastSyncAt ?? '',
      lastSyncAt: raw.lastSyncAt ?? raw.last_sync_at ?? '',
      balances: raw.balances ?? {},
    };
  }

  _normalizePaperAccount(raw) {
    if (!raw) return raw;
    return {
      ...raw,
      isActive: raw.isActive ?? raw.is_active ?? false,
      is_active: raw.is_active ?? raw.isActive ?? false,
      isPaper: raw.isPaper ?? raw.is_paper ?? true,
      balances: raw.balances ?? {},
    };
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
      const err = await res.json().catch(() => ({}));
      const detail = err.detail;
      let detailStr = '';
      if (typeof detail === 'string') detailStr = detail;
      else if (Array.isArray(detail)) {
        detailStr = detail.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ');
      }
      const msg =
        err.message ||
        err.error?.message ||
        detailStr ||
        `请求失败 (${res.status})`;
      throw new Error(msg);
    }

    return res.json();
  }

  async _refreshAccessToken() {
    // 并发竞态保护：多个请求同时 401 时共享同一个 refresh Promise
    if (this._refreshPromise) return this._refreshPromise;
    this._refreshPromise = this._doRefresh();
    try {
      return await this._refreshPromise;
    } finally {
      this._refreshPromise = null;
    }
  }

  async _doRefresh() {
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
      sessionStorage.setItem('access_token', this.accessToken);
      sessionStorage.setItem('refresh_token', this.refreshToken);
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
    const data = json.data || json;  // APIResponse 包裹兼容
    this.accessToken = data.access_token;
    this.refreshToken = data.refresh_token;
    sessionStorage.setItem('access_token', this.accessToken);
    sessionStorage.setItem('refresh_token', this.refreshToken);
    return data;
  }

  logout() {
    this.accessToken = '';
    this.refreshToken = '';
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
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

  // 资产页:账户全持仓视图(跨账户聚合)
  async getPortfolioPositions(exchange = 'all', side = 'all') {
    const json = await this.get(`/asset/positions?exchange=${exchange}&side=${side}`);
    return json.data || json;
  }

  async getEquityCurve(days = 30, exchange = 'all') {
    const json = await this.get(`/asset/equity-curve?days=${days}&exchange=${exchange}`);
    return json.data || json;
  }

  async getRiskDashboard() {
    const json = await this.get('/asset/risk-dashboard');
    return json.data || json;
  }

  async createPaperAccount() {
    const json = await this.post('/asset/paper-account');
    return this._normalizePaperAccount(json.data || json);
  }

  async getPaperAccounts() {
    const json = await this.get('/asset/paper-accounts');
    return (json.data || json || []).map((item) => this._normalizePaperAccount(item));
  }

  async resetPaperAccount(accountId) {
    return this.post(`/asset/paper-account/${accountId}/reset`);
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

  async pauseStrategy(instanceId) {
    const json = await this.post(`/strategies/instances/${instanceId}/pause`);
    return json.data || json;
  }

  async stopStrategy(instanceId) {
    const json = await this.post(`/strategies/instances/${instanceId}/stop`);
    return json.data || json;
  }

  async cloneStrategyToDraft(instanceId) {
    const json = await this.post(`/strategies/instances/${instanceId}/clone-draft`);
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
  // market: 'spot' | 'perp'(永续合约)
  async getTicker(symbol, exchange = 'binance', market = 'spot', fresh = false) {
    const suffix = fresh ? '&fresh=1' : '';
    const json = await this.get(`/market/ticker/${symbol}?exchange=${exchange}&market=${market}${suffix}`);
    return json.data || json;
  }

  async getKline(symbol, interval = '1h', limit = 100, exchange = 'binance', market = 'spot') {
    const json = await this.get(`/market/kline/${symbol}?interval=${interval}&limit=${limit}&exchange=${exchange}&market=${market}`);
    return json.data || json;
  }

  async getSymbols() {
    const json = await this.get('/market/symbols');
    return json.data || json;
  }

  async getMarketIntervals(exchange = 'binance', market = 'spot') {
    const json = await this.get(`/market/intervals?exchange=${exchange}&market=${market}`);
    return json.data || json;
  }

  async getBatchTickers(symbols = 'BTC,ETH,SOL,BNB,DOGE') {
    const json = await this.get(`/market/tickers?symbols=${symbols}`);
    return json.data || json || [];
  }

  async getEvents(params = {}) {
    const search = new URLSearchParams();
    Object.entries(params || {}).forEach(([key, value]) => {
      if (value == null || value === '') return;
      search.set(key, String(value));
    });
    const suffix = search.toString() ? `?${search.toString()}` : '';
    const json = await this.get(`/events${suffix}`);
    return json.data || json;
  }

  async getRunnerStatus() {
    const json = await this.get('/strategies/runner/status');
    return json.data || json;
  }

  // ===== 交易所账户管理 =====
  async getExchangeAccounts({ includePaper = false } = {}) {
    const qs = includePaper ? '?include_paper=true' : '';
    const json = await this.get(`/trading/accounts${qs}`);
    return (json.data || json || []).map((item) => this._normalizeExchangeAccount(item));
  }

  async createExchangeAccount(data) {
    const json = await this.post('/trading/accounts', data);
    return this._normalizeExchangeAccount(json.data || json);
  }

  async getExchangeAccount(accountId) {
    const json = await this.get(`/trading/accounts/${accountId}`);
    return this._normalizeExchangeAccount(json.data || json);
  }

  async syncExchangeAccount(accountId) {
    const json = await this.post(`/trading/accounts/${accountId}/sync`);
    return this._normalizeExchangeAccount(json.data || json);
  }

  async deleteExchangeAccount(accountId) {
    return this.del(`/trading/accounts/${accountId}`);
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

  async getStrategySnapshot(instanceId) {
    const json = await this.get(`/strategies/instances/${instanceId}/snapshot`);
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

  // ===== 规则引擎 =====
  async validateRules(rules) {
    const json = await this.post('/strategies/validate-rules', { rules });
    return json.data || json;
  }

  // ===== 设置抽屉（运行时配置）=====
  async getNotificationsSettings() {
    return this.get('/settings/notifications');
  }

  async putNotificationsSettings(body) {
    return this.put('/settings/notifications', body);
  }

  async getSmtpSettings() {
    return this.get('/settings/smtp');
  }

  async putSmtpSettings(body) {
    return this.put('/settings/smtp', body);
  }

  async testNotification(channel) {
    return this.post('/settings/notifications/test', { channel });
  }
}

// 全局单例
const api = new ApiClient();

function resolveSinceParam(range) {
  const now = new Date();
  const next = new Date(now);
  if (range === '1h') next.setHours(now.getHours() - 1);
  else if (range === '24h') next.setHours(now.getHours() - 24);
  else if (range === '7d') next.setDate(now.getDate() - 7);
  else if (range === '30d') next.setDate(now.getDate() - 30);
  else return '';
  return next.toISOString();
}
