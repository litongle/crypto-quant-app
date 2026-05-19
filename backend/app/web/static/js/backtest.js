'use strict';

/**
 * 回测页面逻辑 v2 — 使用设计令牌
 */

/** 本地日期 YYYY-MM-DD（避免 toISOString 的 UTC 时区偏差） */
function localDate(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

async function loadBacktestPage() {
  if (typeof preloadSymbolSelectorData === 'function') {
    await preloadSymbolSelectorData();
  }

  // 设置默认日期（动态，不过期）
  const startEl = document.getElementById('backtest-start');
  const endEl = document.getElementById('backtest-end');
  const today = localDate();
  if (endEl && !endEl.value) {
    endEl.value = today;
  }
  if (startEl && !startEl.value) {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    startEl.value = localDate(d);
  }
  // 限制日期不能选未来
  if (startEl) startEl.max = today;
  if (endEl) endEl.max = today;

  // 初始化交易对选择器（只创建一次）
  if (!App.state.backtestSymbolSel) {
    const selEl = document.getElementById('backtest-symbol-selector');
    if (selEl) {
      App.state.backtestSymbolSel = new SymbolSelector({
        containerId: 'backtest-symbol-selector',
        value: 'BTCUSDT',
        // 切币种时重渲参数面板：spot ↔ perp 切换决定是否显示 perp-only 参数
        onChange: () => {
          if (App.state.backtestCurrentParams) {
            renderBacktestParamControls(App.state.backtestCurrentParams);
          }
        },
      });
    }
  } else if (typeof App.state.backtestSymbolSel.refreshData === 'function') {
    App.state.backtestSymbolSel.refreshData();
  }

  try {
    const [templates, instances] = await Promise.all([
      api.getStrategyTemplates(),
      api.getStrategyInstances('all').catch(() => []),
    ]);
    App.state.backtestTemplates = templates;
    App.state.backtestInstances = Array.isArray(instances) ? instances : [];
    renderBacktestTemplateSelect(templates, App.state.backtestInstances);
  } catch {
    document.getElementById('backtest-template-select').innerHTML = '<option value="">加载失败</option>';
  }
  try {
    const history = await api.getBacktestHistory(50);
    renderBacktestHistory(history);
  } catch {}
}

const BT_RULE_INDICATORS = [
  { key: 'price', name: '当前价格', type: 'value', params: [] },
  { key: 'sma', name: 'SMA', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'ema', name: 'EMA', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'dema', name: 'DEMA', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'rsi', name: 'RSI', type: 'value', params: [{ key: 'period', name: '周期', default: 14, min: 2, max: 100, type: 'int' }] },
  { key: 'macd', name: 'MACD', type: 'value', params: [] },
  { key: 'stoch_k', name: 'Stoch K', type: 'value', params: [{ key: 'period', name: '周期', default: 14, min: 2, max: 100, type: 'int' }] },
  { key: 'stoch_d', name: 'Stoch D', type: 'value', params: [{ key: 'period', name: '周期', default: 3, min: 1, max: 50, type: 'int' }] },
  { key: 'cci', name: 'CCI', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 100, type: 'int' }] },
  { key: 'obv', name: 'OBV', type: 'value', params: [] },
  { key: 'atr', name: 'ATR', type: 'value', params: [{ key: 'period', name: '周期', default: 14, min: 2, max: 100, type: 'int' }] },
  { key: 'volume_ma', name: '成交量MA', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'boll_mid', name: 'BOLL中轨', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'boll_upper', name: 'BOLL上轨', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'boll_lower', name: 'BOLL下轨', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'bollinger_pct', name: 'BOLL位置%', type: 'value', params: [{ key: 'period', name: '周期', default: 20, min: 2, max: 300, type: 'int' }] },
  { key: 'price_change_pct', name: '价格涨跌幅%', type: 'value', params: [{ key: 'period', name: '周期', default: 1, min: 1, max: 100, type: 'int' }] },
];

const BT_VALUE_OPERATORS = [
  { key: '>', name: '>' },
  { key: '<', name: '<' },
  { key: '>=', name: '>=' },
  { key: '<=', name: '<=' },
];

let _backtestRuleState = {
  buyRules: [],
  sellRules: [],
  buyLogic: 'AND',
  sellLogic: 'AND',
  stopLossPct: 3,
  takeProfitPct: 6,
  confidenceBase: 0.7,
  _nextId: 1,
};

function resetBacktestRuleState() {
  _backtestRuleState = {
    buyRules: [],
    sellRules: [],
    buyLogic: 'AND',
    sellLogic: 'AND',
    stopLossPct: 3,
    takeProfitPct: 6,
    confidenceBase: 0.7,
    _nextId: 1,
  };
}

function newBacktestRuleCondition(indicatorKey = 'price') {
  const indicator = BT_RULE_INDICATORS.find(i => i.key === indicatorKey) || BT_RULE_INDICATORS[0];
  const params = {};
  indicator.params.forEach(p => { params[p.key] = p.default; });
  return {
    id: _backtestRuleState._nextId++,
    indicator: indicator.key,
    params,
    operator: '>',
    value: 0,
  };
}

function renderBacktestRuleBuilder() {
  const el = document.getElementById('backtest-params');
  if (!el) return;
  el.innerHTML = `
    <div class="cq-rule-builder">
      <div class="cq-rule-section">
        <div class="cq-rule-section__header">
          <span>买入条件</span>
          <div class="cq-rule-logic-toggle">
            <button class="cq-logic-btn${_backtestRuleState.buyLogic === 'AND' ? ' is-active' : ''}" onclick="setBacktestRuleLogic('buy','AND')">AND</button>
            <button class="cq-logic-btn${_backtestRuleState.buyLogic === 'OR' ? ' is-active' : ''}" onclick="setBacktestRuleLogic('buy','OR')">OR</button>
          </div>
        </div>
        <div class="cq-rule-conditions" id="bt-rule-buy-conditions"></div>
        <button class="cq-btn cq-btn--secondary cq-btn--sm cq-add-condition-btn" onclick="addBacktestRuleCondition('buy')">添加买入条件</button>
      </div>

      <div class="cq-rule-section">
        <div class="cq-rule-section__header">
          <span>卖出条件</span>
          <div class="cq-rule-logic-toggle">
            <button class="cq-logic-btn${_backtestRuleState.sellLogic === 'AND' ? ' is-active' : ''}" onclick="setBacktestRuleLogic('sell','AND')">AND</button>
            <button class="cq-logic-btn${_backtestRuleState.sellLogic === 'OR' ? ' is-active' : ''}" onclick="setBacktestRuleLogic('sell','OR')">OR</button>
          </div>
        </div>
        <div class="cq-rule-conditions" id="bt-rule-sell-conditions"></div>
        <button class="cq-btn cq-btn--secondary cq-btn--sm cq-add-condition-btn" onclick="addBacktestRuleCondition('sell')">添加卖出条件</button>
      </div>

      <div class="cq-rule-section">
        <div class="cq-rule-section__header"><span>风控参数</span></div>
        <div class="cq-rule-risk-grid">
          <div class="cq-param-group">
            <div class="cq-param-header">
              <label class="cq-param-label" for="slr-bt-stopLossPct">止损 %</label>
              <span class="cq-param-value" id="val-bt-stopLossPct">${_backtestRuleState.stopLossPct}</span>
            </div>
            <input type="range" class="cq-slider" id="slr-bt-stopLossPct" min="0.5" max="20" step="0.5" value="${_backtestRuleState.stopLossPct}"
              oninput="document.getElementById('val-bt-stopLossPct').textContent=this.value; _backtestRuleState.stopLossPct=parseFloat(this.value)">
          </div>
          <div class="cq-param-group">
            <div class="cq-param-header">
              <label class="cq-param-label" for="slr-bt-takeProfitPct">止盈 %</label>
              <span class="cq-param-value" id="val-bt-takeProfitPct">${_backtestRuleState.takeProfitPct}</span>
            </div>
            <input type="range" class="cq-slider" id="slr-bt-takeProfitPct" min="1" max="50" step="1" value="${_backtestRuleState.takeProfitPct}"
              oninput="document.getElementById('val-bt-takeProfitPct').textContent=this.value; _backtestRuleState.takeProfitPct=parseFloat(this.value)">
          </div>
          <div class="cq-param-group">
            <div class="cq-param-header">
              <label class="cq-param-label" for="slr-bt-confidenceBase">信号置信度</label>
              <span class="cq-param-value" id="val-bt-confidenceBase">${Math.round(_backtestRuleState.confidenceBase * 100)}%</span>
            </div>
            <input type="range" class="cq-slider" id="slr-bt-confidenceBase" min="0.1" max="1.0" step="0.05" value="${_backtestRuleState.confidenceBase}"
              oninput="document.getElementById('val-bt-confidenceBase').textContent=Math.round(this.value*100)+'%'; _backtestRuleState.confidenceBase=parseFloat(this.value)">
          </div>
        </div>
      </div>
    </div>
  `;

  renderBacktestRuleConditions('buy');
  renderBacktestRuleConditions('sell');
}

function renderBacktestRuleConditions(side) {
  const container = document.getElementById(`bt-rule-${side}-conditions`);
  if (!container) return;
  const conditions = side === 'buy' ? _backtestRuleState.buyRules : _backtestRuleState.sellRules;
  if (conditions.length === 0) {
    container.innerHTML = '<div class="cq-rule-empty">尚未添加条件，点击下方按钮添加</div>';
    return;
  }

  container.innerHTML = conditions.map(cond => {
    const indicator = BT_RULE_INDICATORS.find(i => i.key === cond.indicator) || BT_RULE_INDICATORS[0];
    const paramInputs = indicator.params.map(p => {
      const val = cond.params[p.key] ?? p.default;
      return `<div class="cq-cond-param">
        <span class="cq-cond-param__label">${p.name}</span>
        <input type="number" class="cq-input cq-cond-param__input" value="${val}" min="${p.min || ''}" max="${p.max || ''}" step="${p.type === 'int' ? 1 : 0.1}" onchange="updateBacktestCondParam('${side}',${cond.id},'${p.key}',this.value)">
      </div>`;
    }).join('');

    return `
      <div class="cq-rule-condition" data-cond-id="${cond.id}">
        <div class="cq-cond-row">
          <select class="cq-input cq-cond-indicator" onchange="changeBacktestCondIndicator('${side}',${cond.id},this.value)">
            ${BT_RULE_INDICATORS.map(i => `<option value="${i.key}" ${i.key === cond.indicator ? 'selected' : ''}>${i.name}</option>`).join('')}
          </select>
          <select class="cq-input cq-cond-operator" onchange="updateBacktestCondOperator('${side}',${cond.id},this.value)">
            ${BT_VALUE_OPERATORS.map(o => `<option value="${o.key}" ${o.key === cond.operator ? 'selected' : ''}>${o.name}</option>`).join('')}
          </select>
          <input type="number" class="cq-input cq-cond-value" value="${cond.value}" step="any" placeholder="阈值" onchange="updateBacktestCondValue('${side}',${cond.id},this.value)">
          <button class="cq-cond-remove" onclick="removeBacktestRuleCondition('${side}',${cond.id})" title="删除条件">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        ${paramInputs ? `<div class="cq-cond-params">${paramInputs}</div>` : ''}
      </div>
    `;
  }).join('');
}

function addBacktestRuleCondition(side) {
  const cond = newBacktestRuleCondition('price');
  if (side === 'buy') _backtestRuleState.buyRules.push(cond);
  else _backtestRuleState.sellRules.push(cond);
  renderBacktestRuleConditions(side);
}

function removeBacktestRuleCondition(side, condId) {
  if (side === 'buy') _backtestRuleState.buyRules = _backtestRuleState.buyRules.filter(c => c.id !== condId);
  else _backtestRuleState.sellRules = _backtestRuleState.sellRules.filter(c => c.id !== condId);
  renderBacktestRuleConditions(side);
}

function changeBacktestCondIndicator(side, condId, indicatorKey) {
  const list = side === 'buy' ? _backtestRuleState.buyRules : _backtestRuleState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (!cond) return;
  const indicator = BT_RULE_INDICATORS.find(i => i.key === indicatorKey) || BT_RULE_INDICATORS[0];
  cond.indicator = indicator.key;
  cond.params = {};
  indicator.params.forEach(p => { cond.params[p.key] = p.default; });
  cond.operator = '>';
  cond.value = 0;
  renderBacktestRuleConditions(side);
}

function updateBacktestCondOperator(side, condId, operator) {
  const list = side === 'buy' ? _backtestRuleState.buyRules : _backtestRuleState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (cond) cond.operator = operator;
}

function updateBacktestCondValue(side, condId, value) {
  const list = side === 'buy' ? _backtestRuleState.buyRules : _backtestRuleState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (cond) cond.value = parseFloat(value) || 0;
}

function updateBacktestCondParam(side, condId, paramKey, value) {
  const list = side === 'buy' ? _backtestRuleState.buyRules : _backtestRuleState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (cond) cond.params[paramKey] = parseFloat(value) || 0;
}

function setBacktestRuleLogic(side, logic) {
  if (side === 'buy') _backtestRuleState.buyLogic = logic;
  else _backtestRuleState.sellLogic = logic;
  renderBacktestRuleBuilder();
}

function buildBacktestRulesDSL() {
  function buildGroup(conditions, logic) {
    return {
      logic,
      conditions: conditions.map(c => ({
        indicator: c.indicator,
        params: { ...c.params },
        operator: c.operator,
        value: c.value,
      })),
    };
  }
  return {
    buy_rules: buildGroup(_backtestRuleState.buyRules, _backtestRuleState.buyLogic),
    sell_rules: buildGroup(_backtestRuleState.sellRules, _backtestRuleState.sellLogic),
    risk: {
      stop_loss_percent: _backtestRuleState.stopLossPct,
      take_profit_percent: _backtestRuleState.takeProfitPct,
      confidence_base: _backtestRuleState.confidenceBase,
    },
  };
}

function renderBacktestTemplateSelect(templates, instances = []) {
  const sel = document.getElementById('backtest-template-select');
  const templateById = new Map((templates || []).map(t => [t.id, t]));
  const templateOpts = (templates || [])
    .map(t => `<option value="tmpl:${t.id}" data-kind="template" data-template-id="${t.id}">${escapeHtml(t.name)}</option>`)
    .join('');
  const instanceOpts = (instances || [])
    .map(inst => {
      const tmplName = templateById.get(inst.templateId)?.name || inst.templateName || inst.templateId;
      const label = `${inst.name} · ${tmplName}`;
      return `<option value="inst:${inst.id}" data-kind="instance" data-instance-id="${inst.id}" data-template-id="${inst.templateId}">${escapeHtml(label)}</option>`;
    })
    .join('');
  const groups = [
    `<optgroup label="策略模板">${templateOpts}</optgroup>`,
    instanceOpts ? `<optgroup label="我的策略">${instanceOpts}</optgroup>` : '',
  ].join('');
  sel.innerHTML = '<option value="">选择策略 / 模板</option>' + groups;
}

/** 解析当前选中的下拉项，统一成 {kind, templateId, instanceId, instance} 形态。 */
function _getSelectedBacktestSource() {
  const sel = document.getElementById('backtest-template-select');
  const opt = sel?.selectedOptions?.[0];
  if (!opt || !opt.value) return null;
  const kind = opt.dataset.kind;
  const templateId = opt.dataset.templateId;
  if (kind === 'instance') {
    const instanceId = parseInt(opt.dataset.instanceId, 10);
    const instance = (App.state.backtestInstances || []).find(i => i.id === instanceId);
    return { kind: 'instance', templateId, instanceId, instance };
  }
  return { kind: 'template', templateId };
}

async function runBacktest() {
  const source = _getSelectedBacktestSource();
  if (!source) { showToast('请选择策略模板或我的策略', 'warn'); return; }
  const templateId = source.templateId;

  const symbolValue = App.state.backtestSymbolSel ? App.state.backtestSymbolSel.getValue() : 'BTCUSDT';
  const parsedSymbol = (typeof splitMarket === 'function')
    ? splitMarket(symbolValue)
    : { symbol: symbolValue, market: 'spot' };
  const symbol = parsedSymbol.symbol;
  const market = parsedSymbol.market || 'spot';
  const startDate = document.getElementById('backtest-start').value || (() => { const d = new Date(); d.setFullYear(d.getFullYear() - 1); return localDate(d); })();
  const endDate = document.getElementById('backtest-end').value || localDate();

  // 日期校验
  const today = localDate();
  if (startDate > endDate) { showToast('开始日期不能晚于结束日期', 'warn'); return; }
  if (endDate > today) { showToast('结束日期不能是未来日期', 'warn'); return; }
  if (startDate > today) { showToast('开始日期不能是未来日期', 'warn'); return; }

  // 交易对校验
  if (!symbol || !/^[A-Z0-9]{2,20}$/.test(symbol)) { showToast('请输入有效的交易对', 'warn'); return; }

  // 初始资金校验
  const initialCapital = parseFloat(document.getElementById('backtest-capital').value);
  if (isNaN(initialCapital) || initialCapital <= 0) { showToast('初始资金必须大于 0', 'warn'); return; }
  if (initialCapital > 1000000000) { showToast('初始资金不能超过 10 亿', 'warn'); return; }

  const awEl = document.getElementById('backtest-analysis-window');
  const awRaw = awEl ? String(awEl.value).trim() : '';
  let analysisWindow = undefined;
  if (awRaw !== '') {
    const aw = parseInt(awRaw, 10);
    if (!Number.isFinite(aw) || aw < 0) {
      showToast('策略K线窗口须为不小于 0 的整数', 'warn');
      return;
    }
    if (aw > 0) analysisWindow = aw;
  }

  // 日期跨度校验
  const daysDiff = Math.ceil((new Date(endDate) - new Date(startDate)) / 86400000);
  if (daysDiff > 3650) { showToast('回测跨度不能超过 10 年', 'warn'); return; }

  // K 线数量预估校验 — 避免用户白点等几十秒才报"数据不足"或"引擎超时"
  // 周期 → 每天 K 线数;rule_custom 跑前可能拿不到 kline_interval,跳过
  const interval = (() => {
    try { return collectBacktestParams().kline_interval; } catch { return null; }
  })();
  const barsPerDay = { '1m': 1440, '5m': 288, '15m': 96, '30m': 48, '1h': 24, '4h': 6, '1d': 1 };
  if (interval && barsPerDay[interval]) {
    const estBars = daysDiff * barsPerDay[interval];
    if (estBars < 50) {
      showToast(`该组合预计仅约 ${estBars} 根 K 线,不足 50 根,请增大日期范围或选更短周期`, 'warn');
      return;
    }
    // MAStrategy O(N²) 修复后实测速度 ~1500 bar/s, 引擎硬上限 120s × 1500 ≈ 18 万根。
    // 留余地 30% 阈值定 100000。低于此都能舒服跑完(43200 根 28s,远未到上限)。
    if (estBars > 100000) {
      const proceed = confirm(`该组合预计约 ${estBars} 根 K 线,数据量极大,回测引擎可能 120 秒超时。\n建议增大周期(如 ${interval} → 4h/1d)或缩小日期范围。\n仍要继续吗?`);
      if (!proceed) return;
    }
  }

  const selectedTemplate = (App.state.backtestTemplates || []).find(t => t.id === templateId);
  const isRuleTemplate = selectedTemplate?.strategyType === 'rule';
  let params = {};
  if (isRuleTemplate) {
    const buyEmpty = _backtestRuleState.buyRules.length === 0;
    const sellEmpty = _backtestRuleState.sellRules.length === 0;
    if (buyEmpty && sellEmpty) {
      showToast('请至少添加一个买入或卖出条件', 'warn');
      return;
    }
    params.rules = buildBacktestRulesDSL();
    // rule_custom 策略也带上选中的 K 线周期(若已选)
    try {
      const ki = collectBacktestParams().kline_interval;
      if (ki) params.kline_interval = ki;
    } catch {}
  } else {
    try {
      params = collectBacktestParams();
    } catch (e) {
      showToast(e.message, 'error');
      return;
    }
  }

  // 周期提示:优先用用户在策略参数里选的 kline_interval,否则按日期跨度自动选
  const intervalLabelMap = { '1m': '1分钟', '5m': '5分钟', '15m': '15分钟', '30m': '30分钟', '1h': '1小时', '4h': '4小时', '1d': '日线' };
  let intervalHint = '';
  if (params.kline_interval) {
    intervalHint = `（${intervalLabelMap[params.kline_interval] || params.kline_interval}级别）`;
  } else {
    const daysDiff = Math.ceil((new Date(endDate) - new Date(startDate)) / 86400000);
    if (daysDiff > 800) intervalHint = '（将使用日线级别）';
    else if (daysDiff > 200) intervalHint = '（将使用4小时级别）';
    else intervalHint = '（1小时级别）';
  }

  const btn = document.getElementById('run-backtest-btn');
  const resetBtn = () => {
    btn.disabled = false;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> 开始回测';
    _clearBacktestProgress();
  };
  btn.disabled = true;
  btn.innerHTML = '<svg class="cq-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg> 提交回测' + intervalHint + '...';

  try {
    const runPayload = {
      templateId,
      symbol,
      market,
      startDate,
      endDate,
      initialCapital,
      params,
    };
    if (analysisWindow !== undefined) runPayload.analysisWindow = analysisWindow;

    // 1. 提交后台任务，立刻拿 taskId
    const submission = await api.runBacktestAsync(runPayload);
    const taskId = submission?.taskId;
    if (!taskId) throw new Error('后端未返回 taskId');

    // 2. 渲染进度面板（含取消按钮）
    _renderBacktestProgress({ taskId, intervalHint });

    // 3. 轮询直到 completed / failed / cancelled
    const finalState = await _pollBacktestTask(taskId);

    if (finalState.status === 'completed') {
      const result = finalState.result || {};
      renderBacktestResults(result);
      const awHint = result.analysisWindow != null ? `, 窗口${result.analysisWindow}根` : ', 全量窗口';
      // elapsedSeconds 0 是合法值(引擎 <0.05s 被 round(0) 了),用 ?? 而不是 || 防误判;
      // < 0.1 显示 "<0.1" 比 "0" 更准确反映"快得测不出"
      const es = result.elapsedSeconds;
      const esText = (es == null) ? '?' : (es < 0.1 ? '<0.1' : es);
      const extra = result.interval ? ` (${result.interval}级别, ${result.klineCount}根K线, ${esText}秒${awHint})` : '';
      showToast('回测完成！' + extra, 'success');
    } else if (finalState.status === 'cancelled') {
      // 取消后保留之前的回测结果显示, toast 提示即可 — 用户取消是"放弃这次新跑",
      // 不应该让之前成功的结果消失
      showToast('回测已取消', 'warn');
    } else {
      // failed — 错误信息走 toast, 保留之前的结果区, 用户能继续看上次的数据
      const msg = finalState.error || '回测失败';
      showToast('回测失败: ' + msg, 'error');
    }
  } catch (err) {
    // 网络错误等异常,toast 提示后保留结果区
    showToast('回测失败: ' + err.message, 'error');
  } finally {
    resetBtn();
    // 进度面板用完即弃 — 不论 completed/failed/cancelled/exception 都清,
    // 避免"回测运行中..."一直留在页面上让用户以为还在跑
    _clearBacktestProgress();
  }
}

// ===== 异步回测：进度 UI + 轮询 =====
// 进度面板 DOM 直接挂在 #backtest-results 上方,不另起容器,简单也好清。
const _BACKTEST_POLL_INTERVAL_MS = 800;
const _STAGE_LABEL = {
  queued: '排队中',
  fetching_klines: '拉取 K 线数据',
  running_engine: '策略引擎运行中',
  saving: '保存结果',
  done: '完成',
};

function _renderBacktestProgress({ taskId, intervalHint }) {
  const host = document.getElementById('backtest-progress');
  if (!host) return;
  host.style.display = '';
  host.innerHTML = `
    <div class="cq-card" style="display:flex;flex-direction:column;gap:var(--cq-space-2);">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:var(--cq-space-3);">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);">
          <svg class="cq-spin" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg>
          <span id="backtest-progress-label" style="font-size:var(--cq-text-sm);font-weight:600;">回测运行中${escapeHtml(intervalHint || '')}</span>
        </div>
        <button type="button" id="backtest-cancel-btn" class="cq-btn cq-btn--ghost" style="padding:4px 12px;font-size:var(--cq-text-sm);">取消</button>
      </div>
      <progress id="backtest-progress-bar" value="0" max="100" style="width:100%;height:6px;"></progress>
      <div id="backtest-progress-stage" style="font-size:var(--cq-text-xs);color:var(--cq-text-secondary);">${escapeHtml(_STAGE_LABEL.queued)}</div>
    </div>
  `;
  const cancelBtn = document.getElementById('backtest-cancel-btn');
  if (cancelBtn) {
    cancelBtn.addEventListener('click', async () => {
      cancelBtn.disabled = true;
      cancelBtn.textContent = '取消中...';
      try {
        await api.cancelBacktestTask(taskId);
      } catch (e) {
        // 取消失败也让 poller 自己继续观察 — 状态会停在原样
        showToast('取消请求失败: ' + e.message, 'warn');
      }
    });
  }
}

function _updateBacktestProgress(state) {
  const bar = document.getElementById('backtest-progress-bar');
  const stage = document.getElementById('backtest-progress-stage');
  if (bar) bar.value = Number(state.progress || 0);
  if (stage) stage.textContent = _STAGE_LABEL[state.stage] || state.stage || '';
}

function _clearBacktestProgress() {
  const host = document.getElementById('backtest-progress');
  if (host) {
    host.innerHTML = '';
    host.style.display = 'none';
  }
}

async function _pollBacktestTask(taskId) {
  const TERMINAL = new Set(['completed', 'failed', 'cancelled']);
  // 兜底超时：服务端 service 自带 _BACKTEST_TIMEOUT (~120s)；前端给 5min 上限,
  // 跑过它直接当 failed 处理(避免 poller 永不退出)。
  const POLL_MAX_MS = 5 * 60 * 1000;
  const startedAt = Date.now();
  let lastState = null;

  // 立即拉一次,然后进入间隔轮询(用户体感快)
  while (true) {
    let state;
    try {
      state = await api.getBacktestTask(taskId);
    } catch (e) {
      // 404 / 网络瞬断 → 当作 failed 退出,避免死循环
      throw new Error(e.message || '查询任务状态失败');
    }
    lastState = state;
    _updateBacktestProgress(state);
    if (TERMINAL.has(state.status)) return state;
    if (Date.now() - startedAt > POLL_MAX_MS) {
      return { status: 'failed', error: '轮询超时(>5min),请稍后查看回测历史' };
    }
    await new Promise(r => setTimeout(r, _BACKTEST_POLL_INTERVAL_MS));
  }
  // unreachable
  // eslint-disable-next-line no-unreachable
  return lastState;
}

function renderBacktestResults(result) {
  const el = document.getElementById('backtest-results');

  const metrics = result.metrics || result;
  // 后端统一返回 camelCase；「总收益率」用百分比字段（与历史详情一致）
  const totalReturn =
    metrics.totalReturnPercent != null && metrics.totalReturnPercent !== ""
      ? Number(metrics.totalReturnPercent)
      : Number(metrics.totalReturn ?? 0);
  const maxDrawdown = metrics.maxDrawdown ?? 0;
  const sharpeRatio = metrics.sharpeRatio ?? 0;
  const winRate = metrics.winRate ?? 0;
  const totalTrades = metrics.totalTrades ?? 0;
  const profitFactor = metrics.profitFactor ?? 0;
  // 扩展指标
  const annualReturn = metrics.annualReturn ?? 0;
  const calmarRatio = metrics.calmarRatio ?? 0;
  const profitTrades = metrics.profitTrades ?? 0;
  const lossTrades = metrics.lossTrades ?? 0;
  const avgProfit = metrics.avgProfit ?? 0;
  const avgLoss = metrics.avgLoss ?? 0;
  const maxConWins = metrics.maxConsecutiveWins ?? 0;
  const maxConLosses = metrics.maxConsecutiveLosses ?? 0;
  const duration = metrics.duration ?? 0;
  const initialCapital = metrics.initialCapital ?? result.initialCapital ?? 100000;
  const finalCapital = metrics.finalCapital ?? result.finalCapital ?? 100000;
  const analysisWindowUsed = metrics.analysisWindow ?? result.analysisWindow;
  const trades = result.trades || [];
  const warning = result.warning || null;
  const analysisWindowLabel = analysisWindowUsed == null
    ? '全量前缀（第1根→当前）'
    : `最近 ${analysisWindowUsed} 根`;

  // 智能金额精度：极小本金 (10 USDT 跑 PEPE) 时 avgProfit 0.005 toFixed(2)
  // 会 round 成 0.01 误导，用 toPrecision 保留有效数字
  const fmtAmount = (v) => {
    if (v === 0) return '0.00';
    const abs = Math.abs(v);
    if (abs >= 1) return v.toFixed(2);
    if (abs >= 0.01) return v.toFixed(4);
    return v.toPrecision(2);
  };

  el.innerHTML = `
    ${warning ? `
    <div class="cq-alert cq-alert--warn" style="margin-bottom:var(--cq-space-4);padding:var(--cq-space-3);border:1px solid var(--cq-color-loss);border-radius:var(--cq-radius);background:rgba(239,68,68,0.08);display:flex;align-items:flex-start;gap:var(--cq-space-3);">
      <span style="font-size:18px;flex-shrink:0;line-height:1;">⚠️</span>
      <div>
        <div style="font-weight:600;color:var(--cq-color-loss);margin-bottom:4px;">数据警告</div>
        <div style="font-size:var(--cq-text-sm);color:var(--cq-text-secondary);">${escapeHtml(warning)}</div>
      </div>
    </div>` : ''}
    <div class="cq-grid-3" style="margin-bottom:var(--cq-space-4);">
      <div class="cq-card stat-card" title="(最终权益 - 初始资金) / 初始资金 × 100%">
        <div class="stat-label">总收益率</div>
        <div class="stat-value cq-num" style="color:${totalReturn >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%</div>
      </div>
      <div class="cq-card stat-card" title="年化收益率 / 年化波动率。>1 良好，>2 优秀；小样本下数值不稳定，已 cap 到 ±10">
        <div class="stat-label">夏普比率</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-primary);">${sharpeRatio.toFixed(2)}</div>
      </div>
      <div class="cq-card stat-card" title="权益曲线从历史峰值的最大跌幅%。越小越稳健">
        <div class="stat-label">最大回撤</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-loss);">${maxDrawdown.toFixed(2)}%</div>
      </div>
      <div class="cq-card stat-card" title="盈利交易笔数 / 总交易笔数。注意：高胜率不代表正收益（小赢大亏会让总收益为负）">
        <div class="stat-label">胜率</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-profit);">${winRate.toFixed(1)}%</div>
      </div>
      <div class="cq-card stat-card" title="所有盈利交易总和 / 所有亏损交易总和。>1 说明赚的比亏的多；∞ 表示无亏损">
        <div class="stat-label">盈亏比</div>
        <div class="stat-value cq-num"${winRate === 100 && totalTrades > 0 ? ' style="color:var(--cq-color-profit);"' : ''}>${
          winRate === 100 && totalTrades > 0
            ? '∞'
            : profitFactor.toFixed(2)
        }</div>
      </div>
      <div class="cq-card stat-card" title="完整开仓 → 平仓的次数（不含加仓动作）。DCA/Martingale/Grid 因为持续加仓，单次开平可能含多次 adds">
        <div class="stat-label">总交易次数</div>
        <div class="stat-value cq-num">${totalTrades} 笔${(() => {
          const totalAdds = (trades || []).reduce((s, t) => s + (t.adds || 0), 0);
          return totalAdds > 0
            ? `<span style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);margin-left:6px;font-weight:400;">含 ${totalAdds} 次加仓</span>`
            : '';
        })()}</div>
      </div>
    </div>

    <!-- 扩展指标：2列布局，紧凑风格 -->
    <div class="cq-card cq-metrics-detail" style="margin-bottom:var(--cq-space-4);">
      <div class="cq-metrics-detail__header" onclick="this.parentElement.classList.toggle('is-collapsed')">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
          <span style="font-size:var(--cq-text-md);font-weight:600;">详细指标</span>
        </div>
        <svg class="cq-metrics-detail__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
      </div>
      <div class="cq-metrics-detail__body">
        <div class="cq-metrics-detail__grid">
          <div class="cq-metrics-detail__item" title="(1 + 总收益率)^(365/天数) - 1。把回测窗口的实际收益换算成「一年下来等价的」复利收益率"><span class="cq-metrics-detail__label">年化收益率</span><span class="cq-metrics-detail__value cq-num" style="color:${annualReturn >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${annualReturn >= 0 ? '+' : ''}${annualReturn.toFixed(2)}%</span></div>
          <div class="cq-metrics-detail__item" title="年化收益率 / 最大回撤。比夏普更关注「亏损深度」，>1 优秀，>3 卓越"><span class="cq-metrics-detail__label">卡玛比率</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-primary);">${calmarRatio.toFixed(2)}</span></div>
          <div class="cq-metrics-detail__item" title="盈利交易笔数 / 亏损交易笔数"><span class="cq-metrics-detail__label">盈利 / 亏损次数</span><span class="cq-metrics-detail__value cq-num"><span style="color:var(--cq-color-profit);">${profitTrades}</span> / <span style="color:var(--cq-color-loss);">${lossTrades}</span></span></div>
          <div class="cq-metrics-detail__item" title="所有盈利交易 pnl 均值（已扣手续费）"><span class="cq-metrics-detail__label">平均盈利</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-profit);">${profitTrades > 0 ? '+' + fmtAmount(avgProfit) : '—'}</span></div>
          <div class="cq-metrics-detail__item" title="所有亏损交易 pnl 绝对值均值（已扣手续费）"><span class="cq-metrics-detail__label">平均亏损</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-loss);">${lossTrades > 0 ? fmtAmount(avgLoss) : '—'}</span></div>
          <div class="cq-metrics-detail__item" title="连续盈利 / 连续亏损的最长记录条数。从 trades 顺序推导"><span class="cq-metrics-detail__label">最大连胜 / 连亏</span><span class="cq-metrics-detail__value cq-num"><span style="color:var(--cq-color-profit);">${maxConWins}</span> / <span style="color:var(--cq-color-loss);">${maxConLosses}</span></span></div>
          <div class="cq-metrics-detail__item" title="回测窗口跨度（端到端天数，非有持仓的实际交易天数）"><span class="cq-metrics-detail__label">交易天数</span><span class="cq-metrics-detail__value cq-num">${duration} 天</span></div>
          <div class="cq-metrics-detail__item" title="从权益曲线峰值跌下来 → 再创新高之间的最长时间间隔。越短说明策略恢复能力越强；0 表示从未跌破峰值"><span class="cq-metrics-detail__label">最长回撤时长</span>${(() => {
            const mddh = metrics.maxDrawdownDurationHours;
            if (mddh == null) return '<span class="cq-metrics-detail__value cq-num">--</span>';
            if (mddh === 0) return '<span class="cq-metrics-detail__value cq-num" style="color:var(--cq-text-tertiary);">—</span>';
            const display = mddh >= 24 ? `${(mddh / 24).toFixed(1)} 天` : `${mddh.toFixed(1)} 小时`;
            return `<span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-loss);">${display}</span>`;
          })()}</div>
          ${(() => {
            const iv = result.interval || metrics.interval;
            const kc = result.klineCount ?? metrics.klineCount;
            if (!iv && kc == null) return '';
            const text = [iv, kc != null ? `${kc} 根` : null].filter(Boolean).join(' · ');
            return `<div class="cq-metrics-detail__item" title="拉取的总 K 线周期与数量。窗口/周期决定策略每次分析的数据规模"><span class="cq-metrics-detail__label">K 线周期</span><span class="cq-metrics-detail__value">${escapeHtml(text)}</span></div>`;
          })()}
          <div class="cq-metrics-detail__item" title="每根 bar 传给策略 analyze() 的 K 线长度。「全量前缀」= 从第 1 根到当前 bar 都传入；「最近 N 根」= 只传最近 N 根省内存"><span class="cq-metrics-detail__label">策略K线窗口</span><span class="cq-metrics-detail__value">${escapeHtml(analysisWindowLabel)}</span></div>
          <div class="cq-metrics-detail__item" title="回测起点资金 → 终点资金（含手续费、资金费等所有成本）"><span class="cq-metrics-detail__label">初始 / 最终权益</span><span class="cq-metrics-detail__value cq-num">${initialCapital.toFixed(2)} → <span style="color:${finalCapital >= initialCapital ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${finalCapital.toFixed(2)}</span></span></div>
          ${(() => {
            if (result.market !== 'perp') return '';
            const lev = result.leverage ?? metrics.leverage;
            if (lev == null) return '';
            return `<div class="cq-metrics-detail__item" title="永续合约杠杆倍数。仅决定保证金占用 (1/杠杆)，不放大持仓 — 名义本金始终 = 单笔最大资金比例 × 余额"><span class="cq-metrics-detail__label">杠杆</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-primary);">${Number(lev).toFixed(0)}×</span></div>`;
          })()}
          ${(() => {
            const fft = result.fundingFeeTotal ?? metrics.fundingFeeTotal;
            if (result.market !== 'perp' || fft == null) return '';
            // 0 是中性（无 funding 影响），非 0 才上色
            const cell = fft === 0
              ? `<span class="cq-metrics-detail__value cq-num" style="color:var(--cq-text-tertiary);">—</span>`
              : `<span class="cq-metrics-detail__value cq-num" style="color:${fft > 0 ? 'var(--cq-color-loss)' : 'var(--cq-color-profit)'};">${fft > 0 ? '-' : '+'}${Math.abs(fft).toFixed(2)}</span>`;
            return `<div class="cq-metrics-detail__item" title="累计资金费用（仅永续）。正值 = 账户净支付（红），负值 = 账户净收（绿），0 表示该回测窗口无 funding 结算"><span class="cq-metrics-detail__label">资金费用累计</span>${cell}</div>`;
          })()}
          <div class="cq-metrics-detail__item" title="K 线数据来源。binance-spot / binance-perp = 真实历史"><span class="cq-metrics-detail__label">数据源</span><span class="cq-metrics-detail__value" style="color:var(--cq-color-primary);">${escapeHtml(metrics.dataSource || result.dataSource || '--')}</span></div>
        </div>
      </div>
    </div>

    <div class="cq-card" style="margin-bottom:var(--cq-space-4);">
      <div class="cq-section-title" style="margin-bottom:var(--cq-space-3);">
        <h3>收益曲线</h3>
      </div>
      <div id="backtestResultChart" style="position:relative;height:280px;width:100%;"></div>
    </div>

    <!-- 交易明细表 -->
    ${trades.length > 0 ? `
    <div class="cq-card cq-trades-detail">
      <div class="cq-metrics-detail__header" onclick="this.parentElement.classList.toggle('is-collapsed')">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span style="font-size:var(--cq-text-md);font-weight:600;">交易明细</span>
          <span class="cq-tag cq-tag--neutral" style="margin-left:var(--cq-space-1);" title="${trades.length < totalTrades ? `仅展示最近 ${trades.length} 笔，总交易 ${totalTrades} 笔` : ''}">${trades.length < totalTrades ? `最近 ${trades.length} / ${totalTrades}` : `${trades.length}`} 笔</span>
        </div>
        <svg class="cq-metrics-detail__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
      </div>
      <div class="cq-metrics-detail__body">
        <div class="cq-table-wrap">
        <table class="cq-table cq-trades-table">
          <thead>
            <tr>
              <th>#</th>
              <th>方向</th>
              <th style="text-align:right;">开仓价</th>
              <th style="text-align:right;">平仓价</th>
              <th style="text-align:right;">数量</th>
              <th style="text-align:right;">盈亏</th>
              <th title="UTC 时间（北京时间 = UTC + 8h）">开仓时间 (UTC)</th>
              <th title="UTC 时间（北京时间 = UTC + 8h）">平仓时间 (UTC)</th>
            </tr>
          </thead>
          <tbody>
            ${trades.map((t, i) => {
              const pnl = t.pnl ?? 0;
              const sideLabel = t.side === 'long' ? '多' : '空';
              const sideClass = t.side === 'long' ? 'cq-tag--profit' : 'cq-tag--loss';
              const entryPrice = t.entryPrice ?? 0;
              const exitPrice = t.exitPrice ?? 0;
              const qty = t.quantity ?? 0;
              const entryTime = t.entryTime ? t.entryTime.substring(0, 16).replace('T', ' ') : '--';
              const exitTime = t.exitTime ? t.exitTime.substring(0, 16).replace('T', ' ') : '--';
              // 智能价格精度：BTC 2 位足够，PEPE 0.00000427 这种 toFixed(2) 会归零
              const fmtPrice = (p) => {
                if (p === 0) return '0';
                const abs = Math.abs(p);
                if (abs >= 100) return p.toFixed(2);
                if (abs >= 1) return p.toFixed(4);
                if (abs >= 0.01) return p.toFixed(6);
                return p.toPrecision(4);
              };
              return `
              <tr>
                <td style="color:var(--cq-text-tertiary);">${i + 1}</td>
                <td>
                  <span class="cq-tag ${sideClass}">${sideLabel}</span>${
                    t.adds && t.adds > 0
                      ? ` <span class="cq-tag cq-tag--neutral" style="margin-left:4px;" title="此 trade 包含 ${t.adds} 次加仓 (DCA/Grid/Martingale)">+${t.adds}</span>`
                      : ''
                  }
                </td>
                <td class="cq-num" style="text-align:right;">${fmtPrice(entryPrice)}</td>
                <td class="cq-num" style="text-align:right;">${fmtPrice(exitPrice)}</td>
                <td class="cq-num" style="text-align:right;">${qty < 1 ? qty.toPrecision(4) : qty.toFixed(4)}</td>
                <td class="cq-num" style="text-align:right;color:${pnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};font-weight:500;">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</td>
                <td style="color:var(--cq-text-secondary);font-size:var(--cq-text-sm);">${entryTime}</td>
                <td style="color:var(--cq-text-secondary);font-size:var(--cq-text-sm);">${exitTime}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
        </div>
      </div>
    </div>` : ''}`;

  const points = result.equityCurve || result.points || [];
  if (points.length > 0) {
    renderBacktestEquityChart(points);
  }
}

function _backtestParseTime(raw) {
  if (raw == null) return null;
  if (typeof raw === 'number') return raw > 1e11 ? Math.floor(raw / 1000) : Math.floor(raw);
  const t = Date.parse(String(raw));
  return isNaN(t) ? null : Math.floor(t / 1000);
}

function _disposeBacktestChart() {
  if (App.state.backtestChart && typeof App.state.backtestChart.remove === 'function') {
    try { App.state.backtestChart.remove(); } catch {}
  }
  App.state.backtestChart = null;
  if (App.state.backtestResizeObserver) {
    try { App.state.backtestResizeObserver.disconnect(); } catch {}
    App.state.backtestResizeObserver = null;
  }
}

function renderBacktestEquityChart(points) {
  const container = document.getElementById('backtestResultChart');
  if (!container) return;
  if (typeof LightweightCharts === 'undefined') return;

  const data = [];
  for (const p of points) {
    const t = _backtestParseTime(p.date);
    if (t == null) continue;
    data.push({ time: t, value: Number(p.equity) });
  }
  data.sort((a, b) => a.time - b.time);
  const dedup = [];
  for (const p of data) {
    if (dedup.length === 0 || dedup[dedup.length - 1].time !== p.time) dedup.push(p);
  }
  if (dedup.length === 0) return;

  _disposeBacktestChart();
  container.innerHTML = '';

  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1';

  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { type: 'solid', color: 'transparent' },
      textColor: isDark ? '#8B949E' : '#475569',
      fontFamily: "'Geist', 'JetBrains Mono', sans-serif",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: isDark ? 'rgba(139,148,158,0.10)' : 'rgba(15,23,42,0.05)' },
      horzLines: { color: isDark ? 'rgba(139,148,158,0.10)' : 'rgba(15,23,42,0.05)' },
    },
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: isDark ? 'rgba(139,148,158,0.4)' : 'rgba(15,23,42,0.3)', labelBackgroundColor: primary },
      horzLine: { color: isDark ? 'rgba(139,148,158,0.4)' : 'rgba(15,23,42,0.3)', labelBackgroundColor: primary },
    },
    rightPriceScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      scaleMargins: { top: 0.10, bottom: 0.06 },
    },
    timeScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      timeVisible: false,
      secondsVisible: false,
    },
    handleScroll: false,
    handleScale: false,
  });

  const series = chart.addAreaSeries({
    lineColor: primary,
    lineWidth: 2,
    topColor: isDark ? 'rgba(99,102,241,0.25)' : 'rgba(79,70,229,0.18)',
    bottomColor: 'rgba(99,102,241,0)',
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  });
  series.setData(dedup);
  chart.timeScale().fitContent();

  const ro = new ResizeObserver(entries => {
    for (const e of entries) {
      const { width, height } = e.contentRect;
      chart.applyOptions({ width: Math.floor(width), height: Math.floor(height) });
    }
  });
  ro.observe(container);

  App.state.backtestChart = chart;
  App.state.backtestEquityData = dedup;
  App.state.backtestResizeObserver = ro;
}

window.addEventListener('cq:theme-change', () => {
  const data = App.state.backtestEquityData;
  if (data && document.getElementById('backtestResultChart')) {
    renderBacktestEquityChart(data.map(p => ({ date: p.time * 1000, equity: p.value })));
  }
});

// 监听模板/实例选择变化，渲染参数（选实例时还自动填入实例的 params + symbol）
document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('backtest-template-select');
  if (sel) {
    sel.addEventListener('change', async () => {
      const source = _getSelectedBacktestSource();
      if (!source) { document.getElementById('backtest-params').innerHTML = ''; return; }
      try {
        const templates = App.state.backtestTemplates || await api.getStrategyTemplates();
        App.state.backtestTemplates = templates;
        const tmpl = templates.find(t => t.id === source.templateId);
        if (tmpl && tmpl.strategyType === 'rule') {
          resetBacktestRuleState();
          renderBacktestRuleBuilder();
        } else if (tmpl && tmpl.params && tmpl.params.length > 0) {
          renderBacktestParamControls(tmpl.params);
          // 选了"我的策略"实例 → 把实例的参数和 symbol 自动带入
          if (source.kind === 'instance' && source.instance) {
            applyBacktestInstanceValues(tmpl.params, source.instance);
          }
        } else {
          document.getElementById('backtest-params').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
        }
      } catch {}
    });
  }
});

/** 选中策略实例后，把实例的 params 填入回测参数控件，symbol 同步到符号选择器。 */
function applyBacktestInstanceValues(paramDefs, instance) {
  const values = instance.params || {};
  for (const param of paramDefs || []) {
    if (param.type === 'rules') continue;
    const value = values[param.key];
    if (value === undefined || value === null) continue;

    if (param.type === 'json_table') {
      applyJsonTableValue(param.key, param.columns || [], value, 'bt-param');
      continue;
    }

    const input = document.getElementById(`bt-param-${param.key}`)
      || document.getElementById(`sl-bt-${param.key}`);
    if (!input) continue;

    if (param.type === 'bool') {
      input.checked = Boolean(value);
    } else if (param.type === 'array_int' || param.type === 'array_double') {
      input.value = Array.isArray(value) ? value.join(', ') : String(value);
    } else if (param.type === 'json') {
      input.value = typeof value === 'string' ? value : JSON.stringify(value);
    } else {
      input.value = value;
      const valueLabel = document.getElementById(`val-bt-${param.key}`);
      if (valueLabel) valueLabel.textContent = value;
    }
  }
  // 同步 symbol 到回测页符号选择器
  if (instance.symbol && App.state.backtestSymbolSel?.setValue) {
    try { App.state.backtestSymbolSel.setValue(instance.symbol); } catch {}
  }
}

/**
 * 渲染回测历史列表
 */
function renderBacktestHistory(history) {
  if (!history || history.length === 0) return;

  const resultsEl = document.getElementById('backtest-results');
  const parentEl = resultsEl.parentElement;

  let historyEl = document.getElementById('backtest-history');
  if (!historyEl) {
    historyEl = document.createElement('div');
    historyEl.id = 'backtest-history';
    historyEl.style.cssText = 'grid-column:1/-1;margin-top:var(--cq-space-4);';
    parentEl.appendChild(historyEl);
  }

  historyEl.innerHTML = `
    <div class="cq-card">
      <div style="font-size:var(--cq-text-md);font-weight:600;margin-bottom:var(--cq-space-2);display:flex;align-items:center;justify-content:space-between;gap:var(--cq-space-2);">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          最近回测记录
        </div>
        <button class="cq-btn cq-btn--ghost cq-btn--sm" onclick="clearAllBacktestHistory()" style="font-size:var(--cq-text-xs);color:var(--cq-color-loss);">
          清空全部
        </button>
      </div>
      <div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);margin-bottom:var(--cq-space-3);">点击一行加载完整图表与交易明细${history.length >= 20 ? ` · 显示最近 ${history.length} 条` : ''}</div>
      <div class="cq-table-wrap" style="max-height:480px;overflow-y:auto;">
      <table class="cq-table">
        <thead>
          <tr>
            <th>策略</th>
            <th>交易对</th>
            <th style="text-align:right;" title="(最终权益 - 初始资金) / 初始资金 × 100%">收益率</th>
            <th style="text-align:right;" title="年化收益率 / 年化波动率，越高越好（cap ±10）">夏普</th>
            <th style="text-align:right;" title="权益曲线从历史峰值最大跌幅%，越小越稳">回撤</th>
            <th style="text-align:right;" title="盈利交易 / 总交易">胜率</th>
            <th style="text-align:right;" title="完整开仓→平仓次数（不含加仓动作）">交易数</th>
            <th style="text-align:right;">时间</th>
            <th style="text-align:right;width:42px;"></th>
          </tr>
        </thead>
        <tbody>
          ${history.map(h => {
            const ret = h.totalReturnPercent ?? 0;
            const sharpe = h.sharpeRatio ?? 0;
            const dd = h.maxDrawdown ?? 0;
            const wr = h.winRate ?? 0;
            const trades = h.totalTrades ?? 0;
            return `
            <tr style="cursor:pointer;" onclick="viewBacktestDetail(${h.id})">
              <td style="color:var(--cq-text-primary);font-weight:500;">${escapeHtml(h.templateName || h.templateId)}</td>
              <td style="color:var(--cq-text-secondary);">
                ${escapeHtml(h.symbol)}
                ${h.market === 'perp'
                  ? '<span class="cq-tag cq-tag--loss" style="margin-left:6px;font-size:var(--cq-text-xs);padding:1px 6px;">永续</span>'
                  : h.market === 'spot'
                  ? '<span class="cq-tag cq-tag--neutral" style="margin-left:6px;font-size:var(--cq-text-xs);padding:1px 6px;">现货</span>'
                  : ''}
              </td>
              <td class="cq-num" style="text-align:right;color:${ret >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-primary);">${sharpe.toFixed(2)}</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-loss);">${dd.toFixed(2)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-profit);">${wr.toFixed(1)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-text-secondary);">${trades}</td>
              <td style="text-align:right;color:var(--cq-text-tertiary);">${h.createdAt ? h.createdAt.substring(0, 10) : ''}</td>
              <td style="text-align:right;" onclick="event.stopPropagation();">
                <button class="cq-icon-btn" title="删除该回测记录" aria-label="删除" onclick="deleteBacktestRow(${h.id}, event)" style="padding:4px;color:var(--cq-text-tertiary);">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 0 1-2 2H9a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
                </button>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>
    </div>`;
}

async function viewBacktestDetail(id) {
  const resultsEl = document.getElementById('backtest-results');
  if (!resultsEl) return;
  _disposeBacktestChart();
  // 记录正在展示的历史 ID，用于删除时判断是否清空详情
  App.state.backtestDisplayedDetailId = id;
  resultsEl.innerHTML =
    '<div class="cq-card cq-empty-state" style="padding:var(--cq-space-6);text-align:center;color:var(--cq-text-secondary);">正在加载回测详情…</div>';
  try {
    const result = await api.getBacktestResults(id);
    renderBacktestResults(result);
    resultsEl.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    showToast('加载回测详情失败: ' + (err.message || String(err)), 'error');
    resultsEl.innerHTML =
      '<div class="cq-card cq-empty-state"><p style="color:var(--cq-text-secondary);">无法加载该条记录，请稍后重试。</p></div>';
  }
}

window.viewBacktestDetail = viewBacktestDetail;

function _resetBacktestResultsArea() {
  _disposeBacktestChart();
  const resultsEl = document.getElementById('backtest-results');
  if (resultsEl) {
    resultsEl.innerHTML = `<div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);text-align:center;color:var(--cq-text-secondary);">
      <h3 style="margin:0 0 var(--cq-space-2) 0;font-size:var(--cq-text-md);">选择策略模板并运行回测</h3>
      <p style="margin:0;font-size:var(--cq-text-sm);">回测结果将在此处展示</p>
    </div>`;
  }
  App.state.backtestDisplayedDetailId = null;
}

async function deleteBacktestRow(id, ev) {
  if (ev) { ev.stopPropagation(); ev.preventDefault(); }
  if (!confirm(`确定删除回测记录 #${id}? 不可恢复`)) return;
  try {
    await api.deleteBacktestResult(id);
    showToast('已删除', 'success');
    // 删除的是正在展示的那条 → 清空详情区，避免显示已删除数据
    if (App.state.backtestDisplayedDetailId === id) {
      _resetBacktestResultsArea();
    }
    // 重新拉历史刷新列表
    const history = await api.getBacktestHistory(50).catch(() => []);
    renderBacktestHistory(history);
  } catch (err) {
    showToast('删除失败: ' + (err.message || String(err)), 'error');
  }
}
window.deleteBacktestRow = deleteBacktestRow;

async function clearAllBacktestHistory() {
  if (!confirm('确定清空全部回测历史? 不可恢复')) return;
  try {
    const r = await api.deleteAllBacktestHistory();
    showToast(`已清空 ${r.deleted ?? 0} 条历史`, 'success');
    // 清空详情区（如果当前在展示历史详情，里面的数据都被删了）
    if (App.state.backtestDisplayedDetailId != null) {
      _resetBacktestResultsArea();
    }
    const history = await api.getBacktestHistory(50).catch(() => []);
    renderBacktestHistory(history);
  } catch (err) {
    showToast('清空失败: ' + (err.message || String(err)), 'error');
  }
}
window.clearAllBacktestHistory = clearAllBacktestHistory;

/**
 * 渲染回测参数控件,与 strategy.js 的 renderParamSliders 同套类型支持。
 * type: int/double  → range slider
 *       bool        → checkbox
 *       array_int / array_double → 逗号分隔文本
 *       json        → textarea
 *       rules / 其他 → 跳过(rules 由 renderBacktestRuleBuilder 处理)
 */
// perp 专属参数：spot 模式下回测引擎根本不读，UI 显示会误导用户
const PERP_ONLY_PARAM_KEYS = new Set(['leverage', 'initial_margin_rate', 'funding_rate_8h']);

function renderBacktestParamControls(params) {
  const root = document.getElementById('backtest-params');
  // 记录当前 params 给 symbol 切换时复用
  App.state.backtestCurrentParams = params;
  // 取当前 market：spot 时过滤掉 perp-only 参数
  let currentMarket = 'spot';
  try {
    const v = App.state.backtestSymbolSel?.getValue?.() || 'BTCUSDT';
    currentMarket = (typeof splitMarket === 'function' ? splitMarket(v).market : 'spot') || 'spot';
  } catch { /* fallback spot */ }

  root.innerHTML = params.map(p => {
    const t = p.type || 'double';
    const desc = p.description
      ? `<div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);margin-top:4px;">${p.description}</div>`
      : '';

    if (t === 'rules') return '';  // rule_custom 不会走到这里(已被 strategyType==='rule' 拦截)
    // auto_trade 是实盘 runner 开关,回测路径根本不读这字段,UI 显示反而误导(文案说"真实下单")
    if (p.key === 'auto_trade') return '';
    // spot 模式下隐藏 perp-only 参数（杠杆/初始保证金率/资金费率）
    if (currentMarket === 'spot' && PERP_ONLY_PARAM_KEYS.has(p.key)) return '';

    if (t === 'bool') {
      const checked = p.default ? 'checked' : '';
      return `
        <div style="margin-bottom:var(--cq-space-3);">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" id="bt-param-${p.key}" data-key="${p.key}" data-type="bool" ${checked}>
            <span class="cq-label" style="margin-bottom:0;">${p.name}</span>
          </label>
          ${desc}
        </div>`;
    }

    if (t === 'array_int' || t === 'array_double') {
      const val = Array.isArray(p.default) ? p.default.join(', ') : (p.default ?? '');
      return `
        <div style="margin-bottom:var(--cq-space-3);">
          <label class="cq-label" for="bt-param-${p.key}">${p.name}</label>
          <input type="text" id="bt-param-${p.key}" data-key="${p.key}" data-type="${t}"
            value="${val}" placeholder="逗号分隔,如: 30, 25, 20"
            style="width:100%;padding:6px 10px;border:1px solid var(--cq-border);border-radius:4px;background:transparent;color:var(--cq-text-primary);">
          ${desc}
        </div>`;
    }

    if (t === 'json') {
      const val = typeof p.default === 'string' ? p.default : JSON.stringify(p.default);
      return `
        <div style="margin-bottom:var(--cq-space-3);">
          <label class="cq-label" for="bt-param-${p.key}">${p.name}</label>
          <textarea id="bt-param-${p.key}" data-key="${p.key}" data-type="json"
            rows="3" style="width:100%;padding:6px 10px;border:1px solid var(--cq-border);border-radius:4px;font-family:monospace;font-size:var(--cq-text-sm);background:transparent;color:var(--cq-text-primary);">${val}</textarea>
          ${desc}
        </div>`;
    }

    if (t === 'json_table') {
      const cols = Array.isArray(p.columns) ? p.columns : [];
      const rows = Array.isArray(p.default) ? p.default : [];
      // json_table 是多 input 组,无单一 target 可指向,改用 aria-labelledby 让 SR
      // 把标题播报给整张表
      const labelId = `bt-tbl-label-${p.key}`;
      return `
        <div style="margin-bottom:var(--cq-space-3);">
          <div class="cq-label" id="${labelId}">${p.name}</div>
          <div role="group" aria-labelledby="${labelId}">
            ${renderJsonTable(p.key, cols, rows, 'bt-param')}
          </div>
          ${desc}
        </div>`;
    }

    if (t === 'select') {
      const options = Array.isArray(p.options) ? p.options : [];
      const optsHtml = options.map(opt => {
        const v = (opt && typeof opt === 'object') ? opt.value : opt;
        const lbl = (opt && typeof opt === 'object') ? (opt.label ?? opt.value) : opt;
        const sel = String(v) === String(p.default) ? ' selected' : '';
        return `<option value="${v}"${sel}>${lbl}</option>`;
      }).join('');
      return `
        <div style="margin-bottom:var(--cq-space-3);">
          <label class="cq-label" for="bt-param-${p.key}">${p.name}</label>
          <select class="cq-input" id="bt-param-${p.key}" data-key="${p.key}" data-type="select">
            ${optsHtml}
          </select>
          ${desc}
        </div>`;
    }

    // int / double — slider
    return `
      <div style="margin-bottom:var(--cq-space-3);">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--cq-space-2);">
          <label class="cq-label" for="sl-bt-${p.key}" style="margin-bottom:0;">${p.name}</label>
          <span class="cq-num" style="font-size:var(--cq-text-sm);font-weight:600;color:var(--cq-color-primary);" id="val-bt-${p.key}">${p.default}</span>
        </div>
        <input type="range" class="cq-slider" id="sl-bt-${p.key}" data-key="${p.key}" data-type="${t}"
          min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
          oninput="document.getElementById('val-bt-${p.key}').textContent=this.value">
        ${desc}
      </div>`;
  }).join('');
}

/**
 * 收集回测参数,按类型解析。json 解析失败抛错由调用方 toast。
 */
function collectBacktestParams() {
  const out = {};
  const root = document.getElementById('backtest-params');

  root.querySelectorAll('input[type="checkbox"][data-key]').forEach(el => {
    out[el.dataset.key] = el.checked;
  });
  root.querySelectorAll('input[type="text"][data-key]').forEach(el => {
    const t = el.dataset.type;
    const parts = el.value.split(',').map(s => s.trim()).filter(s => s !== '');
    out[el.dataset.key] = parts.map(s => t === 'array_int' ? parseInt(s, 10) : parseFloat(s));
  });
  root.querySelectorAll('textarea[data-key]').forEach(el => {
    const txt = el.value.trim();
    if (txt === '') { out[el.dataset.key] = null; return; }
    try {
      out[el.dataset.key] = JSON.parse(txt);
    } catch (e) {
      throw new Error(`参数 "${el.dataset.key}" JSON 格式错误: ${e.message}`);
    }
  });
  root.querySelectorAll('.cq-json-table[data-key]').forEach(table => {
    out[table.dataset.key] = readJsonTable(table);
  });
  root.querySelectorAll('input[type="range"][data-key]').forEach(el => {
    const t = el.dataset.type;
    out[el.dataset.key] = t === 'int' ? parseInt(el.value, 10) : parseFloat(el.value);
  });
  root.querySelectorAll('select[data-key]').forEach(el => {
    out[el.dataset.key] = el.value;
  });

  return out;
}
