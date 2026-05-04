/**
 * 交易页面逻辑 v2 — 账户感知的交易对、现货/永续语义、规则预校验
 */

let tradingForm = {
  accountId: null,
  symbol: 'BTCUSDT',
  marketFilter: 'spot',
  pairSearch: '',
  bottomTab: 'positions',
  side: 'buy',
  orderType: 'market',
  quantity: '',
  price: '',
  symbolRules: null,
  contractSettings: null,
};

let tradingOrderbookTimer = null;

async function loadTradingPage() {
  if (typeof preloadSymbolSelectorData === 'function') {
    await preloadSymbolSelectorData();
  }

  try {
    const accounts = await api.getExchangeAccounts({ includePaper: true });
    window._tradingAccounts = accounts;
    renderTradingAccountSelect(accounts);
  } catch {
    window._tradingAccounts = [];
    renderTradingAccountSelect([]);
  }

  attachTradingInputHandlers();
  bindTradingTerminalInteractions();
  renderTradingPairBrowser();
  ensureTradingSymbolMatchesAccount();
  await loadTradingSymbolRules();
  await loadTradingContractSettings();
  await refreshTradingData();
  startTradingOrderbookPolling();
  setTradingBottomTab(tradingForm.bottomTab);
  setTradingSide(tradingForm.side);
  setTradingOrderType(tradingForm.orderType);
}

function renderTradingAccountSelect(accounts) {
  const sel = document.getElementById('trading-account-select');
  if (!sel) return;

  if (accounts.length === 0) {
    sel.innerHTML = '<option value="">请先添加交易所账户</option>';
    tradingForm.accountId = null;
    renderTradingRuleSummary();
    return;
  }

  sel.innerHTML = accounts.map((a) => {
    const meta = { binance: 'Binance', okx: 'OKX', huobi: 'HTX' }[a.exchange] || a.exchange;
    const env = getTradingAccountEnvironmentLabel(a);
    return `<option value="${a.id}">${escapeHtml(a.account_name || meta)} (${meta}${env ? ` / ${env}` : ''}) — ${Number(a.balance || 0).toFixed(2)} USDT</option>`;
  }).join('');

  tradingForm.accountId = parseInt(sel.value, 10) || null;
}

function getTradingAccounts() {
  return Array.isArray(window._tradingAccounts) ? window._tradingAccounts : [];
}

function getTradingAccount(accountId = tradingForm.accountId) {
  const targetId = parseInt(accountId, 10);
  return getTradingAccounts().find((item) => Number(item.id) === targetId) || null;
}

function getTradingAccountExchange(accountId = tradingForm.accountId) {
  return getTradingAccount(accountId)?.exchange || '';
}

function getTradingSymbolData() {
  return Array.isArray(SYMBOL_DATA) ? SYMBOL_DATA : [];
}

function getTradingFilteredSymbols() {
  const exchange = getTradingAccountExchange();
  const query = String(tradingForm.pairSearch || '').trim().toLowerCase();

  return getTradingSymbolData().filter((item) => {
    if (exchange && Array.isArray(item.exchanges) && !item.exchanges.includes(exchange)) {
      return false;
    }
    if (tradingForm.marketFilter === 'spot' && item.type !== 'spot') return false;
    if (tradingForm.marketFilter === 'perp' && item.type !== 'perp') return false;
    if (!query) return true;
    return [
      item.symbol,
      item.name,
      item.base,
      item.category,
    ].some((value) => String(value || '').toLowerCase().includes(query));
  });
}

function getTradingDisplaySymbol(symbol = tradingForm.symbol) {
  return String(symbol || '').replace('.P', '').replace('USDT', '/USDT');
}

function syncTradingTerminalMode() {
  const terminal = document.querySelector('.cq-trading-terminal');
  const isPerp = isTradingPerp();
  if (terminal) {
    terminal.classList.toggle('is-perp', isPerp);
    terminal.classList.toggle('is-spot', !isPerp);
  }

  document.querySelectorAll('.cq-trading-market-switch__btn').forEach((button) => {
    const isActive = button.id === `trading-market-switch-${tradingForm.marketFilter}`;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function renderTradingPairBrowser() {
  const listEl = document.getElementById('trading-symbol-selector');
  const countEl = document.getElementById('trading-pair-count');
  const searchInput = document.getElementById('trading-pair-search');
  if (!listEl) return;

  if (searchInput && searchInput.value !== tradingForm.pairSearch) {
    searchInput.value = tradingForm.pairSearch;
  }

  syncTradingTerminalMode();

  const symbols = getTradingFilteredSymbols();
  if (countEl) {
    countEl.textContent = String(symbols.length);
  }

  if (symbols.length === 0) {
    listEl.setAttribute('aria-activedescendant', '');
    listEl.innerHTML = '<div class="cq-trading-pairs__empty">当前账户下没有匹配的交易对</div>';
    return;
  }

  const activeItem = symbols.find((item) => item.symbol === tradingForm.symbol) || symbols[0];
  listEl.setAttribute('aria-activedescendant', `trading-symbol-${activeItem.symbol.replace(/[^a-zA-Z0-9_-]/g, '-')}`);
  listEl.innerHTML = symbols.map((item) => {
    const color = COIN_COLORS?.[item.base] || 'var(--cq-color-primary)';
    const active = item.symbol === tradingForm.symbol;
    const optionId = `trading-symbol-${item.symbol.replace(/[^a-zA-Z0-9_-]/g, '-')}`;
    return `
      <button
        class="cq-trading-pairs__item${active ? ' is-active' : ''}"
        type="button"
        role="option"
        id="${optionId}"
        aria-selected="${active ? 'true' : 'false'}"
        onclick="selectTradingSymbol('${item.symbol}')"
      >
        <span class="cq-trading-pairs__coin" style="background:${color}1A;color:${color};">${escapeHtml(item.base)}</span>
        <span class="cq-trading-pairs__meta">
          <strong>${escapeHtml(getTradingDisplaySymbol(item.symbol))}</strong>
          <span>${escapeHtml(item.category || (item.type === 'perp' ? '永续合约' : '现货'))}</span>
        </span>
        <span class="cq-trading-pairs__type cq-trading-pairs__type--${item.type}">${item.type === 'perp' ? '合约' : '现货'}</span>
      </button>
    `;
  }).join('');
}

function isTradingPerp(symbol = tradingForm.symbol) {
  return String(symbol || '').toUpperCase().endsWith('.P');
}

function getTradingSideLabels() {
  if (isTradingPerp()) {
    return {
      buy: '开多',
      sell: '开空',
      submitBuy: '开多',
      submitSell: '开空',
      helper: '合约模式下左侧用于开仓，平仓请使用右侧持仓操作。',
    };
  }
  return {
    buy: '买入',
    sell: '卖出',
    submitBuy: '买入',
    submitSell: '卖出',
    helper: '现货模式下买入增加持仓，卖出减少现货持仓。',
  };
}

function formatTradingNumber(value, fallback = '--') {
  if (value === null || value === undefined || value === '') return fallback;
  const normalized = normalizeDecimalString(String(value)) || String(value);
  const num = Number(normalized);
  if (!Number.isFinite(num)) return normalized;
  if (Math.abs(num) >= 1000) return num.toLocaleString('zh-CN', { maximumFractionDigits: 8 });
  return num.toLocaleString('zh-CN', { maximumFractionDigits: 8 });
}

function getTradingAccountEnvironmentLabel(account) {
  if (!account) return '';
  if (account.isPaper) return '本地模拟盘';
  if (account.isDemo) return '模拟盘';
  if (account.isTestnet) return '测试网';
  return '实盘';
}

function isTradingPaperAccount(account = getTradingAccount()) {
  return !!account?.isPaper;
}

function getTradingAccountKindLabel(account = getTradingAccount()) {
  if (!account) return '交易账户';
  if (account.isPaper) return '本地模拟账户';
  if (account.isDemo) return '交易所模拟盘账户';
  if (account.isTestnet) return '测试网账户';
  return '实盘账户';
}

function normalizeDecimalString(raw) {
  const value = String(raw ?? '').trim();
  if (!value || !/^\d+(\.\d+)?$/.test(value)) return null;
  const normalized = value.replace(/^0+(?=\d)/, '');
  return normalized.startsWith('.') ? `0${normalized}` : normalized;
}

function decimalScale(value) {
  const text = normalizeDecimalString(value) || '0';
  return text.includes('.') ? text.split('.')[1].length : 0;
}

function decimalToBigInt(value, scale) {
  const text = normalizeDecimalString(value) || '0';
  const parts = text.split('.');
  const intPart = parts[0] || '0';
  const fracPart = (parts[1] || '').padEnd(scale, '0');
  return BigInt(`${intPart}${fracPart.slice(0, scale)}` || '0');
}

function compareDecimalStrings(left, right) {
  const scale = Math.max(decimalScale(left), decimalScale(right));
  const a = decimalToBigInt(left, scale);
  const b = decimalToBigInt(right, scale);
  if (a === b) return 0;
  return a > b ? 1 : -1;
}

function isDecimalMultiple(value, step) {
  const normalizedStep = normalizeDecimalString(step);
  const normalizedValue = normalizeDecimalString(value);
  if (!normalizedStep || !normalizedValue) return false;
  const scale = Math.max(decimalScale(normalizedValue), decimalScale(normalizedStep));
  const stepInt = decimalToBigInt(normalizedStep, scale);
  if (stepInt === 0n) return true;
  return decimalToBigInt(normalizedValue, scale) % stepInt === 0n;
}

function attachTradingInputHandlers() {
  const quantityInput = document.getElementById('trading-quantity');
  const priceInput = document.getElementById('trading-price');
  const pairSearchInput = document.getElementById('trading-pair-search');

  if (quantityInput && !quantityInput.dataset.boundTrading) {
    quantityInput.dataset.boundTrading = '1';
    quantityInput.addEventListener('input', () => {
      quantityInput.setCustomValidity('');
      tradingForm.quantity = quantityInput.value;
    });
  }

  if (priceInput && !priceInput.dataset.boundTrading) {
    priceInput.dataset.boundTrading = '1';
    priceInput.addEventListener('input', () => {
      priceInput.setCustomValidity('');
      tradingForm.price = priceInput.value;
    });
  }

  if (pairSearchInput && !pairSearchInput.dataset.boundTrading) {
    pairSearchInput.dataset.boundTrading = '1';
    pairSearchInput.addEventListener('input', () => {
      tradingForm.pairSearch = pairSearchInput.value;
      renderTradingPairBrowser();
    });
  }
}

function bindTradingTerminalInteractions() {
  const pairSearchInput = document.getElementById('trading-pair-search');
  if (pairSearchInput && !pairSearchInput.dataset.boundTradingNav) {
    pairSearchInput.dataset.boundTradingNav = '1';
    pairSearchInput.addEventListener('keydown', (event) => {
      if (!['ArrowDown', 'ArrowUp', 'Enter'].includes(event.key)) return;
      const symbols = getTradingFilteredSymbols();
      if (!symbols.length) return;
      const currentIndex = Math.max(0, symbols.findIndex((item) => item.symbol === tradingForm.symbol));
      if (event.key === 'Enter') {
        event.preventDefault();
        selectTradingSymbol(symbols[currentIndex].symbol);
        return;
      }
      event.preventDefault();
      const offset = event.key === 'ArrowDown' ? 1 : -1;
      const nextIndex = (currentIndex + offset + symbols.length) % symbols.length;
      selectTradingSymbol(symbols[nextIndex].symbol);
    });
  }
}

function ensureTradingSymbolMatchesAccount() {
  const available = getTradingFilteredSymbols();
  if (!Array.isArray(available) || available.length === 0) return;
  const current = tradingForm.symbol;
  if (!available.some((item) => item.symbol === current)) {
    handleTradingSymbolChange(available[0].symbol);
    return;
  }
  renderTradingPairBrowser();
  handleTradingSymbolChange(current);
}

function handleTradingSymbolChange(value) {
  tradingForm.symbol = value || 'BTCUSDT';
  tradingForm.marketFilter = isTradingPerp(tradingForm.symbol) ? 'perp' : 'spot';
  tradingForm.symbolRules = null;
  tradingForm.contractSettings = null;
  renderTradingRuleSummary();
  updateTradingSideLabels();
  renderTradingPairBrowser();
  loadTradingSymbolRules();
  loadTradingContractSettings();
  loadTradingOrderbook();
}

async function handleTradingAccountChange(value) {
  tradingForm.accountId = parseInt(value, 10) || null;
  renderTradingPairBrowser();
  ensureTradingSymbolMatchesAccount();
  await loadTradingSymbolRules();
  await loadTradingContractSettings();
  await refreshTradingData();
  await loadTradingOrderbook();
}

function setTradingMarketFilter(nextFilter) {
  if (!['spot', 'perp'].includes(nextFilter)) return;
  tradingForm.marketFilter = nextFilter;
  renderTradingPairBrowser();
  ensureTradingSymbolMatchesAccount();
}

function selectTradingSymbol(symbol) {
  handleTradingSymbolChange(symbol);
}

function setTradingBottomTab(tab) {
  tradingForm.bottomTab = tab;
  document.querySelectorAll('.cq-trading-tabs__btn').forEach((button) => {
    const isActive = button.dataset.tab === tab;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-selected', isActive ? 'true' : 'false');
    button.setAttribute('tabindex', isActive ? '0' : '-1');
  });
  document.querySelectorAll('.cq-trading-tabs__panel').forEach((panel) => {
    const isActive = panel.id === `trading-tab-panel-${tab}`;
    panel.classList.toggle('is-active', isActive);
    panel.hidden = !isActive;
  });
}

function updateTradingSideLabels() {
  const labels = getTradingSideLabels();
  document.querySelectorAll('.cq-side-btn').forEach((button) => {
    const side = button.dataset.side;
    if (!side) return;
    button.textContent = side === 'buy' ? labels.buy : labels.sell;
  });
  updateTradingSubmitBtnLabel();
  renderTradingRuleSummary();
}

function setTradingSide(side) {
  tradingForm.side = side;
  document.querySelectorAll('.cq-side-btn').forEach((button) => {
    const isActive = button.dataset.side === side;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
  updateTradingSubmitBtnLabel();
}

function updateTradingSubmitBtnLabel() {
  const btn = document.getElementById('trading-submit-btn');
  if (!btn || btn.dataset.loading === '1') return;
  const labels = getTradingSideLabels();
  btn.textContent = tradingForm.side === 'buy' ? labels.submitBuy : labels.submitSell;
}

function setTradingOrderType(type) {
  tradingForm.orderType = type;
  document.querySelectorAll('.cq-otype-btn').forEach((button) => {
    const isActive = button.dataset.otype === type;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
  const priceField = document.getElementById('trading-price-field');
  if (priceField) {
    priceField.style.display = type === 'limit' ? 'block' : 'none';
  }
}

function syncTradingRuleInputs() {
  const quantityInput = document.getElementById('trading-quantity');
  const priceInput = document.getElementById('trading-price');
  const quantityLabel = document.getElementById('trading-quantity-label');
  const priceLabel = document.getElementById('trading-price-label');
  const rules = tradingForm.symbolRules;

  if (quantityLabel) {
    quantityLabel.textContent = rules?.quantityLabel || '数量';
  }
  if (priceLabel) {
    priceLabel.textContent = isTradingPerp() ? '委托价格' : '价格 (USDT)';
  }

  if (quantityInput) {
    quantityInput.setCustomValidity('');
    quantityInput.min = rules?.minQty || '0';
    quantityInput.step = rules?.stepSize || 'any';
    quantityInput.placeholder = rules?.minQty || '0.00';
  }

  if (priceInput) {
    priceInput.setCustomValidity('');
    priceInput.step = rules?.tickSize || 'any';
  }
}

function renderTradingContractSettings(errorMessage = '') {
  const panel = document.getElementById('trading-contract-settings');
  const leverageInput = document.getElementById('trading-leverage');
  const paperHint = document.getElementById('trading-paper-hint');
  if (!panel || !leverageInput || !paperHint) return;

  const isPerp = isTradingPerp();
  panel.style.display = isPerp ? 'block' : 'none';
  if (!isPerp) return;

  const settings = tradingForm.contractSettings || { leverage: 10, margin_mode: 'cross' };
  leverageInput.value = String(settings.leverage || 10);
  document.querySelectorAll('.cq-margin-btn').forEach((button) => {
    const isActive = button.dataset.marginMode === settings.margin_mode;
    button.classList.toggle('is-active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });

  if (isTradingPaperAccount()) {
    paperHint.textContent = errorMessage || '本地模拟盘会按这里的杠杆和保证金模式估算占用保证金，并在平仓时回补盈亏。';
  } else {
    paperHint.textContent = errorMessage || '保存后会把杠杆和保证金模式同步到当前交易账户对应的交易所。';
  }
}

function renderTradingRuleSummary(errorMessage = '') {
  const badgeEl = document.getElementById('trading-market-badge');
  const titleEl = document.getElementById('trading-market-title');
  const subtitleEl = document.getElementById('trading-market-subtitle');
  const summaryEl = document.getElementById('trading-rule-summary');
  const helperEl = document.getElementById('trading-market-helper');
  if (!badgeEl || !titleEl || !subtitleEl || !summaryEl || !helperEl) return;

  const account = getTradingAccount();
  const exchangeLabel = account ? ({ binance: 'Binance', okx: 'OKX', huobi: 'HTX' }[account.exchange] || account.exchange) : '--';
  const envLabel = getTradingAccountEnvironmentLabel(account);
  const labels = getTradingSideLabels();
  const rules = tradingForm.symbolRules;
  const perp = rules ? rules.marketType === 'perp' : isTradingPerp();

  badgeEl.textContent = perp ? '永续合约' : '现货';
  badgeEl.className = `cq-trading-market-badge ${perp ? 'is-perp' : 'is-spot'}`;

  titleEl.textContent = rules ? rules.symbol.replace('.P', '').replace('USDT', '/USDT') : '等待选择交易对';
  subtitleEl.textContent = `${account?.isPaper ? '本地撮合' : exchangeLabel}${envLabel ? ` · ${envLabel}` : ''}${rules ? ` · ${rules.marketType === 'perp' ? '合约规则' : '现货规则'}` : ''}`;
  helperEl.textContent = errorMessage || labels.helper;

  if (!account) {
    summaryEl.innerHTML = '<div class="cq-trading-rule-empty">选择交易账户后，这里会显示该账户下交易所的最小下单量、步进和价格精度。</div>';
    return;
  }

  if (!rules) {
    summaryEl.innerHTML = `<div class="cq-trading-rule-empty">${errorMessage || '正在读取交易所规则...'}</div>`;
    return;
  }

  const minNotionalLabel = rules.marketType === 'perp' ? '名义价值参考' : '最小名义金额';
  summaryEl.innerHTML = `
    <div class="cq-trading-rule-grid">
      <div class="cq-trading-rule-item">
        <span>最小下单量</span>
        <strong>${escapeHtml(formatTradingNumber(rules.minQty))}${rules.quantityUnit === 'cont' ? ' 张' : ''}</strong>
      </div>
      <div class="cq-trading-rule-item">
        <span>数量步进</span>
        <strong>${escapeHtml(formatTradingNumber(rules.stepSize))}</strong>
      </div>
      <div class="cq-trading-rule-item">
        <span>${minNotionalLabel}</span>
        <strong>${escapeHtml(formatTradingNumber(rules.minNotional))}${rules.marketType === 'perp' ? '' : ' USDT'}</strong>
      </div>
      <div class="cq-trading-rule-item">
        <span>${account?.isPaper ? '成交方式' : '价格步进'}</span>
        <strong>${escapeHtml(formatTradingNumber(rules.tickSize))}</strong>
      </div>
    </div>
  `;
  if (account?.isPaper) {
    summaryEl.innerHTML = summaryEl.innerHTML.replace(
      `<strong>${escapeHtml(formatTradingNumber(rules.tickSize))}</strong>`,
      '<strong>本地即时模拟成交</strong>'
    );
  }
}

async function loadTradingSymbolRules() {
  syncTradingRuleInputs();
  renderTradingRuleSummary();

  if (!tradingForm.accountId || !tradingForm.symbol) {
    tradingForm.symbolRules = null;
    renderTradingRuleSummary();
    return;
  }

  try {
    const rules = await api.getTradingSymbolRules(tradingForm.accountId, tradingForm.symbol);
    tradingForm.symbolRules = rules || null;
    syncTradingRuleInputs();
    renderTradingRuleSummary();
  } catch (err) {
    tradingForm.symbolRules = null;
    syncTradingRuleInputs();
    renderTradingRuleSummary(err.message || '交易规则读取失败');
  }
}

async function loadTradingContractSettings() {
  tradingForm.contractSettings = null;
  renderTradingContractSettings();

  if (!tradingForm.accountId || !isTradingPerp()) {
    renderTradingContractSettings();
    return;
  }

  try {
    const settings = await api.getContractSettings(tradingForm.accountId, tradingForm.symbol);
    tradingForm.contractSettings = settings || null;
    renderTradingContractSettings();
  } catch (err) {
    tradingForm.contractSettings = { leverage: 10, margin_mode: 'cross' };
    renderTradingContractSettings(err.message || '合约设置读取失败');
  }
}

function setTradingMarginMode(marginMode) {
  if (!tradingForm.contractSettings) {
    tradingForm.contractSettings = { leverage: 10, margin_mode: marginMode };
  } else {
    tradingForm.contractSettings.margin_mode = marginMode;
  }
  renderTradingContractSettings();
}

async function saveTradingContractSettings() {
  if (!tradingForm.accountId || !isTradingPerp()) return;
  const leverageInput = document.getElementById('trading-leverage');
  const leverage = parseInt(leverageInput?.value, 10);
  const marginMode = tradingForm.contractSettings?.margin_mode || 'cross';

  if (!Number.isFinite(leverage) || leverage < 1 || leverage > 125) {
    showToast('请输入 1 到 125 之间的杠杆倍数', 'warn');
    leverageInput?.focus();
    return;
  }

  const button = document.getElementById('trading-contract-save-btn');
  const original = button?.innerHTML || '';
  if (button) {
    button.disabled = true;
    button.innerHTML = '保存中...';
  }

  try {
    const settings = await api.updateContractSettings(tradingForm.accountId, {
      symbol: tradingForm.symbol,
      leverage,
      marginMode,
    });
    tradingForm.contractSettings = settings || { leverage, margin_mode: marginMode };
    renderTradingContractSettings();
    showToast(isTradingPaperAccount() ? '本地模拟盘合约设置已保存' : '合约设置已同步到交易所', 'success');
    await refreshTradingData();
  } catch (err) {
    renderTradingContractSettings(err.message || '合约设置保存失败');
    showToast(err.message || '合约设置保存失败', 'error');
  } finally {
    if (button) {
      button.disabled = false;
      button.innerHTML = original;
    }
  }
}

function validateTradingForm() {
  const quantityInput = document.getElementById('trading-quantity');
  const priceInput = document.getElementById('trading-price');
  if (!quantityInput) return false;

  quantityInput.setCustomValidity('');
  if (priceInput) priceInput.setCustomValidity('');

  const quantity = normalizeDecimalString(quantityInput.value);
  if (!quantity || compareDecimalStrings(quantity, '0') <= 0) {
    quantityInput.setCustomValidity('请输入有效数量');
    quantityInput.reportValidity();
    return false;
  }

  const rules = tradingForm.symbolRules;
  if (rules?.minQty && compareDecimalStrings(quantity, rules.minQty) < 0) {
    quantityInput.setCustomValidity(`最小下单量为 ${formatTradingNumber(rules.minQty)}${rules.quantityUnit === 'cont' ? ' 张' : ''}`);
    quantityInput.reportValidity();
    return false;
  }

  if (rules?.stepSize && rules.stepSize !== '0' && !isDecimalMultiple(quantity, rules.stepSize)) {
    quantityInput.setCustomValidity(`数量必须按 ${formatTradingNumber(rules.stepSize)} 的步进输入`);
    quantityInput.reportValidity();
    return false;
  }

  if (tradingForm.orderType === 'limit' && priceInput) {
    const price = normalizeDecimalString(priceInput.value);
    if (!price || compareDecimalStrings(price, '0') <= 0) {
      priceInput.setCustomValidity('限价单请输入有效价格');
      priceInput.reportValidity();
      return false;
    }
    if (rules?.tickSize && rules.tickSize !== '0' && !isDecimalMultiple(price, rules.tickSize)) {
      priceInput.setCustomValidity(`价格必须按 ${formatTradingNumber(rules.tickSize)} 的步进输入`);
      priceInput.reportValidity();
      return false;
    }
  }

  return quantityInput.checkValidity() && (!priceInput || priceInput.checkValidity());
}

function isTradingTerminalOrderStatus(status) {
  return ['filled', 'cancelled', 'rejected', 'error'].includes(String(status || '').toLowerCase());
}

async function waitTradingRefresh(delayMs) {
  await new Promise((resolve) => window.setTimeout(resolve, delayMs));
}

async function pollRecentOrderStatus(accountId, createdOrder) {
  if (!createdOrder || isTradingPaperAccount()) return;

  const orderId = Number(createdOrder.id);
  if (!orderId) return;

  for (const delayMs of [800, 1500, 2500, 4000]) {
    await waitTradingRefresh(delayMs);

    const [positions, orders] = await Promise.all([
      api.getPositions(accountId).catch(() => []),
      api.getOrders({ accountId, limit: 50 }).catch(() => []),
    ]);

    renderTradingDataPanels(positions, orders);

    const currentOrder = orders.find((item) => Number(item.id) === orderId);
    if (currentOrder && isTradingTerminalOrderStatus(currentOrder.status)) {
      break;
    }
  }
}

async function submitOrder() {
  const accountSelect = document.getElementById('trading-account-select');
  const accountId = parseInt(accountSelect?.value, 10);
  if (!accountId) {
    showToast('请选择交易所账户', 'warn');
    return;
  }

  const symbol = tradingForm.symbol || 'BTCUSDT';
  const quantityInput = document.getElementById('trading-quantity');
  const priceInput = document.getElementById('trading-price');
  const quantity = quantityInput?.value || '';
  const price = tradingForm.orderType === 'limit' ? priceInput?.value : null;

  if (!validateTradingForm()) return;

  const btn = document.getElementById('trading-submit-btn');
  const labels = getTradingSideLabels();
  const sideLabel = tradingForm.side === 'buy' ? labels.submitBuy : labels.submitSell;
  btn.disabled = true;
  btn.dataset.loading = '1';
  const origHtml = btn.innerHTML;
  btn.innerHTML = `<svg class="cq-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg> ${sideLabel}中...`;

  try {
    const createdOrder = await api.createOrder({
      accountId,
      symbol,
      side: tradingForm.side,
      orderType: tradingForm.orderType,
      quantity,
      price,
    });
    const createdStatus = String(createdOrder?.status || '').toLowerCase();
    const successMessage = isTradingPaperAccount()
      ? `${sideLabel}已按本地模拟盘即时成交`
      : createdStatus === 'filled'
        ? `${sideLabel}订单已成交`
        : `${sideLabel}订单已提交`;
    showToast(successMessage, 'success');
    if (quantityInput) {
      quantityInput.value = '';
      quantityInput.setCustomValidity('');
    }
    await refreshTradingData();
    await pollRecentOrderStatus(accountId, createdOrder);
  } catch (err) {
    showToast('下单失败: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.dataset.loading = '0';
    btn.innerHTML = origHtml;
    updateTradingSubmitBtnLabel();
  }
}

async function refreshTradingData() {
  const accountId = tradingForm.accountId || parseInt(document.getElementById('trading-account-select')?.value, 10) || null;
  const [positions, orders] = await Promise.all([
    api.getPositions(accountId).catch(() => []),
    api.getOrders({ accountId, limit: 50 }).catch(() => []),
  ]);

  renderTradingDataPanels(positions, orders);
}

function renderTradingDataPanels(positions, orders) {
  renderTradingPositions(positions);
  renderTradingOrders(
    orders.filter((item) => ['pending', 'submitted', 'partial'].includes(String(item.status || '').toLowerCase())),
    {
      targetId: 'trading-open-orders',
      emptyTitle: '暂无当前订单',
      allowCancel: true,
    }
  );
  renderTradingOrders(
    orders.filter((item) => String(item.status || '').toLowerCase() === 'filled'),
    {
      targetId: 'trading-orders',
      emptyTitle: '暂无历史成交',
      allowCancel: false,
    }
  );
  setTradingBottomTab(tradingForm.bottomTab);
}

function formatTradingOrderbookValue(value, digits = 4) {
  const number = Number(value);
  if (!Number.isFinite(number)) return '--';
  if (Math.abs(number) >= 1000) {
    return number.toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }
  if (Math.abs(number) >= 1) return number.toFixed(Math.min(digits, 4));
  return number.toFixed(Math.min(Math.max(digits, 4), 6));
}

function renderTradingOrderbookRows(items, side) {
  if (!Array.isArray(items) || items.length === 0) {
    return '<div class="cq-market-orderbook__empty">暂无盘口数据</div>';
  }

  const maxQuantity = Math.max(...items.map((item) => Number(item.quantity || 0)), 0);
  return items.map((item) => {
    const price = Number(item.price || 0);
    const quantity = Number(item.quantity || 0);
    const depthWidth = maxQuantity > 0 ? Math.max((quantity / maxQuantity) * 100, 4) : 0;
    return `
      <div class="cq-market-orderbook__row cq-market-orderbook__row--${side}">
        <div class="cq-market-orderbook__depth" style="width:${depthWidth.toFixed(1)}%;"></div>
        <span class="cq-market-orderbook__price cq-num">${formatTradingOrderbookValue(price, 2)}</span>
        <span class="cq-market-orderbook__qty cq-num">${formatTradingOrderbookValue(quantity, 4)}</span>
      </div>
    `;
  }).join('');
}

function renderTradingOrderbook(orderbook) {
  const summaryEl = document.getElementById('trading-orderbook-summary');
  const bodyEl = document.getElementById('trading-orderbook-body');
  const metaEl = document.getElementById('trading-orderbook-meta');
  if (!summaryEl || !bodyEl) return;

  const bids = Array.isArray(orderbook?.bids) ? [...orderbook.bids].slice(0, 12) : [];
  const asks = Array.isArray(orderbook?.asks) ? [...orderbook.asks].slice(0, 12) : [];
  const bestBid = Number(bids[0]?.price || 0);
  const bestAsk = Number(asks[0]?.price || 0);
  const spread = bestBid > 0 && bestAsk > 0 ? bestAsk - bestBid : null;
  const spreadPct = spread != null && bestBid > 0 ? (spread / bestBid) * 100 : null;
  const bidTotal = bids.reduce((sum, item) => sum + Number(item.quantity || 0), 0);
  const askTotal = asks.reduce((sum, item) => sum + Number(item.quantity || 0), 0);

  summaryEl.innerHTML = `
    <div class="cq-market-orderbook__metric">
      <span>买一 / 卖一</span>
      <strong class="cq-num">${bestBid ? formatTradingOrderbookValue(bestBid, 2) : '--'} / ${bestAsk ? formatTradingOrderbookValue(bestAsk, 2) : '--'}</strong>
    </div>
    <div class="cq-market-orderbook__metric">
      <span>点差</span>
      <strong class="cq-num">${spread == null ? '--' : formatTradingOrderbookValue(spread, 4)}</strong>
      <em>${spreadPct == null ? '' : `${spreadPct.toFixed(3)}%`}</em>
    </div>
    <div class="cq-market-orderbook__metric">
      <span>深度合计</span>
      <strong class="cq-num">${formatTradingOrderbookValue(bidTotal, 4)} / ${formatTradingOrderbookValue(askTotal, 4)}</strong>
      <em>买 / 卖</em>
    </div>
  `;

  bodyEl.innerHTML = `
    <div class="cq-market-orderbook__section">
      <div class="cq-market-orderbook__section-head">
        <span>卖盘</span>
        <span>价格 / 数量</span>
      </div>
      <div class="cq-market-orderbook__rows">${renderTradingOrderbookRows([...asks].reverse(), 'ask')}</div>
    </div>
    <div class="cq-market-orderbook__spread">
      <span class="cq-tag cq-tag--neutral">${escapeHtml((getTradingAccountExchange() || '--').toUpperCase())}</span>
      <span class="cq-tag ${isTradingPerp() ? 'cq-tag--warn' : 'cq-tag--info'}">${isTradingPerp() ? '永续' : '现货'}</span>
    </div>
    <div class="cq-market-orderbook__section">
      <div class="cq-market-orderbook__section-head">
        <span>买盘</span>
        <span>价格 / 数量</span>
      </div>
      <div class="cq-market-orderbook__rows">${renderTradingOrderbookRows(bids, 'bid')}</div>
    </div>
  `;

  if (metaEl) {
    metaEl.textContent = `更新于 ${new Date().toLocaleTimeString('zh-CN', { hour12: false })}`;
  }
}

async function loadTradingOrderbook() {
  const bodyEl = document.getElementById('trading-orderbook-body');
  const summaryEl = document.getElementById('trading-orderbook-summary');
  const metaEl = document.getElementById('trading-orderbook-meta');
  if (!bodyEl || !summaryEl) return;

  if (!tradingForm.symbol || !getTradingAccountExchange()) {
    summaryEl.innerHTML = '';
    bodyEl.innerHTML = '<div class="cq-market-orderbook__empty">选择账户和交易对后显示订单簿</div>';
    if (metaEl) metaEl.textContent = '';
    return;
  }

  bodyEl.innerHTML = '<div class="cq-skeleton" style="height:240px;border-radius:12px;"></div>';
  summaryEl.innerHTML = '';

  try {
    const orderbook = await api.getOrderbook(
      tradingForm.symbol.replace('.P', ''),
      12,
      getTradingAccountExchange(),
      isTradingPerp() ? 'perp' : 'spot'
    );
    renderTradingOrderbook(orderbook);
  } catch (err) {
    bodyEl.innerHTML = `<div class="cq-market-orderbook__empty">${escapeHtml(err.message || '订单簿读取失败')}</div>`;
    if (metaEl) metaEl.textContent = '';
  }
}

function stopTradingOrderbookPolling() {
  if (tradingOrderbookTimer) {
    clearInterval(tradingOrderbookTimer);
    tradingOrderbookTimer = null;
  }
}

function startTradingOrderbookPolling() {
  stopTradingOrderbookPolling();
  loadTradingOrderbook().catch(() => {});
  tradingOrderbookTimer = setInterval(() => {
    const page = document.getElementById('page-trading');
    if (!page || !page.classList.contains('active')) return;
    loadTradingOrderbook().catch(() => {});
  }, 5000);
}

/* ── 持仓列表（带操作按钮） ── */
function renderTradingPositions(positions) {
  const el = document.getElementById('trading-positions');
  if (!el) return;

  if (!positions || positions.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-6);"><h3>暂无持仓</h3></div>`;
    return;
  }

  el.innerHTML = `
    <div class="cq-card" style="padding:0;overflow:hidden;">
      <div class="cq-table-wrap">
      <table class="cq-table">
        <thead>
          <tr>
            <th>交易对</th>
            <th>方向</th>
            <th>数量</th>
            <th>开仓价</th>
            <th>现价</th>
            <th>杠杆</th>
            <th>未实现盈亏</th>
            <th>止损</th>
            <th>止盈</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${positions.map(p => {
            const pnl = p.unrealizedPnl ?? p.unrealized_pnl ?? 0;
            const pnlPct = p.unrealizedPnlPercent ?? p.unrealized_pnl_percent ?? 0;
            const sl = p.stopLoss ?? p.stop_loss ?? null;
            const tp = p.takeProfit ?? p.take_profit ?? null;
            const posId = p.id;
            const accountId = p.accountId ?? p.account_id ?? '';
            return `
            <tr>
              <td style="font-weight:600;">${escapeHtml(p.symbol)}</td>
              <td><span class="cq-tag ${p.side === 'long' ? 'cq-tag--profit' : 'cq-tag--loss'}">${p.side === 'long' ? '多' : '空'}</span></td>
              <td class="cq-num">${p.quantity}</td>
              <td class="cq-num">$${formatNum(p.entryPrice ?? p.entry_price)}</td>
              <td class="cq-num">$${formatNum(p.currentPrice ?? p.current_price)}</td>
              <td class="cq-num">${String(p.symbol || '').endsWith('.P') ? `${p.leverage || 1}x` : '--'}</td>
              <td class="cq-num" style="color:${pnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};font-weight:600;">${pnl >= 0 ? '+' : ''}$${formatNum(pnl)}</td>
              <td class="cq-num" style="color:var(--cq-color-loss);font-size:var(--cq-text-sm);">${sl ? '$' + Number(sl).toFixed(2) : '--'}</td>
              <td class="cq-num" style="color:var(--cq-color-profit);font-size:var(--cq-text-sm);">${tp ? '$' + Number(tp).toFixed(2) : '--'}</td>
              <td style="white-space:nowrap;">
                <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="showSlTpDialog(${posId}, ${accountId})" title="设置止损止盈">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </button>
                <button class="cq-btn cq-btn--danger cq-btn--sm" onclick="closePositionAction(${posId}, ${accountId})" title="平仓">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>
    </div>

    <div style="margin-top:var(--cq-space-3);display:flex;justify-content:flex-end;">
      <button class="cq-btn cq-btn--danger" onclick="emergencyCloseAllAction()" style="font-size:var(--cq-text-sm);">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        紧急一键平仓
      </button>
    </div>`;
}

/* ── 订单历史 ── */
function renderTradingOrders(orders, options = {}) {
  const {
    targetId = 'trading-orders',
    emptyTitle = '暂无订单记录',
    allowCancel = true,
  } = options;
  const el = document.getElementById(targetId);
  if (!el) return;

  if (!orders || orders.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-6);"><h3>${escapeHtml(emptyTitle)}</h3></div>`;
    return;
  }

  const statusMap = {
    pending: '<span class="cq-tag cq-tag--warn">待提交</span>',
    submitted: '<span class="cq-tag cq-tag--info">已提交</span>',
    partial: '<span class="cq-tag cq-tag--info">部分成交</span>',
    filled: '<span class="cq-tag cq-tag--profit">已成交</span>',
    cancelled: '<span class="cq-tag cq-tag--neutral">已取消</span>',
    rejected: '<span class="cq-tag cq-tag--loss">已拒绝</span>',
    error: '<span class="cq-tag cq-tag--loss">异常</span>',
  };

  el.innerHTML = `
    <div class="cq-card" style="padding:0;overflow:hidden;">
      <div class="cq-table-wrap">
      <table class="cq-table">
        <thead>
          <tr>
            <th>交易对</th>
            <th>方向</th>
            <th>类型</th>
            <th style="text-align:right;">数量</th>
            <th style="text-align:right;">委托价</th>
            <th style="text-align:right;">已成交</th>
            <th style="text-align:right;">成交均价</th>
            <th style="text-align:right;">成交额</th>
            <th>状态</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${orders.slice(0, 50).map(o => {
            const status = (o.status || '').toLowerCase();
            const statusHtml = statusMap[status] || `<span class="cq-tag cq-tag--neutral">${escapeHtml(o.status)}</span>`;
            const time = o.createdAt || o.created_at || '';
            const timeStr = time ? time.substring(0, 16).replace('T', ' ') : '--';
            const canCancel = allowCancel && ['pending', 'submitted', 'partial'].includes(status);
            const orderType = o.orderType || o.order_type || '--';
            const side = String(o.side || '').toLowerCase();
            const isPerpOrder = String(o.symbol || '').toUpperCase().endsWith('.P');
            const sideLabel = isPerpOrder
              ? (side === 'buy' ? '开多' : side === 'sell' ? '开空' : (o.side || '--'))
              : (side === 'buy' ? '买入' : side === 'sell' ? '卖出' : (o.side || '--'));
            const filledQuantity = o.filledQuantity ?? o.filled_quantity ?? null;
            const avgFillPrice = o.avgFillPrice ?? o.avg_fill_price ?? null;
            const orderValue = o.orderValue ?? o.order_value ?? null;
            const exchangeOrderId = o.exchangeOrderId || o.exchange_order_id || '';
            const errorMessage = o.errorMessage || o.error_message || '';
            const statusDetail = errorMessage
              ? `<div style="margin-top:4px;color:var(--cq-color-loss);font-size:var(--cq-text-xs);line-height:1.4;">${escapeHtml(errorMessage)}</div>`
              : exchangeOrderId
                ? `<div style="margin-top:4px;color:var(--cq-text-tertiary);font-size:var(--cq-text-xs);line-height:1.4;">#${escapeHtml(exchangeOrderId)}</div>`
                : '';
            return `
            <tr>
              <td style="font-weight:600;">${escapeHtml(o.symbol)}</td>
              <td><span class="cq-tag ${side === 'buy' ? 'cq-tag--profit' : 'cq-tag--loss'}">${sideLabel}</span></td>
              <td style="color:var(--cq-text-secondary);">${orderType}</td>
              <td class="cq-num" style="text-align:right;">${o.quantity || '--'}</td>
              <td class="cq-num" style="text-align:right;">${o.price ? '$' + Number(o.price).toFixed(2) : '--'}</td>
              <td class="cq-num" style="text-align:right;">${filledQuantity && Number(filledQuantity) > 0 ? formatTradingNumber(filledQuantity) : '--'}</td>
              <td class="cq-num" style="text-align:right;">${avgFillPrice ? '$' + formatNum(avgFillPrice) : '--'}</td>
              <td class="cq-num" style="text-align:right;">${orderValue && Number(orderValue) > 0 ? '$' + formatNum(orderValue) : '--'}</td>
              <td>${statusHtml}${statusDetail}</td>
              <td style="color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">${timeStr}</td>
              <td>${canCancel ? `<button class="cq-btn cq-btn--danger cq-btn--sm" onclick="cancelOrderAction(${o.id})">撤单</button>` : ''}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>
    </div>`;
}

/* ── 持仓操作：止损止盈弹窗 ── */
function showSlTpDialog(positionId, accountId) {
  const el = document.getElementById('sltp-dialog');
  if (!el) return;
  el.dataset.positionId = positionId;
  el.dataset.accountId = accountId;
  el.classList.add('is-visible');
  // 清空输入
  const slInput = document.getElementById('sltp-stop-price');
  const tpInput = document.getElementById('sltp-take-price');
  if (slInput) slInput.value = '';
  if (tpInput) tpInput.value = '';
}

function closeSlTpDialog() {
  const el = document.getElementById('sltp-dialog');
  if (el) el.classList.remove('is-visible');
}

async function submitSlTp() {
  const el = document.getElementById('sltp-dialog');
  const positionId = el?.dataset.positionId;
  const accountId = el?.dataset.accountId;
  const stopPrice = document.getElementById('sltp-stop-price')?.value;
  const takePrice = document.getElementById('sltp-take-price')?.value;

  try {
    const results = [];
    if (stopPrice && parseFloat(stopPrice) > 0) {
      await api.setStopLoss(positionId, accountId, stopPrice);
      results.push('止损');
    }
    if (takePrice && parseFloat(takePrice) > 0) {
      await api.setTakeProfit(positionId, accountId, takePrice);
      results.push('止盈');
    }
    if (results.length > 0) {
      showToast(results.join(' / ') + '已设置', 'success');
    }
    closeSlTpDialog();
    refreshTradingData();
  } catch (err) {
    showToast('设置失败: ' + err.message, 'error');
  }
}

/* ── 平仓 ── */
async function closePositionAction(positionId, accountId) {
  if (!confirm('确认平仓此仓位？')) return;
  if (!accountId) {
    showToast('无法识别仓位所属账户，平仓失败', 'error');
    return;
  }
  try {
    await api.closePosition(positionId, accountId);
    showToast('平仓成功', 'success');
    refreshTradingData();
  } catch (err) {
    showToast('平仓失败: ' + err.message, 'error');
  }
}

/* ── 紧急一键平仓 ── */
async function emergencyCloseAllAction() {
  if (!confirm('⚠️ 确认紧急平仓所有仓位？此操作不可撤销！')) return;
  const accountSelect = document.getElementById('trading-account-select');
  const accountId = parseInt(accountSelect?.value);
  if (!accountId) {
    showToast('请先选择交易所账户', 'warn');
    return;
  }
  try {
    const result = await api.emergencyCloseAll(accountId);
    showToast(`已平仓 ${result.closed_count || 0} 个仓位`, 'success');
    refreshTradingData();
  } catch (err) {
    showToast('紧急平仓失败: ' + err.message, 'error');
  }
}

/* ── 撤单 ── */
async function cancelOrderAction(orderId) {
  if (!confirm('确认撤销此订单？')) return;
  try {
    await api.cancelOrder(orderId);
    showToast('撤单成功', 'success');
    refreshTradingData();
  } catch (err) {
    showToast('撤单失败: ' + err.message, 'error');
  }
}
