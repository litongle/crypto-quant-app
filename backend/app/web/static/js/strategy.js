/**
 * 策略中心页面逻辑 v2 — 使用设计令牌
 */
let selectedTemplateId = null;

/* ── 策略图标映射 ── */
const STRATEGY_ICONS = {
  ma:    '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  rsi:   '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-8"/></svg>',
  boll:  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12C2 6.5 6.5 2 12 2s10 4.5 10 10-4.5 10-10 10S2 17.5 2 12z"/><path d="M6 12C6 8.7 8.7 6 12 6s6 2.7 6 6-2.7 6-6 6-6-2.7-6-6z"/></svg>',
  grid:  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
  mart:  '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
  default: '<svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93"/><path d="M8.5 8.5L5 12l3.5 3.5"/><path d="M15.5 8.5L19 12l-3.5 3.5"/><circle cx="12" cy="18" r="3"/></svg>',
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

  // 只显示当前交易所的账户
  const filtered = accounts.filter(a => a.exchange === selectedExchange);

  accountSelect.innerHTML = '<option value="">模拟模式（不下单）</option>' +
    filtered.map(a => `<option value="${a.id}">${a.account_name || a.exchange} (${a.exchange})</option>`).join('');

  // 如果该交易所没有已连接账户，显示提示
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

  // 预加载账户数据到全局缓存
  try {
    window._connectedAccounts = await api.getExchangeAccounts();
  } catch (e) { console.warn('预加载交易所账户失败:', e); }

  try {
    const [templates, instances] = await Promise.all([
      api.getStrategyTemplates().catch(() => []),
      api.getStrategyInstances().catch(() => []),
    ]);

    renderTemplateList(templates);
    renderInstanceList(instances);
    // 缓存实例数据供删除时判断运行状态
    window._strategyInstances = instances;
  } catch (err) {
    container.innerHTML = `
      <div class="cq-card cq-empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        <h3>${err.message}</h3>
      </div>`;
  }
}

function renderTemplateList(templates) {
  const el = document.getElementById('template-list');
  if (!templates || templates.length === 0) {
    el.innerHTML = '<div class="cq-card" style="text-align:center;padding:var(--cq-space-6);color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">暂无策略模板</div>';
    return;
  }

  el.innerHTML = templates.map(t => `
    <div class="cq-card cq-strategy-card" id="tmpl-${t.id}" onclick="selectTemplate('${t.id}')" style="margin-bottom:var(--cq-space-3);">
      <div class="cq-strategy-icon">${getStrategyIcon(t.id)}</div>
      <div style="flex:1;min-width:0;">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);margin-bottom:var(--cq-space-1);">
          <span style="font-size:var(--cq-text-md);font-weight:600;color:var(--cq-text-primary);">${t.name}</span>
        </div>
        <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${t.description}</div>
      </div>
      <div style="flex-shrink:0;display:none;" id="check-${t.id}">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg>
      </div>
    </div>
  `).join('');
}

function renderInstanceList(instances) {
  const el = document.getElementById('instance-list');
  if (!instances || instances.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93"/><path d="M8.5 8.5L5 12l3.5 3.5"/><path d="M15.5 8.5L19 12l-3.5 3.5"/><circle cx="12" cy="18" r="3"/></svg>
        <h3>暂无运行中的策略实例</h3>
        <p>选择左侧模板创建你的第一个策略</p>
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

    return `
    <div class="cq-card" style="margin-bottom:var(--cq-space-3);">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div style="min-width:0;">
          <div style="display:flex;align-items:center;gap:var(--cq-space-2);margin-bottom:var(--cq-space-1);flex-wrap:wrap;">
            <span style="font-size:var(--cq-text-md);font-weight:600;color:var(--cq-text-primary);">${inst.name}</span>
            ${statusTag}
            ${modeTag}
          </div>
          <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);display:flex;align-items:center;gap:var(--cq-space-2);flex-wrap:wrap;">
            <span>${inst.templateName}</span>
            <span style="color:var(--cq-border-subtle);">·</span>
            <span>${exchangeLabel}</span>
            <span style="color:var(--cq-border-subtle);">·</span>
            <span style="font-family:'JetBrains Mono',monospace;">${inst.symbol || '—'}</span>
            <span style="color:var(--cq-border-subtle);">·</span>
            <span>${inst.totalTrades} 笔交易</span>
          </div>
        </div>
        <div style="text-align:right;flex-shrink:0;margin-left:var(--cq-space-4);">
          <div class="cq-num" style="font-size:var(--cq-text-md);font-weight:600;color:${inst.totalPnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${inst.totalPnl >= 0 ? '+' : ''}$${inst.totalPnl.toFixed(2)}</div>
          <div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);">${inst.winRate.toFixed(1)}% 胜率</div>
        </div>
      </div>
      <div style="display:flex;gap:var(--cq-space-2);margin-top:var(--cq-space-3);">
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
        <button class="cq-btn cq-btn--danger cq-btn--sm" onclick="deleteStrategyInst('${inst.id}')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          删除
        </button>
      </div>
    </div>`;
  }).join('');
}

async function selectTemplate(id) {
  selectedTemplateId = id;

  document.querySelectorAll('.cq-strategy-card').forEach(c => {
    c.classList.remove('is-selected');
    const checkEl = c.querySelector('[id^="check-"]');
    if (checkEl) checkEl.style.display = 'none';
  });

  const card = document.getElementById('tmpl-' + id);
  if (card) card.classList.add('is-selected');

  const check = document.getElementById('check-' + id);
  if (check) check.style.display = 'block';

  // 显示右侧创建表单
  document.getElementById('create-section').style.display = 'block';

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
    const templates = await api.getStrategyTemplates();
    const tmpl = templates.find(t => t.id === id);
    if (tmpl && tmpl.params) renderParamSliders(tmpl.params);
  } catch {}
}

function renderParamSliders(params) {
  const el = document.getElementById('param-sliders');
  if (!params || params.length === 0) {
    el.innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
    return;
  }

  el.innerHTML = params.map(p => `
    <div style="margin-bottom:var(--cq-space-4);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--cq-space-2);">
        <label style="font-size:var(--cq-text-sm);font-weight:500;color:var(--cq-text-secondary);">${p.name}</label>
        <span class="cq-num" style="font-size:var(--cq-text-sm);font-weight:600;color:var(--cq-color-primary-hover);" id="val-${p.key}">${p.default}</span>
      </div>
      <input type="range" class="cq-slider" id="sl-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
        oninput="document.getElementById('val-${p.key}').textContent=this.value">
    </div>
  `).join('');
}

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
    loadStrategyPage();
  } catch (err) {
    showToast('创建失败: ' + err.message, 'error');
  }
}

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

async function deleteStrategyInst(instanceId) {
  // 找到该实例的当前状态
  const inst = window._strategyInstances?.find(i => i.id === instanceId);
  const isRunning = inst && inst.status === 'running';

  const msg = isRunning
    ? '该策略正在运行，将先停止再删除。确认删除？'
    : '确认删除此策略？此操作不可撤销。';
  if (!confirm(msg)) return;

  try {
    // 如果正在运行，先停止
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
