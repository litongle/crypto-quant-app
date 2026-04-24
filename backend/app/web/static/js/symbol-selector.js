/**
 * 币钱袋 - 交易对选择器组件
 * 可搜索、分类（现货/永续合约）、带币种图标
 */

// ===== 交易对数据 =====
const SYMBOL_DATA = [
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

  // ─── 永续合约 U本本 ───
  { symbol: 'BTCUSDT.P',  name: 'BTC/USDT 永续',  base: 'BTC',  type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'ETHUSDT.P',  name: 'ETH/USDT 永续',  base: 'ETH',  type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'SOLUSDT.P',  name: 'SOL/USDT 永续',  base: 'SOL',  type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'BNBUSDT.P',  name: 'BNB/USDT 永续',  base: 'BNB',  type: 'perp', category: '永续合约', exchanges: ['binance'] },
  { symbol: 'XRPUSDT.P',  name: 'XRP/USDT 永续',  base: 'XRP',  type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'DOGEUSDT.P', name: 'DOGE/USDT 永续', base: 'DOGE', type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'ADAUSDT.P',  name: 'ADA/USDT 永续',  base: 'ADA',  type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'AVAXUSDT.P', name: 'AVAX/USDT 永续', base: 'AVAX', type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'LINKUSDT.P', name: 'LINK/USDT 永续', base: 'LINK', type: 'perp', category: '永续合约', exchanges: ['binance','okx','htx'] },
  { symbol: 'PEPEUSDT.P', name: 'PEPE/USDT 永续', base: 'PEPE', type: 'perp', category: '永续合约', exchanges: ['binance','okx'] },
];

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
    this.isOpen = false;
    this.search = '';
    this.filterType = 'all'; // all | spot | perp

    this._build();
    this._bind();
  }

  _getFilteredSymbols() {
    let list = SYMBOL_DATA;

    // 按交易所过滤
    if (this.exchangeFilterId) {
      const el = document.getElementById(this.exchangeFilterId);
      if (el) {
        const ex = el.value;
        if (ex) list = list.filter(s => s.exchanges.includes(ex));
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
    return SYMBOL_DATA.find(s => s.symbol === val);
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
            <input type="text" class="sym-sel__search" placeholder="搜索币种..." autocomplete="off">
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

    // 点击触发器
    container.querySelector('.sym-sel__trigger').addEventListener('click', (e) => {
      e.stopPropagation();
      this.toggle();
    });

    // 搜索
    container.querySelector('.sym-sel__search').addEventListener('input', (e) => {
      this.search = e.target.value;
      this._renderList();
    });

    // 搜索框阻止冒泡
    container.querySelector('.sym-sel__search').addEventListener('click', (e) => e.stopPropagation());

    // 类型过滤
    container.querySelectorAll('.sym-sel__filter').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        container.querySelectorAll('.sym-sel__filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        this.filterType = btn.dataset.type;
        this._renderList();
      });
    });

    // 选中项
    container.querySelector('.sym-sel__list').addEventListener('click', (e) => {
      const item = e.target.closest('.sym-sel__item');
      if (!item) return;
      this.setValue(item.dataset.symbol);
      this.close();
    });

    // 点击外部关闭
    document.addEventListener('click', (e) => {
      if (!container.contains(e.target)) this.close();
    });
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
}
