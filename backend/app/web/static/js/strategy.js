/**
 * 策略中心页面逻辑 v3 — 药丸选择器 + 内联表单
 */
let selectedTemplateId = null;

/* ── 策略图标映射 ── */
const STRATEGY_ICONS = {
  ma:    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  rsi:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-8"/></svg>',
  boll:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12C2 6.5 6.5 2 12 2s10 4.5 10 10-4.5 10-10 10S2 17.5 2 12z"/><path d="M6 12C6 8.7 8.7 6 12 6s6 2.7 6 6-2.7 6-6 6-6-2.7-6-6z"/></svg>',
  grid:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
  mart:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
  default: '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93"/><path d="M8.5 8.5L5 12l3.5 3.5"/><path d="M15.5 8.5L19 12l-3.5 3.5"/><circle cx="12" cy="18" r="3"/></svg>',
};

function getStrategyIcon(templateId) {
  const key = (templateId || '').toLowerCase();
  for (const [k, v] of Object.entries(STRATEGY_ICONS)) {
    if (key.includes(k)) return v;
  }
  return STRATEGY_ICONS.default;
}

/** 根据当前选中的交易所过滤账户下拉 */
function filterAccountsByExchange() {
  const exSelect = document.getElementById('new-strategy-exchange');
  const accountSelect = document.getElementById('new-strategy-account');
  if (!exSelect || !accountSelect) return;

  const selectedExchange = exSelect.value;
  const accounts = window._connectedAccounts || [];

  const filtered = accounts.filter(a => a.exchange === selectedExchange);

  accountSelect.innerHTML = '<option value="">模拟模式（不下单）</option>' +
    filtered.map(a => `<option value="${a.id}">${a.account_name || a.exchange} (${a.exchange})</option>`).join('');

  if (filtered.length === 0) {
    const opt = document.createElement('option');
    opt.disabled = true;
    opt.textContent = '— 该交易所暂无已连接账户 —';
    accountSelect.appendChild(opt);
  }
}

async function loadStrategyPage() {
  const container = document.getElementById('instance-list');
  container.innerHTML = '<div class="cq-skeleton" style="height:80px;margin-bottom:var(--cq-space-3);"></div><div class="cq-skeleton" style="height:60px;"></div>';

  // 预加载账户数据
  try {
    window._connectedAccounts = await api.getExchangeAccounts();
  } catch (e) { console.warn('预加载交易所账户失败:', e); }

  try {
    const [templates, instances] = await Promise.all([
      api.getStrategyTemplates().catch(() => []),
      api.getStrategyInstances().catch(() => []),
    ]);

    renderTemplatePills(templates);
    renderInstanceList(instances);
    window._strategyInstances = instances;
    window._cachedTemplates = templates;
  } catch (err) {
    container.innerHTML = `
      <div class="cq-card cq-empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        <h3>${escapeHtml(err.message)}</h3>
      </div>`;
  }
}

/* ── 渲染药丸选择器 ── */
function renderTemplatePills(templates) {
  const el = document.getElementById('template-list');
  if (!templates || templates.length === 0) {
    el.innerHTML = '<div style="color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">暂无策略模板</div>';
    return;
  }

  el.innerHTML = templates.map(t => `
    <button class="cq-pill${selectedTemplateId === t.id ? ' is-selected' : ''}" id="pill-${t.id}" onclick="selectTemplate('${t.id}')" title="${t.description || t.name}">
      <div class="cq-pill__icon">${getStrategyIcon(t.id)}</div>
      <span class="cq-pill__name">${t.name}</span>
      <div class="cq-pill__check">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      </div>
    </button>
  `).join('');
}

/* ── 渲染实例列表 ── */
function renderInstanceList(instances) {
  const el = document.getElementById('instance-list');
  if (!instances || instances.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93"/><path d="M8.5 8.5L5 12l3.5 3.5"/><path d="M15.5 8.5L19 12l-3.5 3.5"/><circle cx="12" cy="18" r="3"/></svg>
        <h3>暂无运行中的策略实例</h3>
        <p>选择上方模板创建你的第一个策略</p>
      </div>`;
    return;
  }

  el.innerHTML = instances.map(inst => {
    const statusTag = inst.status === 'running'
      ? '<span class="cq-tag cq-tag--profit"><span class="cq-pulse-dot" style="width:6px;height:6px;margin-right:4px;"></span>运行中</span>'
      : inst.status === 'paused'
      ? '<span class="cq-tag cq-tag--warn">已暂停</span>'
      : '<span class="cq-tag cq-tag--neutral">已停止</span>';

    const isLive = inst.isLive || inst.accountId;
    const modeTag = isLive
      ? '<span class="cq-tag cq-tag--profit" style="font-size:10px;padding:1px 6px;">实盘</span>'
      : '<span class="cq-tag cq-tag--neutral" style="font-size:10px;padding:1px 6px;">模拟</span>';

    const exchangeLabel = { binance: 'Binance', okx: 'OKX', htx: 'HTX' }[inst.exchange] || inst.exchange;
    const pnl = inst.totalPnl ?? 0;
    const winRate = inst.winRate ?? 0;
    const totalTrades = inst.totalTrades ?? 0;

    return `
    <div class="cq-card cq-instance-card">
      <div class="cq-instance-card__header">
        <div class="cq-instance-card__info">
          <div class="cq-instance-card__name-row">
            <span class="cq-instance-card__name">${escapeHtml(inst.name)}</span>
            ${statusTag}
            ${modeTag}
          </div>
          <div class="cq-instance-card__meta">
            <span>${escapeHtml(inst.templateName)}</span>
            <span class="sep">·</span>
            <span>${exchangeLabel}</span>
            <span class="sep">·</span>
            <span style="font-family:var(--cq-font-mono);">${inst.symbol || '—'}</span>
            <span class="sep">·</span>
            <span>${totalTrades} 笔交易</span>
          </div>
        </div>
        <div class="cq-instance-card__pnl">
          <div class="cq-instance-card__pnl-value" style="color:${pnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}</div>
          <div class="cq-instance-card__pnl-rate">${winRate.toFixed(1)}% 胜率</div>
        </div>
      </div>
      <div class="cq-instance-card__actions">
        ${inst.status !== 'running'
          ? `<button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="toggleStrategy('${inst.id}', 'start')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
              启动
            </button>`
          : `<button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="toggleStrategy('${inst.id}', 'stop')">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
              停止
            </button>`
        }
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="showStrategyPerformance('${inst.id}')" title="绩效报告">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
          绩效
        </button>
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="showStrategyEdit('${inst.id}')" title="编辑策略">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"/></svg>
        </button>
        <button class="cq-btn cq-btn--danger cq-btn--sm" onclick="deleteStrategyInst('${inst.id}')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          删除
        </button>
      </div>
    </div>`;
  }).join('');
}

/* ── 选择模板 ── */
async function selectTemplate(id) {
  // 如果再次点击已选中的药丸，则取消选择
  if (selectedTemplateId === id) {
    deselectTemplate();
    return;
  }

  selectedTemplateId = id;

  // 更新药丸选中态
  document.querySelectorAll('.cq-pill').forEach(p => p.classList.remove('is-selected'));
  const pill = document.getElementById('pill-' + id);
  if (pill) pill.classList.add('is-selected');

  // 展开创建表单
  await showCreateForm(id);
}

/* ── 取消选择 ── */
function deselectTemplate() {
  selectedTemplateId = null;
  document.querySelectorAll('.cq-pill').forEach(p => p.classList.remove('is-selected'));

  const wrap = document.getElementById('create-form-wrap');
  if (wrap) {
    wrap.style.display = 'none';
  }
}

/* ── 展开创建表单 ── */
async function showCreateForm(templateId) {
  const wrap = document.getElementById('create-form-wrap');

  // 更新标题
  const templates = window._cachedTemplates || [];
  const tmpl = templates.find(t => t.id === templateId);
  const titleEl = document.getElementById('create-form-title');
  if (titleEl && tmpl) {
    titleEl.textContent = `创建 ${tmpl.name} 实例`;
  }

  // 显示表单容器
  wrap.style.display = 'block';

  // 初始化交易对选择器（只创建一次）
  if (!window._strategySymbolSel) {
    const selEl = document.getElementById('strategy-symbol-selector');
    if (selEl) {
      window._strategySymbolSel = new SymbolSelector({
        containerId: 'strategy-symbol-selector',
        value: 'BTCUSDT',
        exchangeFilter: 'new-strategy-exchange',
      });
    }
  }

  // 初始化交易所账户联动
  try {
    const accounts = window._connectedAccounts || await api.getExchangeAccounts();
    window._connectedAccounts = accounts;
    const exSelect = document.getElementById('new-strategy-exchange');
    if (exSelect && !exSelect.dataset.initialized) {
      const connectedExchanges = [...new Set(accounts.map(a => a.exchange).filter(Boolean))];
      const allExchanges = [
        { value: 'binance', label: 'Binance' },
        { value: 'okx', label: 'OKX' },
        { value: 'htx', label: 'HTX' },
      ];
      exSelect.innerHTML = allExchanges.map(ex => {
        const connected = connectedExchanges.includes(ex.value);
        return `<option value="${ex.value}">${ex.label}${connected ? ' ✓' : '（未连接）'}</option>`;
      }).join('');
      exSelect.addEventListener('change', () => filterAccountsByExchange());
      exSelect.dataset.initialized = '1';
    }
    filterAccountsByExchange();
  } catch (e) { console.warn('加载交易所账户失败:', e); }

  // 加载参数滑块
  try {
    if (!tmpl) {
      const allTemplates = await api.getStrategyTemplates();
      window._cachedTemplates = allTemplates;
      const found = allTemplates.find(t => t.id === templateId);
      if (found && found.params) renderParamSliders(found.params);
      else document.getElementById('param-sliders').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
    } else {
      if (tmpl.params) renderParamSliders(tmpl.params);
      else document.getElementById('param-sliders').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
    }
  } catch {}

  // 滚动到表单位置
  wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── 渲染参数滑块 ── */
function renderParamSliders(params) {
  const el = document.getElementById('param-sliders');
  if (!params || params.length === 0) {
    el.innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
    return;
  }

  el.innerHTML = params.map(p => `
    <div class="cq-param-group">
      <div class="cq-param-header">
        <span class="cq-param-label">${p.name}</span>
        <span class="cq-param-value" id="val-${p.key}">${p.default}</span>
      </div>
      <input type="range" class="cq-slider" id="sl-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
        oninput="document.getElementById('val-${p.key}').textContent=this.value">
    </div>
  `).join('');
}

/* ── 创建策略实例 ── */
async function createStrategyInstance() {
  if (!selectedTemplateId) { showToast('请先选择策略模板', 'warn'); return; }

  const name = document.getElementById('new-strategy-name').value.trim();
  if (!name) { showToast('请输入策略名称', 'warn'); return; }

  const exchange = document.getElementById('new-strategy-exchange').value;
  const symbol = window._strategySymbolSel ? window._strategySymbolSel.getValue() : 'BTCUSDT';
  const accountEl = document.getElementById('new-strategy-account');
  const accountId = accountEl ? (parseInt(accountEl.value) || undefined) : undefined;

  const params = {};
  document.querySelectorAll('#param-sliders input[type="range"]').forEach(sl => {
    const key = sl.id.replace('sl-', '');
    params[key] = parseFloat(sl.value);
  });

  try {
    await api.createStrategyInstance({
      name,
      templateId: selectedTemplateId,
      exchange,
      symbol,
      accountId,
      params,
    });
    showToast('策略创建成功！', 'success');
    deselectTemplate();
    loadStrategyPage();
  } catch (err) {
    showToast('创建失败: ' + err.message, 'error');
  }
}

/* ── 启停策略 ── */
async function toggleStrategy(instanceId, action) {
  try {
    if (action === 'start') await api.startStrategy(instanceId);
    else await api.stopStrategy(instanceId);
    showToast(`策略已${action === 'start' ? '启动' : '停止'}`, 'success');
    loadStrategyPage();
  } catch (err) {
    showToast('操作失败: ' + err.message, 'error');
  }
}

/* ── 删除策略 ── */
async function deleteStrategyInst(instanceId) {
  const inst = window._strategyInstances?.find(i => i.id === instanceId);
  const isRunning = inst && inst.status === 'running';

  const msg = isRunning
    ? '该策略正在运行，将先停止再删除。确认删除？'
    : '确认删除此策略？此操作不可撤销。';
  if (!confirm(msg)) return;

  try {
    if (isRunning) {
      await api.stopStrategy(instanceId);
    }
    await api.deleteStrategy(instanceId);
    showToast('策略已删除', 'success');
    loadStrategyPage();
  } catch (err) {
    showToast('删除失败: ' + err.message, 'error');
  }
}

/* ── 绩效报告弹窗 ── */
async function showStrategyPerformance(instanceId) {
  const modal = document.getElementById('strategy-perf-modal');
  const body = document.getElementById('strategy-perf-body');
  if (!modal || !body) return;

  body.innerHTML = '<div class="cq-skeleton" style="height:200px;"></div>';
  modal.classList.add('is-visible');

  try {
    const perf = await api.getStrategyPerformance(instanceId);
    renderStrategyPerformance(perf);
  } catch (err) {
    body.innerHTML = `<div class="cq-empty-state" style="padding:var(--cq-space-6);"><h3>${escapeHtml(err.message)}</h3><p>暂无绩效数据，策略需运行产生交易后才会有绩效</p></div>`;
  }
}

function renderStrategyPerformance(perf) {
  const body = document.getElementById('strategy-perf-body');
  if (!body) return;

  const totalReturn = perf.totalReturn ?? perf.total_return ?? 0;
  const sharpeRatio = perf.sharpeRatio ?? perf.sharpe_ratio ?? 0;
  const maxDrawdown = perf.maxDrawdown ?? perf.max_drawdown ?? 0;
  const winRate = perf.winRate ?? perf.win_rate ?? 0;
  const profitFactor = perf.profitFactor ?? perf.profit_factor ?? 0;
  const totalTrades = perf.totalTrades ?? perf.total_trades ?? 0;
  const annualReturn = perf.annualReturn ?? perf.annual_return ?? 0;
  const calmarRatio = perf.calmarRatio ?? perf.calmar_ratio ?? 0;
  const avgProfit = perf.avgProfit ?? perf.avg_profit ?? 0;
  const avgLoss = perf.avgLoss ?? perf.avg_loss ?? 0;

  body.innerHTML = `
    <div class="cq-grid-3" style="margin-bottom:var(--cq-space-4);">
      <div class="stat-card"><div class="stat-label">总收益率</div><div class="stat-value cq-num" style="color:${totalReturn >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%</div></div>
      <div class="stat-card"><div class="stat-label">夏普比率</div><div class="stat-value cq-num" style="color:var(--cq-color-primary-hover);">${sharpeRatio.toFixed(2)}</div></div>
      <div class="stat-card"><div class="stat-label">最大回撤</div><div class="stat-value cq-num" style="color:var(--cq-color-loss);">${maxDrawdown.toFixed(2)}%</div></div>
      <div class="stat-card"><div class="stat-label">胜率</div><div class="stat-value cq-num" style="color:var(--cq-color-profit);">${winRate.toFixed(1)}%</div></div>
      <div class="stat-card"><div class="stat-label">盈亏比</div><div class="stat-value cq-num">${profitFactor.toFixed(2)}</div></div>
      <div class="stat-card"><div class="stat-label">交易次数</div><div class="stat-value cq-num">${totalTrades} 笔</div></div>
    </div>
    <div class="cq-metrics-detail__grid" style="border-top:1px solid var(--cq-border-subtle);padding-top:var(--cq-space-3);">
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">年化收益</span><span class="cq-metrics-detail__value cq-num" style="color:${annualReturn >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${annualReturn >= 0 ? '+' : ''}${annualReturn.toFixed(2)}%</span></div>
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">卡玛比率</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-primary-hover);">${calmarRatio.toFixed(2)}</span></div>
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">平均盈利</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-profit);">+${avgProfit.toFixed(2)}</span></div>
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">平均亏损</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-loss);">${avgLoss.toFixed(2)}</span></div>
    </div>`;
}

function closeStrategyPerfModal() {
  const modal = document.getElementById('strategy-perf-modal');
  if (modal) modal.classList.remove('is-visible');
}

/* ── 编辑策略弹窗 ── */
async function showStrategyEdit(instanceId) {
  const modal = document.getElementById('strategy-edit-modal');
  const body = document.getElementById('strategy-edit-body');
  if (!modal || !body) return;

  body.innerHTML = '<div class="cq-skeleton" style="height:100px;"></div>';
  modal.classList.add('is-visible');

  try {
    const detail = await api.getStrategyDetail(instanceId);
    window._editingStrategyId = instanceId;
    window._editingStrategyDetail = detail;

    // 查找模板获取参数定义
    const templates = window._cachedTemplates || await api.getStrategyTemplates();
    const tmpl = templates.find(t => t.id === detail.templateId);

    const currentParams = detail.params || {};

    let paramsHtml = '';
    if (tmpl && tmpl.params && tmpl.params.length > 0) {
      paramsHtml = tmpl.params.map(p => {
        const currentVal = currentParams[p.key] ?? p.default;
        return `
        <div class="cq-param-group">
          <div class="cq-param-header">
            <span class="cq-param-label">${p.name}</span>
            <span class="cq-param-value" id="val-edit-${p.key}">${currentVal}</span>
          </div>
          <input type="range" class="cq-slider" id="sl-edit-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${currentVal}" step="${p.step || 1}"
            oninput="document.getElementById('val-edit-${p.key}').textContent=this.value">
        </div>`;
      }).join('');
    } else {
      paramsHtml = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无可编辑参数</div>';
    }

    body.innerHTML = `
      <div style="margin-bottom:var(--cq-space-3);">
        <label class="cq-label">策略名称</label>
        <input type="text" class="cq-input" id="edit-strategy-name" value="${escapeHtml(detail.name)}">
      </div>
      <div style="border-top:1px solid var(--cq-border-subtle);padding-top:var(--cq-space-3);">
        ${paramsHtml}
      </div>`;
  } catch (err) {
    body.innerHTML = `<div class="cq-empty-state" style="padding:var(--cq-space-6);"><h3>${escapeHtml(err.message)}</h3></div>`;
  }
}

async function submitStrategyEdit() {
  const instanceId = window._editingStrategyId;
  if (!instanceId) return;

  const name = document.getElementById('edit-strategy-name')?.value.trim();
  const params = {};
  document.querySelectorAll('#strategy-edit-body input[type="range"]').forEach(sl => {
    const key = sl.id.replace('sl-edit-', '');
    params[key] = parseFloat(sl.value);
  });

  try {
    await api.updateStrategy(instanceId, { name, params });
    showToast('策略已更新', 'success');
    closeStrategyEditModal();
    loadStrategyPage();
  } catch (err) {
    showToast('更新失败: ' + err.message, 'error');
  }
}

function closeStrategyEditModal() {
  const modal = document.getElementById('strategy-edit-modal');
  if (modal) modal.classList.remove('is-visible');
  window._editingStrategyId = null;
}
