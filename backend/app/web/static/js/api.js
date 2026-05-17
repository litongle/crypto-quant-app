'use strict';

/**
 * Alpha-7 Web API 客户端 v2
 * 封装所有后端 API 调用，自动处理认证和刷新
 */

// 全局命名空间：收敛原 window._xxx 私有状态，避免污染顶层。
// inline onclick 仍走全局函数名（SPA 设计），改 App.state.x 是因为这些是模块间共享的"实例引用"，
// 不是 public API。新增私有共享状态请挂在 App.state.* 下。
window.App = window.App || { state: {} };

const API_BASE = '/api/v1';

/** HTML转义，防止XSS（全局工具函数，所有JS模块共享） */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

class ApiClient {
  constructor() {
    // token 改走 HttpOnly cookie,JS 完全读不到也写不到 → XSS 拿不到 token。
    // _isLoggedIn 三态:
    //   null  = 未知(冷启动首次探活前),401 时仍要尝试 refresh
    //         — 因为 access_token cookie 可能过期 (30min) 但 refresh_token (7d) 还活,
    //         直接判 logged-out 会让用户白白重新登录
    //   true  = 已确认登录(login 成功 或 探活成功后由调用方设)
    //   false = 已显式登出,401 直接快速失败,不再瞎打 refresh
    this._isLoggedIn = null;
    // 清理可能残留的旧版 sessionStorage(老版本浏览器从 Bearer 模式升上来)
    try {
      sessionStorage.removeItem('access_token');
      sessionStorage.removeItem('refresh_token');
    } catch {}
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
  // headers / fetch 都不再附 Authorization — 浏览器靠 HttpOnly cookie 自动带 token,
  // credentials: 'same-origin' 是 fetch 默认行为,但显式写出来防止以后被人改成 'omit'。
  get headers() {
    return { 'Content-Type': 'application/json', 'Accept': 'application/json' };
  }

  async request(method, path, body = null) {
    const opts = { method, headers: this.headers, credentials: 'same-origin' };
    if (body && method !== 'GET') opts.body = JSON.stringify(body);

    let res = await fetch(`${API_BASE}${path}`, opts);

    // 401 → 尝试 refresh(server 从 refresh_token cookie 读)。
    // 显式登出后(_isLoggedIn===false)直接快速失败,不打无意义 refresh;
    // 冷启动(_isLoggedIn===null)还是要试一次 refresh,因为 access cookie 30min 过期
    // 但 refresh cookie 7d 还活,直接判退会让用户白重新登录。
    if (res.status === 401) {
      if (this._isLoggedIn === false) {
        this._markLoggedOut();
        throw new Error('认证已过期，请重新登录');
      }
      const refreshed = await this._refreshAccessToken();
      if (refreshed) {
        res = await fetch(`${API_BASE}${path}`, opts);
      } else {
        this._markLoggedOut();
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
    // 并发竞态保护:多个请求同时 401 时共享同一个 refresh Promise
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
      // refresh_token 由 cookie 自动带,body 不需要
      const res = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  async login(email, password) {
    const res = await fetch(`${API_BASE}/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      credentials: 'same-origin',
      body: new URLSearchParams({ username: email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail || '登录失败');
    }
    const json = await res.json();
    const userData = json.data || json;
    this._isLoggedIn = true;
    // login response body 与 /auth/me 同 schema (UserResponse),
    // 预填进缓存,enterApp() 紧跟的 getUserInfo() 不用再打一次 HTTP。
    this._meCache = { at: Date.now(), value: userData };
    return userData;
  }

  async logout() {
    // 先通知后端清 cookie,再翻 flag。
    // 后端 logout 不需要鉴权(避免 401 时无法登出),即便网络挂了 catch 兜底翻 flag。
    try {
      await fetch(`${API_BASE}/auth/logout`, {
        method: 'POST',
        credentials: 'same-origin',
      });
    } catch {}
    this._markLoggedOut();
  }

  _markLoggedOut() {
    this._isLoggedIn = false;
    this._invalidateUserCache?.();
    // 通知页面进入登出态,让所有 polling 自检停下,避免 401 死循环刷屏
    try {
      window.dispatchEvent(new CustomEvent('cq:logged-out'));
    } catch {}
  }

  get isLoggedIn() {
    // 外部 getter 不暴露 null 三态,只返回布尔。
    // null (未知) 与 false (已登出) 对消费者来说都是"现在没登录"。
    return this._isLoggedIn === true;
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

  // 单账户持仓（含 source / strategyInstanceId / strategyName 字段）
  async getAccountPositions(accountId) {
    const json = await this.get(`/asset/positions?account_id=${accountId}`);
    return json.data || json;
  }

  // 平掉指定持仓；策略仓位平掉后后端会自动暂停对应策略
  async closePosition(positionId) {
    const json = await this.post(`/trading/positions/${positionId}/close`);
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
    // 去重 + 5s 短缓存：login 后 enterApp() 与 DOMContentLoaded 启动探活
    // 都会调一次，叠加策略页/抽屉里独立调用，瞬时能打出 2-3 个相同请求
    const now = Date.now();
    if (this._meCache && now - this._meCache.at < 5000) {
      return this._meCache.value;
    }
    if (this._meInFlight) return this._meInFlight;
    this._meInFlight = (async () => {
      try {
        const json = await this.get('/auth/me');
        const value = json.data || json;
        this._meCache = { at: Date.now(), value };
        return value;
      } finally {
        this._meInFlight = null;
      }
    })();
    return this._meInFlight;
  }

  _invalidateUserCache() {
    this._meCache = null;
    this._meInFlight = null;
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

  async getRiskSettings() {
    return this.get('/settings/risk');
  }

  async putRiskSettings(body) {
    return this.put('/settings/risk', body);
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
