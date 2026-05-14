/**
 * Alpha-7 - 交易对选择器组件
 * 可搜索、分类（现货/永续合约）、带币种图标
 */

// ===== 交易对数据 =====
const FALLBACK_SYMBOL_DATA = [
  // ─── 主流币 ───
  { symbol: 'BTCUSDT',  name: 'BTC/USDT',  base: 'BTC',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'ETHUSDT',  name: 'ETH/USDT',  base: 'ETH',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'BNBUSDT',  name: 'BNB/USDT',  base: 'BNB',  type: 'spot',    category: '主流币', exchanges: ['binance'] },
  { symbol: 'SOLUSDT',  name: 'SOL/USDT',  base: 'SOL',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'XRPUSDT',  name: 'XRP/USDT',  base: 'XRP',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'ADAUSDT',  name: 'ADA/USDT',  base: 'ADA',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'DOGEUSDT', name: 'DOGE/USDT', base: 'DOGE', type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'TRXUSDT',  name: 'TRX/USDT',  base: 'TRX',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'LTCUSDT',  name: 'LTC/USDT',  base: 'LTC',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'AVAXUSDT', name: 'AVAX/USDT', base: 'AVAX', type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'DOTUSDT',  name: 'DOT/USDT',  base: 'DOT',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'LINKUSDT', name: 'LINK/USDT', base: 'LINK', type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'MATICUSDT',name: 'MATIC/USDT',base: 'MATIC',type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'SHIBUSDT', name: 'SHIB/USDT', base: 'SHIB', type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },
  { symbol: 'UNIUSDT',  name: 'UNI/USDT',  base: 'UNI',  type: 'spot',    category: '主流币', exchanges: ['binance','okx','htx'] },

  // ─── DeFi / 热门 ───
  { symbol: 'PEPEUSDT', name: 'PEPE/USDT', base: 'PEPE', type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },
  { symbol: 'WIFUSDT',  name: 'WIF/USDT',  base: 'WIF',  type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },
  { symbol: 'SUIUSDT',  name: 'SUI/USDT',  base: 'SUI',  type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },
  { symbol: 'APTUSDT',  name: 'APT/USDT',  base: 'APT',  type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },
  { symbol: 'ARBUSDT',  name: 'ARB/USDT',  base: 'ARB',  type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },
  { symbol: 'OPUSDT',   name: 'OP/USDT',   base: 'OP',   type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },
  { symbol: 'NEARUSDT', name: 'NEAR/USDT', base: 'NEAR', type: 'spot',    category: '热门',   exchanges: ['binance','okx','htx'] },
  { symbol: 'FILUSDT',  name: 'FIL/USDT',  base: 'FIL',  type: 'spot',    category: '热门',   exchanges: ['binance','okx','htx'] },
  { symbol: 'ATOMUSDT', name: 'ATOM/USDT', base: 'ATOM', type: 'spot',    category: '热门',   exchanges: ['binance','okx','htx'] },
  { symbol: 'AAVEUSDT', name: 'AAVE/USDT', base: 'AAVE', type: 'spot',    category: '热门',   exchanges: ['binance','okx'] },

  // ─── 永续合约(USDT 本位) ───
  // F1: 后端 market_service 已支持 perp 路由
  // (binance fapi / okx SWAP instId / htx linear-swap-ex)
  // .P 后缀仅前端语义,getValue() 时拆成 (symbol, market='perp')
  { symbol: 'BTCUSDT.P',  name: 'BTC/USDT 永续',  base: 'BTC',  type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'ETHUSDT.P',  name: 'ETH/USDT 永续',  base: 'ETH',  type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'SOLUSDT.P',  name: 'SOL/USDT 永续',  base: 'SOL',  type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'BNBUSDT.P',  name: 'BNB/USDT 永续',  base: 'BNB',  type: 'perp', category: '永续合约', exchanges: ['binance'] },
  { symbol: 'XRPUSDT.P',  name: 'XRP/USDT 永续',  base: 'XRP',  type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'DOGEUSDT.P', name: 'DOGE/USDT 永续', base: 'DOGE', type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'ADAUSDT.P',  name: 'ADA/USDT 永续',  base: 'ADA',  type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'AVAXUSDT.P', name: 'AVAX/USDT 永续', base: 'AVAX', type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'LINKUSDT.P', name: 'LINK/USDT 永续', base: 'LINK', type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
  { symbol: 'PEPEUSDT.P', name: 'PEPE/USDT 永续', base: 'PEPE', type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
];

let SYMBOL_DATA = [...FALLBACK_SYMBOL_DATA];
let _symbolDataPromise = null;
let _symbolDataLoaded = false;

const DEFAULT_SYMBOL_EXCHANGES = ['binance', 'okx', 'huobi'];

function normalizeExchangeName(exchange) {
  const value = String(exchange || '').trim().toLowerCase();
  if (value === 'htx') return 'huobi';
  return value;
}

function buildDefaultSpotSymbolMeta(symbol) {
  const upperSymbol = String(symbol || '').trim().toUpperCase();
  const base = upperSymbol.replace(/USDT$/, '') || upperSymbol;
  return {
    symbol: upperSymbol,
    name: `${base}/USDT`,
    base,
    type: 'spot',
    category: '更多交易对',
    exchanges: [...DEFAULT_SYMBOL_EXCHANGES],
  };
}

function cloneSymbolMeta(item) {
  return {
    ...item,
    exchanges: Array.isArray(item.exchanges)
      ? [...new Set(item.exchanges.map(normalizeExchangeName).filter(Boolean))]
      : [...DEFAULT_SYMBOL_EXCHANGES],
  };
}

function buildSymbolDataFromServer(symbols) {
  if (!Array.isArray(symbols) || symbols.length === 0) {
    return [...FALLBACK_SYMBOL_DATA];
  }

  const fallbackBySymbol = new Map(FALLBACK_SYMBOL_DATA.map((item) => [item.symbol, item]));
  const fallbackOrder = new Map(FALLBACK_SYMBOL_DATA.map((item, index) => [item.symbol, index]));
  const seen = new Set();
  const items = [];

  for (const rawSymbol of symbols) {
    const symbol = String(rawSymbol || '').trim().toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);

    const fallbackSpot = fallbackBySymbol.get(symbol);
    items.push(cloneSymbolMeta(fallbackSpot || buildDefaultSpotSymbolMeta(symbol)));

    const fallbackPerp = fallbackBySymbol.get(`${symbol}.P`);
    if (fallbackPerp) {
      items.push(cloneSymbolMeta(fallbackPerp));
    }
  }

  items.sort((a, b) => {
    const aRank = fallbackOrder.has(a.symbol) ? fallbackOrder.get(a.symbol) : Number.MAX_SAFE_INTEGER;
    const bRank = fallbackOrder.has(b.symbol) ? fallbackOrder.get(b.symbol) : Number.MAX_SAFE_INTEGER;
    if (aRank !== bRank) return aRank - bRank;
    return a.symbol.localeCompare(b.symbol);
  });

  return items;
}

async function preloadSymbolSelectorData(force = false) {
  if (!force && _symbolDataLoaded) return SYMBOL_DATA;
  if (!force && _symbolDataPromise) return _symbolDataPromise;
  if (typeof api === 'undefined' || typeof api.getSymbols !== 'function') return SYMBOL_DATA;

  _symbolDataPromise = (async () => {
    try {
      const response = await api.getSymbols();
      const nextData = buildSymbolDataFromServer(response?.symbols || response);
      if (Array.isArray(nextData) && nextData.length > 0) {
        SYMBOL_DATA = nextData;
        _symbolDataLoaded = true;
      }
    } catch {
      // 保持本地兜底列表，页面仍可用
    }
    return SYMBOL_DATA;
  })();

  try {
    return await _symbolDataPromise;
  } finally {
    _symbolDataPromise = null;
  }
}

/**
 * 把前端选择器里的 "BTCUSDT.P" 拆成 { symbol, market }
 * 现货返回 market='spot',永续(.P 后缀)返回 market='perp' 并去掉 .P。
 * F1 起 getValue() 直接返回字符串(向后兼容),用此 helper 拆。
 */
function splitMarket(symbolWithSuffix) {
  if (!symbolWithSuffix) return { symbol: 'BTCUSDT', market: 'spot' };
  if (symbolWithSuffix.endsWith('.P')) {
    return { symbol: symbolWithSuffix.slice(0, -2), market: 'perp' };
  }
  return { symbol: symbolWithSuffix, market: 'spot' };
}

// ===== 币种颜色映射 =====
const COIN_COLORS = {
  BTC: '#F7931A', ETH: '#627EEA', BNB: '#F3BA2F', SOL: '#9945FF',
  XRP: '#23292F', ADA: '#0033AD', DOGE: '#C3A634', TRX: '#FF0013',
  LTC: '#345D9D', AVAX: '#E84142', DOT: '#E6007A', LINK: '#2A5ADA',
  MATIC:'#8247E5', SHIB: '#FFA409', UNI: '#FF007A', PEPE: '#3D7B30',
  WIF: '#D4A373', SUI: '#4DA2FF', APT: '#2DD8A3', ARB: '#28A0F0',
  OP: '#FF0420', NEAR:'#00C1DE', FIL: '#0090FF', ATOM:'#2E3148',
  AAVE: '#B6509E',
};

// ===== 组件类 =====
class SymbolSelector {
  /**
   * @param {Object} opts
   * @param {string} opts.containerId - 挂载容器元素ID
   * @param {string} opts.value - 初始值 (如 'BTCUSDT')
   * @param {Function} opts.onChange - 值变更回调
   * @param {string} [opts.exchangeFilter] - 按交易所过滤的 select ID
   */
  constructor(opts) {
    this.containerId = opts.containerId;
    this.value = opts.value || 'BTCUSDT';
    this.onChange = opts.onChange || (() => {});
    this.exchangeFilterId = opts.exchangeFilter || null;
    this.exchangeResolver = typeof opts.exchangeResolver === 'function' ? opts.exchangeResolver : null;
    this.isOpen = false;
    this.search = '';
    this.filterType = 'all'; // all | spot | perp
    this.symbolData = SYMBOL_DATA;
    this._containerClickHandler = null;
    this._containerInputHandler = null;
    this._documentClickHandler = null;
    this._exchangeFilterHandler = null;

    this._build();
    this._bind();
    preloadSymbolSelectorData().then((data) => this.refreshData(data));
  }

  _getFilteredSymbols() {
    let list = this.symbolData;

    // 按交易所过滤
    if (this.exchangeFilterId) {
      const el = document.getElementById(this.exchangeFilterId);
      if (el) {
        const ex = normalizeExchangeName(
          this.exchangeResolver ? this.exchangeResolver(el.value, el) : el.value
        );
        if (ex) list = list.filter((s) => (s.exchanges || []).includes(ex));
      }
    }

    // 按类型过滤
    if (this.filterType === 'spot') list = list.filter(s => s.type === 'spot');
    else if (this.filterType === 'perp') list = list.filter(s => s.type === 'perp');

    // 搜索
    if (this.search) {
      const q = this.search.toLowerCase();
      list = list.filter(s =>
        s.symbol.toLowerCase().includes(q) ||
        s.name.toLowerCase().includes(q) ||
        s.base.toLowerCase().includes(q)
      );
    }

    return list;
  }

  _findSymbol(val) {
    return this.symbolData.find((s) => s.symbol === val);
  }

  refreshData(nextData = SYMBOL_DATA) {
    if (!Array.isArray(nextData) || nextData.length === 0) return;
    this.symbolData = nextData;
    if (!this._findSymbol(this.value)) {
      this.value = nextData[0].symbol;
    }
    this._build();
  }

  _build() {
    const container = document.getElementById(this.containerId);
    if (!container) return;

    const current = this._findSymbol(this.value);
    const displayName = current ? current.name : this.value;

    container.innerHTML = `
      <div class="sym-sel" data-id="${this.containerId}">
        <div class="sym-sel__trigger">
          ${this._renderSelected(this.value, displayName)}
          <svg class="sym-sel__chevron" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
        </div>
        <div class="sym-sel__dropdown" style="display:none;">
          <div class="sym-sel__search-wrap">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
            <input type="text" class="sym-sel__search" name="symbolSearch" aria-label="搜索币种" placeholder="搜索币种..." autocomplete="off">
          </div>
          <div class="sym-sel__filters">
            <button class="sym-sel__filter active" data-type="all">全部</button>
            <button class="sym-sel__filter" data-type="spot">现货</button>
            <button class="sym-sel__filter" data-type="perp">永续合约</button>

          </div>
          <div class="sym-sel__list"></div>
        </div>
      </div>
    `;

    this._renderList();
  }

  _renderSelected(symbol, displayName) {
    const info = this._findSymbol(symbol);
    const color = info ? (COIN_COLORS[info.base] || 'var(--cq-color-primary)') : 'var(--cq-color-primary)';
    const typeTag = info
      ? (info.type === 'perp'
        ? '<span class="sym-sel__tag sym-sel__tag--perp">合约</span>'
        : '<span class="sym-sel__tag sym-sel__tag--spot">现货</span>')
      : '';

    return `
      <span class="sym-sel__icon" style="background:${color}1A;color:${color};">${info ? info.base : '?'}</span>
      <span class="sym-sel__name">${displayName}</span>
      ${typeTag}
    `;
  }

  _renderList() {
    const container = document.getElementById(this.containerId);
    if (!container) return;
    const listEl = container.querySelector('.sym-sel__list');
    if (!listEl) return;

    const filtered = this._getFilteredSymbols();

    if (filtered.length === 0) {
      listEl.innerHTML = '<div class="sym-sel__empty">没有匹配的交易对</div>';
      return;
    }

    // 按 category 分组
    const groups = {};
    for (const s of filtered) {
      if (!groups[s.category]) groups[s.category] = [];
      groups[s.category].push(s);
    }

    let html = '';
    for (const [cat, items] of Object.entries(groups)) {
      html += `<div class="sym-sel__group-label">${cat}</div>`;
      for (const s of items) {
        const color = COIN_COLORS[s.base] || 'var(--cq-color-primary)';
        const isActive = s.symbol === this.value;
        const typeClass = s.type === 'perp' ? 'sym-sel__tag--perp' : 'sym-sel__tag--spot';
        const typeLabel = s.type === 'perp' ? '合约' : '现货';
        html += `
          <div class="sym-sel__item${isActive ? ' is-active' : ''}" data-symbol="${s.symbol}">
            <span class="sym-sel__icon" style="background:${color}1A;color:${color};">${s.base}</span>
            <span class="sym-sel__item-name">${s.name}</span>
            <span class="sym-sel__tag ${typeClass}">${typeLabel}</span>
          </div>
        `;
      }
    }

    listEl.innerHTML = html;
  }

  _bind() {
    const container = document.getElementById(this.containerId);
    if (!container) return;

    if (!this._containerClickHandler) {
      this._containerClickHandler = (e) => {
        const trigger = e.target.closest('.sym-sel__trigger');
        if (trigger) {
          e.stopPropagation();
          this.toggle();
          return;
        }

        const filter = e.target.closest('.sym-sel__filter');
        if (filter) {
          e.stopPropagation();
          container.querySelectorAll('.sym-sel__filter').forEach((button) => button.classList.remove('active'));
          filter.classList.add('active');
          this.filterType = filter.dataset.type;
          this._renderList();
          return;
        }

        const item = e.target.closest('.sym-sel__item');
        if (item) {
          this.setValue(item.dataset.symbol);
          this.close();
          return;
        }

        if (e.target.closest('.sym-sel__search')) {
          e.stopPropagation();
        }
      };
      container.addEventListener('click', this._containerClickHandler);
    }

    if (!this._containerInputHandler) {
      this._containerInputHandler = (e) => {
        if (!e.target.classList.contains('sym-sel__search')) return;
        this.search = e.target.value;
        this._renderList();
      };
      container.addEventListener('input', this._containerInputHandler);
    }

    if (this.exchangeFilterId && !this._exchangeFilterHandler) {
      const exchangeFilter = document.getElementById(this.exchangeFilterId);
      if (exchangeFilter) {
        this._exchangeFilterHandler = () => this._renderList();
        exchangeFilter.addEventListener('change', this._exchangeFilterHandler);
      }
    }

    if (!this._documentClickHandler) {
      this._documentClickHandler = (e) => {
        if (!container.contains(e.target)) this.close();
      };
      document.addEventListener('click', this._documentClickHandler);
    }
  }

  toggle() {
    this.isOpen ? this.close() : this.open();
  }

  open() {
    const container = document.getElementById(this.containerId);
    if (!container) return;
    const dd = container.querySelector('.sym-sel__dropdown');
    dd.style.display = 'block';
    this.isOpen = true;
    // 聚焦搜索框
    const search = container.querySelector('.sym-sel__search');
    if (search) setTimeout(() => search.focus(), 50);
  }

  close() {
    const container = document.getElementById(this.containerId);
    if (!container) return;
    const dd = container.querySelector('.sym-sel__dropdown');
    dd.style.display = 'none';
    this.isOpen = false;
    // 重置搜索
    this.search = '';
    const search = container.querySelector('.sym-sel__search');
    if (search) search.value = '';
  }

  setValue(symbol) {
    this.value = symbol;
    const current = this._findSymbol(symbol);
    const displayName = current ? current.name : symbol;
    const container = document.getElementById(this.containerId);
    if (!container) return;

    // 更新触发器显示
    const trigger = container.querySelector('.sym-sel__trigger');
    const chevron = trigger.querySelector('.sym-sel__chevron').outerHTML;
    trigger.innerHTML = this._renderSelected(symbol, displayName) + chevron;

    // 更新列表激活态
    this._renderList();

    this.onChange(symbol);
  }

  getValue() {
    return this.value;
  }

  getFilteredSymbols() {
    return this._getFilteredSymbols();
  }
}

window.preloadSymbolSelectorData = preloadSymbolSelectorData;
