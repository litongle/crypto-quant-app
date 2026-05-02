/**
 * 策略中心页面逻辑 v3 - 药丸选择器 + 内联表单
 */
let selectedTemplateId = null;

/* ── 策略图标映射 ── */
const STRATEGY_ICONS = {
  ma:    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>',
  rsi:   '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M7 16l4-8 4 4 5-8"/></svg>',
  boll:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 12C2 6.5 6.5 2 12 2s10 4.5 10 10-4.5 10-10 10S2 17.5 2 12z"/><path d="M6 12C6 8.7 8.7 6 12 6s6 2.7 6 6-2.7 6-6 6-6-2.7-6-6z"/></svg>',
  grid:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/></svg>',
  mart:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="23 6 13.5 15.5 8.5 10.5 1 18"/><polyline points="17 6 23 6 23 12"/></svg>',
  rule:  '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>',
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

  accountSelect.innerHTML = '<option value="">模拟模式(不下单)</option>' +
    filtered.map(a => `<option value="${a.id}">${escapeHtml(a.account_name || a.exchange)} (${escapeHtml(a.exchange)})</option>`).join('');

  if (filtered.length === 0) {
    const opt = document.createElement('option');
    opt.disabled = true;
    opt.textContent = '- 该交易所暂无已连接账户 -';
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

    window._strategyInstances = instances;
    window._cachedTemplates = templates;
    renderTemplatePills(templates);
    renderInstanceList(instances);
  } catch (err) {
    container.innerHTML = `
      <div class="cq-card cq-empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        <h3>${escapeHtml(err.message)}</h3>
      </div>`;
  }
}

const TEMPLATE_GROUPS = [
  {
    title: '快速启动',
    hint: '点击模板快速创建并启动策略实例',
    ids: ['ma_cross', 'rsi', 'bollinger', 'grid', 'martingale', 'rsi_layered', 'dca', 'multi_symbol'],
  },
  {
    title: '自定义创建',
    hint: '从规则构建器开始,组合指标条件生成策略',
    ids: ['rule_custom'],
  },
  {
    title: '我的策略',
    hint: '你已创建的策略实例,点击可编辑',
    ids: [],
    dynamicKey: 'myStrategies',
  },
];

function renderTemplateButton(t) {
  const pillId = t.id;
  const isInst = t._isInstancePill;
  // 系统模板 → quickLaunch / 自定义/实例 → selectTemplate
  const isSystemTemplate = !isInst && t.id !== 'rule_custom';
  const clickAction = isSystemTemplate
    ? `quickLaunchTemplate('${t.id}')`
    : `selectTemplate('${t.id}')`;
  // 实例药丸状态标签
  let instTag = '';
  if (isInst) {
    const st = t._instanceStatus;
    if (st === 'running') instTag = '<span class="cq-pill__tag" style="font-size:10px;color:var(--cq-profit);margin-left:4px;">运行中</span>';
    else if (st === 'draft') instTag = '<span class="cq-pill__tag" style="font-size:10px;color:var(--cq-text-tertiary);margin-left:4px;">草稿</span>';
    else instTag = '<span class="cq-pill__tag" style="font-size:10px;color:var(--cq-text-tertiary);margin-left:4px;">已停止</span>';
  }
  const isSelected = isInst
    ? (window._editingInstanceId === t._instanceId)  // 编辑模式按实例ID匹配
    : (selectedTemplateId === t.id);
  return `
    <button class="cq-pill${isSelected ? ' is-selected' : ''}" id="pill-${pillId}" onclick="${clickAction}" title="${escapeHtml(t.description || t.name)}">
      <div class="cq-pill__icon">${getStrategyIcon(t.icon || t.id)}</div>
      <span class="cq-pill__name">${escapeHtml(t.name)}</span>
      ${instTag}
      <div class="cq-pill__check">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
      </div>
    </button>
  `;
}

/* ── 从策略实例构造"我的策略"动态药丸 ── */
function _buildMyStrategyPills(instances) {
  if (!instances || instances.length === 0) return [];
  return instances.map(inst => ({
    id: 'inst_' + inst.id,
    name: inst.name,
    description: inst.templateName + ' · ' + (inst.symbol || ''),
    icon: inst.templateId || inst._templateId || 'default',
    strategyType: inst.templateId === 'rule_custom' ? 'rule' : inst.templateId,
    _instanceId: inst.id,
    _isInstancePill: true,
    _instanceStatus: inst.status,
    _templateId: inst.templateId,
  }));
}

/* ── 渲染分组模板选择器 ── */
function renderTemplatePills(templates) {
  const el = document.getElementById('template-list');
  if (!templates || templates.length === 0) {
    el.innerHTML = '<div style="color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">暂无策略模板</div>';
    return;
  }

  const templateMap = new Map(templates.map(t => [t.id, t]));
  const instances = window._strategyInstances || [];
  const myStrategyPills = _buildMyStrategyPills(instances);

  const groupedIds = new Set(TEMPLATE_GROUPS.flatMap(group => group.ids));
  const groups = TEMPLATE_GROUPS.map(group => {
    const staticTemplates = group.ids.map(id => templateMap.get(id)).filter(Boolean);
    // 动态注入"我的策略"实例药丸
    const dynamicPills = group.dynamicKey === 'myStrategies' ? myStrategyPills : [];
    return {
      ...group,
      templates: [...staticTemplates, ...dynamicPills],
    };
  }).filter(group => group.templates.length > 0);

  const ungroupedTemplates = templates.filter(t => !groupedIds.has(t.id));
  if (ungroupedTemplates.length > 0) {
    const systemGroup = groups.find(group => group.title === '系统模板');
    if (systemGroup) {
      systemGroup.templates.push(...ungroupedTemplates);
    } else {
      groups.push({ title: '系统模板', hint: '内置示例模板,可直接配置运行', templates: ungroupedTemplates });
    }
  }

  el.innerHTML = groups.map(group => `

    <div class="cq-template-group">
      <div class="cq-template-group__header">
        <span class="cq-template-group__title">${group.title}</span>
        <span class="cq-template-group__hint">${group.hint}</span>
      </div>
      <div class="cq-template-group__pills">
        ${group.templates.map(renderTemplateButton).join('')}
      </div>
    </div>
  `).join('');
}


/* ── 渲染实例列表 ── */
function renderInstanceList(instances) {
  const el = document.getElementById('instance-list');
  if (!instances || instances.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2a4 4 0 0 1 4 4c0 1.95-1.4 3.58-3.25 3.93"/><path d="M8.5 8.5L5 12l3.5 3.5"/><path d="M15.5 8.5L19 12l-3.5 3.5"/><circle cx="12" cy="18" r="3"/></svg>
        <h3>暂无策略实例</h3>
        <p>点击上方模板,快速启动你的第一个策略</p>
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

    // 运行时长
    let runDuration = '';
    if (inst.status === 'running' && inst.createdAt) {
      const created = new Date(inst.createdAt);
      const now = new Date();
      const diffMs = now - created;
      const hours = Math.floor(diffMs / 3600000);
      const mins = Math.floor((diffMs % 3600000) / 60000);
      if (hours >= 24) {
        const days = Math.floor(hours / 24);
        runDuration = `${days}天${hours % 24}时`;
      } else if (hours > 0) {
        runDuration = `${hours}时${mins}分`;
      } else {
        runDuration = `${mins}分钟`;
      }
    }
    const runDurationTag = runDuration
      ? `<span class="sep">·</span><span style=\"color:var(--cq-color-profit);\">⏱ ${runDuration}</span>`
      : '';

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
            <span style="font-family:var(--cq-font-mono);">${escapeHtml(inst.symbol || '-')}</span>
            <span class="sep">·</span>
            <span>${totalTrades} 笔交易</span>
            ${runDurationTag}
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
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="${inst.templateId === 'rule_custom' ? `selectTemplate('rule_custom', ${inst.id})` : `showStrategyEdit('${inst.id}')`}" title="编辑策略">
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

/* ── 快速启动系统模板 ── */
async function quickLaunchTemplate(templateId) {
  // 切换药丸选中态
  document.querySelectorAll('.cq-pill').forEach(p => p.classList.remove('is-selected'));
  const pill = document.getElementById('pill-' + templateId);
  if (pill) pill.classList.add('is-selected');

  selectedTemplateId = templateId;
  window._editingInstanceId = null;

  // 展开快速配置面板
  const wrap = document.getElementById('create-form-wrap');
  const templates = window._cachedTemplates || [];
  const tmpl = templates.find(t => t.id === templateId);
  if (!tmpl) { showToast('模板信息加载失败', 'error'); return; }

  // 更新标题
  const titleEl = document.getElementById('create-form-title');
  if (titleEl) titleEl.textContent = `启动 ${tmpl.name}`;

  // 显示表单
  wrap.style.display = 'block';

  // 初始化交易对选择器
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
        return `<option value="${ex.value}">${ex.label}${connected ? ' ✓' : '(未连接)'}</option>`;
      }).join('');
      exSelect.addEventListener('change', () => filterAccountsByExchange());
      exSelect.dataset.initialized = '1';
    }
    filterAccountsByExchange();
  } catch (e) { console.warn('加载交易所账户失败:', e); }

  // 渲染参数控件
  if (tmpl.params && tmpl.params.length > 0) {
    // 过滤掉 rules 类型参数(系统模板不会有,保险起见)
    const nonRuleParams = tmpl.params.filter(p => p.type !== 'rules');
    renderParamSliders(nonRuleParams);
  } else {
    document.getElementById('param-sliders').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
  }

  // 更新按钮文案为"启动策略"
  const btn = document.getElementById('create-strategy-btn');
  if (btn) btn.textContent = '启动策略';
  // 隐藏删除按钮
  const delBtn = document.getElementById('delete-strategy-btn');
  if (delBtn) delBtn.style.display = 'none';

  wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── 选择模板(仅自定义创建 + 实例编辑) ── */
async function selectTemplate(id) {
  // 如果再次点击已选中的药丸,则取消选择
  const isSameInstancePill = id.startsWith('inst_') && window._editingInstanceId === parseInt(id.replace('inst_', ''));
  if (selectedTemplateId === id || isSameInstancePill) {
    deselectTemplate();
    return;
  }

  // 实例药丸:根据策略类型走不同编辑流程
  if (id.startsWith('inst_')) {
    const instanceId = parseInt(id.replace('inst_', ''));
    const inst = (window._strategyInstances || []).find(i => i.id === instanceId);
    if (!inst) return;

    // rule_custom 走规则构建器编辑
    if (inst.templateId === 'rule_custom' || inst._templateId === 'rule_custom') {
      // 设置编辑模式
      window._editingInstanceId = instanceId;
      selectedTemplateId = 'rule_custom';

      // 先展开 rule_custom 表单
      await showCreateForm('rule_custom');

      // 从实例详情加载 rules 到规则构建器
      try {
        const detail = await api.getStrategyDetail(instanceId);
        if (detail.params && detail.params.rules) {
          loadRulesFromDSL(detail.params.rules);
          renderRuleBuilder(); // 重新渲染构建器
        }
        // 填入名称
        const nameEl = document.getElementById('new-strategy-name');
        if (nameEl) nameEl.value = detail.name || '';
      } catch (e) {
        console.warn('加载实例详情失败:', e);
      }
    } else {
      // 非 rule 策略走 slider 编辑弹窗
      showStrategyEdit(String(instanceId));
      return;
    }

    // 更新药丸选中态
    document.querySelectorAll('.cq-pill').forEach(p => p.classList.remove('is-selected'));
    const pill = document.getElementById('pill-' + id);
    if (pill) pill.classList.add('is-selected');

    // 更新标题和按钮文案
    const titleEl = document.getElementById('create-form-title');
    if (titleEl) titleEl.textContent = `编辑 ${inst.name}`;
    const btn = document.getElementById('create-strategy-btn');
    if (btn) btn.textContent = '更新策略';
    // 编辑模式显示删除按钮
    const delBtn = document.getElementById('delete-strategy-btn');
    if (delBtn) delBtn.style.display = 'inline-flex';
    return;
  }

  selectedTemplateId = id;

  // 切换到非实例药丸时,清除编辑模式并重置规则构建器状态
  window._editingInstanceId = null;
  _ruleBuilderState = {
    buyRules: [], sellRules: [],
    buyLogic: 'AND', sellLogic: 'AND',
    stopLossPct: 3, takeProfitPct: 6, confidenceBase: 0.7,
    _nextId: 1,
  };

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
  window._editingInstanceId = null;
  // 重置规则构建器状态
  _ruleBuilderState = {
    buyRules: [], sellRules: [],
    buyLogic: 'AND', sellLogic: 'AND',
    stopLossPct: 3, takeProfitPct: 6, confidenceBase: 0.7,
    _nextId: 1,
  };
  document.querySelectorAll('.cq-pill').forEach(p => p.classList.remove('is-selected'));

  const wrap = document.getElementById('create-form-wrap');
  if (wrap) {
    wrap.style.display = 'none';
  }
  // 恢复创建按钮文案
  const btn = document.getElementById('create-strategy-btn');
  if (btn) btn.textContent = '创建策略';
  // 隐藏删除按钮
  const delBtn = document.getElementById('delete-strategy-btn');
  if (delBtn) delBtn.style.display = 'none';
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

  // 初始化交易对选择器(只创建一次)
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
        return `<option value="${ex.value}">${ex.label}${connected ? ' ✓' : '(未连接)'}</option>`;
      }).join('');
      exSelect.addEventListener('change', () => filterAccountsByExchange());
      exSelect.dataset.initialized = '1';
    }
    filterAccountsByExchange();
  } catch (e) { console.warn('加载交易所账户失败:', e); }

  // 加载参数滑块(或规则构建器)
  try {
    if (!tmpl) {
      const allTemplates = await api.getStrategyTemplates();
      window._cachedTemplates = allTemplates;
      const found = allTemplates.find(t => t.id === templateId);
      if (found) {
        if (found.strategyType === 'rule') renderRuleBuilder();
        else if (found.params) renderParamSliders(found.params);
        else document.getElementById('param-sliders').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
      }
    } else {
      if (tmpl.strategyType === 'rule') renderRuleBuilder();
      else if (tmpl.params) renderParamSliders(tmpl.params);
      else document.getElementById('param-sliders').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
    }
  } catch {}

  // 滚动到表单位置
  wrap.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/* ── 渲染参数滑块 ── */
/**
 * 渲染参数控件,按 type 分发:
 *   int / double                → range slider(原行为)
 *   bool                        → checkbox
 *   array_int / array_double    → 单行文本(逗号分隔)
 *   json                        → 多行 textarea(JSON 格式)
 *   rules / 其他                → 跳过(由专用构建器处理)
 */
function renderParamSliders(params) {
  const el = document.getElementById('param-sliders');
  if (!params || params.length === 0) {
    el.innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
    return;
  }

  el.innerHTML = params.map(p => {
    const t = p.type || 'double';
    const desc = p.description
      ? `<div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);margin-top:4px;">${p.description}</div>`
      : '';

    // 跳过专用构建器处理的类型
    if (t === 'rules') return '';

    if (t === 'bool') {
      const checked = p.default ? 'checked' : '';
      return `
        <div class="cq-param-group">
          <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
            <input type="checkbox" id="param-${p.key}" data-key="${p.key}" data-type="bool" ${checked}>
            <span class="cq-param-label">${p.name}</span>
          </label>
          ${desc}
        </div>`;
    }

    if (t === 'array_int' || t === 'array_double') {
      const val = Array.isArray(p.default) ? p.default.join(', ') : (p.default ?? '');
      return `
        <div class="cq-param-group">
          <div class="cq-param-header">
            <span class="cq-param-label">${p.name}</span>
          </div>
          <input type="text" class="cq-input" id="param-${p.key}" data-key="${p.key}" data-type="${t}"
            value="${val}" placeholder="逗号分隔,如: 30, 25, 20"
            style="width:100%;padding:6px 10px;border:1px solid var(--cq-border);border-radius:4px;">
          ${desc}
        </div>`;
    }

    if (t === 'json') {
      const val = typeof p.default === 'string' ? p.default : JSON.stringify(p.default);
      return `
        <div class="cq-param-group">
          <div class="cq-param-header">
            <span class="cq-param-label">${p.name}</span>
          </div>
          <textarea class="cq-input" id="param-${p.key}" data-key="${p.key}" data-type="json"
            rows="3" style="width:100%;padding:6px 10px;border:1px solid var(--cq-border);border-radius:4px;font-family:monospace;font-size:var(--cq-text-sm);">${val}</textarea>
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
        <div class="cq-param-group">
          <div class="cq-param-header">
            <span class="cq-param-label">${p.name}</span>
          </div>
          <select class="cq-input" id="param-${p.key}" data-key="${p.key}" data-type="select">
            ${optsHtml}
          </select>
          ${desc}
        </div>`;
    }

    // int / double - range slider
    return `
      <div class="cq-param-group">
        <div class="cq-param-header">
          <span class="cq-param-label">${p.name}</span>
          <span class="cq-param-value" id="val-${p.key}">${p.default}</span>
        </div>
        <input type="range" class="cq-slider" id="sl-${p.key}" data-key="${p.key}" data-type="${t}"
          min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
          oninput="document.getElementById('val-${p.key}').textContent=this.value">
        ${desc}
      </div>`;
  }).join('');
}

/**
 * 收集 #param-sliders 内所有控件的值,按类型解析。
 * 返回 { paramKey: parsedValue, ... };遇 JSON 解析错抛异常上层捕获。
 */
function collectStrategyParams() {
  const out = {};
  const root = document.getElementById('param-sliders');

  // bool: checkbox
  root.querySelectorAll('input[type="checkbox"][data-key]').forEach(el => {
    out[el.dataset.key] = el.checked;
  });

  // array_int / array_double: text 逗号分隔
  root.querySelectorAll('input[type="text"][data-key]').forEach(el => {
    const t = el.dataset.type;
    const parts = el.value.split(',').map(s => s.trim()).filter(s => s !== '');
    out[el.dataset.key] = parts.map(s => t === 'array_int' ? parseInt(s, 10) : parseFloat(s));
  });

  // select: dropdown
  root.querySelectorAll('select[data-key]').forEach(el => {
    out[el.dataset.key] = el.value;
  });

  // json: textarea
  root.querySelectorAll('textarea[data-key]').forEach(el => {
    const txt = el.value.trim();
    if (txt === '') { out[el.dataset.key] = null; return; }
    try {
      out[el.dataset.key] = JSON.parse(txt);
    } catch (e) {
      throw new Error(`参数 "${el.dataset.key}" JSON 格式错误: ${e.message}`);
    }
  });

  // int / double: range slider(排除规则构建器内部的)
  root.querySelectorAll('input[type="range"][data-key]:not(.cq-rule-builder input)').forEach(el => {
    const t = el.dataset.type;
    out[el.dataset.key] = t === 'int' ? parseInt(el.value, 10) : parseFloat(el.value);
  });

  return out;
}

/* ── 创建/启动策略实例 ── */
async function createStrategyInstance() {
  if (!selectedTemplateId) { showToast('请先选择策略模板', 'warn'); return; }

  const name = document.getElementById('new-strategy-name').value.trim();
  if (!name) { showToast('请输入策略名称', 'warn'); return; }

  const exchange = document.getElementById('new-strategy-exchange').value;
  const symbol = window._strategySymbolSel ? window._strategySymbolSel.getValue() : 'BTCUSDT';
  const accountEl = document.getElementById('new-strategy-account');
  const accountId = accountEl ? (parseInt(accountEl.value) || undefined) : undefined;

  // 判断是否系统模板(快速启动模式)
  const isSystemTemplate = selectedTemplateId !== 'rule_custom' &&
    !window._editingInstanceId &&
    (window._cachedTemplates || []).some(t => t.id === selectedTemplateId && t.id !== 'rule_custom');

  let params;
  try {
    params = collectStrategyParams();
  } catch (e) {
    showToast(e.message, 'error');
    return;
  }

  // 规则策略:从构建器生成 rules JSON
  const isRuleTemplate = (window._cachedTemplates || []).find(t => t.id === selectedTemplateId)?.strategyType === 'rule';
  if (isRuleTemplate) {
    const buyEmpty = _ruleBuilderState.buyRules.length === 0;
    const sellEmpty = _ruleBuilderState.sellRules.length === 0;
    if (buyEmpty && sellEmpty) {
      showToast('请至少添加一个买入或卖出条件', 'warn');
      return;
    }
    params.rules = buildRulesDSL();
  }

  try {
    let instanceId;
    if (window._editingInstanceId) {
      // 编辑模式:更新已有策略
      await api.updateStrategy(window._editingInstanceId, { name, params });
      instanceId = window._editingInstanceId;
      showToast('策略已更新!', 'success');
    } else {
      const result = await api.createStrategyInstance({
        name,
        templateId: selectedTemplateId,
        exchange,
        symbol,
        accountId,
        params,
      });
      instanceId = parseInt(result.id);
      showToast('策略创建成功!', 'success');
    }

    // 快速启动模式:创建后自动 start
    if (isSystemTemplate && instanceId) {
      try {
        await api.startStrategy(instanceId);
        showToast('策略已启动!', 'success');
      } catch (e) {
        showToast('策略已创建但启动失败: ' + e.message, 'warn');
      }
    }

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

  const bodyHtml = isRunning
    ? `<p style="color:var(--cq-text-secondary);margin-bottom:8px;">该策略<strong style="color:var(--cq-color-loss);">正在运行</strong>，将先停止再删除。</p>
       <div class="cq-alert cq-alert--warn" style="padding:8px 12px;border-radius:4px;font-size:var(--cq-text-sm);">
         <span style="font-weight:600;">⚠️ 不可逆操作</span>：删除后所有交易记录和绩效数据将永久丢失。
       </div>`
    : `<p style="color:var(--cq-text-secondary);margin-bottom:8px;">确认删除此策略？</p>
       <div class="cq-alert cq-alert--warn" style="padding:8px 12px;border-radius:4px;font-size:var(--cq-text-sm);">
         <span style="font-weight:600;">⚠️ 不可逆操作</span>：删除后所有交易记录和绩效数据将永久丢失。
       </div>`;

  const confirmed = await confirmDangerous(
    `删除策略：${escapeHtml(inst?.name || '未知')}`,
    bodyHtml
  );
  if (!confirmed) return;

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
    body.innerHTML = `<div class="cq-empty-state" style="padding:var(--cq-space-6);"><h3>${escapeHtml(err.message)}</h3><p>暂无绩效数据,策略需运行产生交易后才会有绩效</p></div>`;
  }
}

function renderStrategyPerformance(perf) {
  const body = document.getElementById('strategy-perf-body');
  if (!body) return;

  const totalReturn = Number(perf.total_return_pct ?? perf.totalReturn ?? perf.total_return ?? 0);
  const sharpeRatio = Number(perf.sharpe_ratio ?? perf.sharpeRatio ?? 0);
  const maxDrawdown = Number(perf.max_drawdown_pct ?? perf.maxDrawdown ?? perf.max_drawdown ?? 0);
  const winRate = Number(perf.win_rate ?? perf.winRate ?? 0);
  const profitFactor = Number(perf.profit_loss_ratio ?? perf.profitFactor ?? perf.profit_factor ?? 0);
  const totalTrades = Number(perf.total_trades ?? perf.totalTrades ?? 0);
  const annualReturn = Number(perf.annualized_return_pct ?? perf.annualReturn ?? perf.annual_return ?? 0);
  const calmarRatio = Number(perf.calmar_ratio ?? perf.calmarRatio ?? 0);
  const avgProfit = Number(perf.avg_profit ?? perf.avgProfit ?? 0);
  const avgLoss = Number(perf.avg_loss ?? perf.avgLoss ?? 0);
  const tradingDays = Number(perf.trading_days ?? 0);
  const maxConsecWins = Number(perf.max_consecutive_wins ?? 0);
  const maxConsecLosses = Number(perf.max_consecutive_losses ?? 0);
  const maxDrawdownHours = Number(perf.max_drawdown_duration_hours ?? 0);

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
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">交易天数</span><span class="cq-metrics-detail__value cq-num">${tradingDays} 天</span></div>
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">最大连胜</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-profit);">${maxConsecWins}</span></div>
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">最大连亏</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-loss);">${maxConsecLosses}</span></div>
      <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">回撤持续</span><span class="cq-metrics-detail__value cq-num">${maxDrawdownHours.toFixed(1)}h</span></div>
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
        const t = p.type || 'double';
        const desc = p.description
          ? `<div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);margin-top:4px;">${p.description}</div>`
          : '';

        if (t === 'rules') return ''; // rules 由规则构建器处理

        if (t === 'bool') {
          const checked = currentVal ? 'checked' : '';
          return `
          <div class="cq-param-group">
            <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
              <input type="checkbox" id="sl-edit-${p.key}" data-key="${p.key}" data-type="bool" ${checked}>
              <span class="cq-param-label">${p.name}</span>
            </label>
            ${desc}
          </div>`;
        }

        if (t === 'array_int' || t === 'array_double') {
          const val = Array.isArray(currentVal) ? currentVal.join(', ') : (currentVal ?? '');
          return `
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">${p.name}</span>
            </div>
            <input type="text" class="cq-input" id="sl-edit-${p.key}" data-key="${p.key}" data-type="${t}"
              value="${val}" placeholder="逗号分隔,如: 30, 25, 20"
              style="width:100%;padding:6px 10px;border:1px solid var(--cq-border);border-radius:4px;">
            ${desc}
          </div>`;
        }

        if (t === 'select') {
          const options = Array.isArray(p.options) ? p.options : [];
          const optsHtml = options.map(opt => {
            const v = (opt && typeof opt === 'object') ? opt.value : opt;
            const lbl = (opt && typeof opt === 'object') ? (opt.label ?? opt.value) : opt;
            const sel = String(v) === String(currentVal) ? ' selected' : '';
            return `<option value="${v}"${sel}>${lbl}</option>`;
          }).join('');
          return `
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">${p.name}</span>
            </div>
            <select class="cq-input" id="sl-edit-${p.key}" data-key="${p.key}" data-type="select">
              ${optsHtml}
            </select>
            ${desc}
          </div>`;
        }

        if (t === 'json') {
          const val = typeof currentVal === 'string' ? currentVal : JSON.stringify(currentVal);
          return `
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">${p.name}</span>
            </div>
            <textarea class="cq-input" id="sl-edit-${p.key}" data-key="${p.key}" data-type="json"
              rows="3" style="width:100%;padding:6px 10px;border:1px solid var(--cq-border);border-radius:4px;font-family:monospace;font-size:var(--cq-text-sm);">${val}</textarea>
            ${desc}
          </div>`;
        }

        // int / double - range slider
        return `
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">${p.name}</span>
              <span class="cq-param-value" id="val-edit-${p.key}">${currentVal}</span>
            </div>
            <input type="range" class="cq-slider" id="sl-edit-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${currentVal}" step="${p.step || 1}"
              oninput="document.getElementById('val-edit-${p.key}').textContent=this.value">
            ${desc}
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

  // 收集所有类型的参数控件
  // range slider
  document.querySelectorAll('#strategy-edit-body input[type="range"]').forEach(sl => {
    const key = sl.id.replace('sl-edit-', '');
    const step = parseFloat(sl.step) || 1;
    params[key] = step >= 1 ? parseInt(sl.value, 10) : parseFloat(sl.value);
  });
  // checkbox
  document.querySelectorAll('#strategy-edit-body input[type="checkbox"][data-key]').forEach(el => {
    params[el.dataset.key] = el.checked;
  });
  // text (array types)
  document.querySelectorAll('#strategy-edit-body input[type="text"][data-key]').forEach(el => {
    const t = el.dataset.type;
    const parts = el.value.split(',').map(s => s.trim()).filter(s => s !== '');
    params[el.dataset.key] = parts.map(s => t === 'array_int' ? parseInt(s, 10) : parseFloat(s));
  });
  // select
  document.querySelectorAll('#strategy-edit-body select[data-key]').forEach(el => {
    params[el.dataset.key] = el.value;
  });
  // textarea (json)
  document.querySelectorAll('#strategy-edit-body textarea[data-key]').forEach(el => {
    const txt = el.value.trim();
    if (txt === '') { params[el.dataset.key] = null; return; }
    try {
      params[el.dataset.key] = JSON.parse(txt);
    } catch (e) {
      showToast(`参数 "${el.dataset.key}" JSON 格式错误`, 'error');
      return;
    }
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

/* ═══════════════════════════════════════════════════════════════
   规则构建器 - 自定义规则策略的可视化条件编辑器
   ═══════════════════════════════════════════════════════════════ */

/* ── 指标元数据(与 seed_data.py indicators 同步) ── */
const RULE_INDICATORS = [
  { key: 'price',          name: '价格',       type: 'value',  params: [] },
  { key: 'rsi',            name: 'RSI',        type: 'value',  params: [{ key: 'period', name: '周期', default: 14, type: 'int', min: 2, max: 50 }] },
  { key: 'ma',             name: '均线MA',     type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 2, max: 200 }] },
  { key: 'ema',            name: '指数均线EMA',type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 2, max: 200 }] },
  { key: 'bollinger_upper',name: '布林上轨',   type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 5, max: 50 },{ key: 'std_dev', name: '标准差', default: 2.0, type: 'double', min: 1.0, max: 4.0 }] },
  { key: 'bollinger_lower',name: '布林下轨',   type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 5, max: 50 },{ key: 'std_dev', name: '标准差', default: 2.0, type: 'double', min: 1.0, max: 4.0 }] },
  { key: 'bollinger_pct',  name: '布林位置%',  type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 5, max: 50 },{ key: 'std_dev', name: '标准差', default: 2.0, type: 'double', min: 1.0, max: 4.0 }] },
  { key: 'volume',         name: '成交量',     type: 'value',  params: [] },
  { key: 'volume_ma',      name: '成交量均线', type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 2, max: 100 }] },
  { key: 'atr',            name: 'ATR波幅',   type: 'value',  params: [{ key: 'period', name: '周期', default: 14, type: 'int', min: 2, max: 50 }] },
  { key: 'macd',           name: 'MACD柱',    type: 'value',  params: [{ key: 'fast', name: '快线', default: 12, type: 'int', min: 2, max: 50 },{ key: 'slow', name: '慢线', default: 26, type: 'int', min: 5, max: 100 },{ key: 'signal', name: '信号线', default: 9, type: 'int', min: 2, max: 50 }] },
  { key: 'ma_cross',       name: '均线交叉',   type: 'event',  params: [{ key: 'fast_period', name: '快线周期', default: 5, type: 'int', min: 2, max: 50 },{ key: 'slow_period', name: '慢线周期', default: 20, type: 'int', min: 5, max: 200 }] },
  { key: 'macd_cross',     name: 'MACD交叉',   type: 'event',  params: [{ key: 'fast', name: '快线', default: 12, type: 'int', min: 2, max: 50 },{ key: 'slow', name: '慢线', default: 26, type: 'int', min: 5, max: 100 },{ key: 'signal', name: '信号线', default: 9, type: 'int', min: 2, max: 50 }] },
  { key: 'price_change_pct',name: '涨跌幅%',   type: 'value',  params: [{ key: 'period', name: 'K线数', default: 1, type: 'int', min: 1, max: 50 }] },
  { key: 'stoch_k',        name: 'KDJ-K值',   type: 'value',  params: [{ key: 'period', name: '周期', default: 14, type: 'int', min: 2, max: 50 }] },
  { key: 'stoch_d',        name: 'KDJ-D值',   type: 'value',  params: [{ key: 'k_period', name: 'K周期', default: 14, type: 'int', min: 2, max: 50 },{ key: 'd_period', name: 'D周期', default: 3, type: 'int', min: 1, max: 20 }] },
  { key: 'cci',            name: 'CCI',       type: 'value',  params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 5, max: 50 }] },
  { key: 'dema',           name: '双指数均线DEMA', type: 'value', params: [{ key: 'period', name: '周期', default: 20, type: 'int', min: 2, max: 200 }] },
  { key: 'obv',            name: '能量潮OBV', type: 'value',  params: [] },
];

const VALUE_OPERATORS = [
  { key: '>',  name: '>' },
  { key: '>=', name: '>=' },
  { key: '<',  name: '<' },
  { key: '<=', name: '<=' },
  { key: '==', name: '==' },
];

const EVENT_OPERATORS = [
  { key: 'cross_up',   name: '上穿' },
  { key: 'cross_down', name: '下穿' },
];

/* ── 规则构建器状态 ── */
let _ruleBuilderState = {
  buyRules: [],   // [{ id, indicator, params, operator, value }]
  sellRules: [],  // same
  buyLogic: 'AND',
  sellLogic: 'AND',
  stopLossPct: 3,
  takeProfitPct: 6,
  confidenceBase: 0.7,
  _nextId: 1,
};

/* ── 从已保存的 rules DSL 反向填充规则构建器 ── */
function loadRulesFromDSL(rules) {
  if (!rules) return;
  let nextId = 1;
  function parseGroup(group, side) {
    if (!group || !group.conditions) return;
    if (group.logic) {
      if (side === 'buy') _ruleBuilderState.buyLogic = group.logic;
      else _ruleBuilderState.sellLogic = group.logic;
    }
    const list = side === 'buy' ? 'buyRules' : 'sellRules';
    _ruleBuilderState[list] = group.conditions.map(c => {
      const id = nextId++;
      return {
        id,
        indicator: c.indicator,
        params: c.params || {},
        operator: c.operator,
        value: c.value,
      };
    });
  }
  parseGroup(rules.buy_rules, 'buy');
  parseGroup(rules.sell_rules, 'sell');
  if (rules.risk) {
    _ruleBuilderState.stopLossPct = rules.risk.stop_loss_percent ?? 3;
    _ruleBuilderState.takeProfitPct = rules.risk.take_profit_percent ?? 6;
    _ruleBuilderState.confidenceBase = rules.risk.confidence_base ?? 0.7;
  }
  _ruleBuilderState._nextId = nextId;
}

function _newCondition(indicatorKey) {
  const ind = RULE_INDICATORS.find(i => i.key === indicatorKey) || RULE_INDICATORS[0];
  const params = {};
  ind.params.forEach(p => { params[p.key] = p.default; });
  return {
    id: _ruleBuilderState._nextId++,
    indicator: indicatorKey || 'price',
    params,
    operator: ind.type === 'event' ? 'cross_up' : '>',
    value: ind.type === 'event' ? '' : 0,
  };
}

/* ── 渲染规则构建器到 #param-sliders ── */
function renderRuleBuilder() {
  const el = document.getElementById('param-sliders');
  if (!el) return;

  el.innerHTML = `
    <div class="cq-rule-builder">
      <!-- 买入条件 -->
      <div class="cq-rule-section">
        <div class="cq-rule-section__header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-profit)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14"/><path d="M5 12h14"/></svg>
          <span>买入条件</span>
          <div class="cq-rule-logic-toggle">
            <button class="cq-logic-btn${_ruleBuilderState.buyLogic === 'AND' ? ' is-active' : ''}" onclick="setRuleLogic('buy','AND')">AND</button>
            <button class="cq-logic-btn${_ruleBuilderState.buyLogic === 'OR' ? ' is-active' : ''}" onclick="setRuleLogic('buy','OR')">OR</button>
          </div>
        </div>
        <div class="cq-rule-conditions" id="rule-buy-conditions"></div>
        <button class="cq-btn cq-btn--secondary cq-btn--sm cq-add-condition-btn" onclick="addRuleCondition('buy')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加条件
        </button>
      </div>

      <!-- 卖出条件 -->
      <div class="cq-rule-section">
        <div class="cq-rule-section__header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-loss)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M5 12h14"/></svg>
          <span>卖出条件</span>
          <div class="cq-rule-logic-toggle">
            <button class="cq-logic-btn${_ruleBuilderState.sellLogic === 'AND' ? ' is-active' : ''}" onclick="setRuleLogic('sell','AND')">AND</button>
            <button class="cq-logic-btn${_ruleBuilderState.sellLogic === 'OR' ? ' is-active' : ''}" onclick="setRuleLogic('sell','OR')">OR</button>
          </div>
        </div>
        <div class="cq-rule-conditions" id="rule-sell-conditions"></div>
        <button class="cq-btn cq-btn--secondary cq-btn--sm cq-add-condition-btn" onclick="addRuleCondition('sell')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加条件
        </button>
      </div>

      <!-- 风控参数 -->
      <div class="cq-rule-section">
        <div class="cq-rule-section__header">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-warning)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
          <span>风控参数</span>
        </div>
        <div class="cq-rule-risk-grid">
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">止损 %</span>
              <span class="cq-param-value" id="val-stopLossPct">${_ruleBuilderState.stopLossPct}</span>
            </div>
            <input type="range" class="cq-slider" min="0.5" max="20" step="0.5" value="${_ruleBuilderState.stopLossPct}"
              oninput="document.getElementById('val-stopLossPct').textContent=this.value; _ruleBuilderState.stopLossPct=parseFloat(this.value)">
          </div>
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">止盈 %</span>
              <span class="cq-param-value" id="val-takeProfitPct">${_ruleBuilderState.takeProfitPct}</span>
            </div>
            <input type="range" class="cq-slider" min="1" max="50" step="1" value="${_ruleBuilderState.takeProfitPct}"
              oninput="document.getElementById('val-takeProfitPct').textContent=this.value; _ruleBuilderState.takeProfitPct=parseFloat(this.value)">
          </div>
          <div class="cq-param-group">
            <div class="cq-param-header">
              <span class="cq-param-label">信号置信度</span>
              <span class="cq-param-value" id="val-confidenceBase">${(_ruleBuilderState.confidenceBase * 100).toFixed(0)}%</span>
            </div>
            <input type="range" class="cq-slider" min="0.1" max="1.0" step="0.05" value="${_ruleBuilderState.confidenceBase}"
              oninput="document.getElementById('val-confidenceBase').textContent=Math.round(this.value*100)+'%'; _ruleBuilderState.confidenceBase=parseFloat(this.value)">
          </div>
        </div>
      </div>

      <!-- 预览 + 校验 -->
      <div class="cq-rule-preview">
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="previewRules()">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>
          预览规则
        </button>
        <div id="rule-preview-text" class="cq-rule-preview-text" style="display:none;"></div>
        <div id="rule-validation-msg" class="cq-rule-validation-msg" style="display:none;"></div>
      </div>
    </div>
  `;

  renderRuleConditions('buy');
  renderRuleConditions('sell');
}

/* ── 渲染条件列表 ── */
function renderRuleConditions(side) {
  const container = document.getElementById(`rule-${side}-conditions`);
  if (!container) return;

  const conditions = side === 'buy' ? _ruleBuilderState.buyRules : _ruleBuilderState.sellRules;

  if (conditions.length === 0) {
    container.innerHTML = '<div class="cq-rule-empty">尚未添加条件,点击下方按钮添加</div>';
    return;
  }

  container.innerHTML = conditions.map((cond, idx) => {
    const ind = RULE_INDICATORS.find(i => i.key === cond.indicator) || RULE_INDICATORS[0];
    const isEvent = ind.type === 'event';
    const operators = isEvent ? EVENT_OPERATORS : VALUE_OPERATORS;

    // 指标参数输入
    const paramInputs = ind.params.map(p => {
      const val = cond.params[p.key] ?? p.default;
      return `<div class="cq-cond-param">
        <span class="cq-cond-param__label">${p.name}</span>
        <input type="number" class="cq-input cq-cond-param__input" value="${val}"
          min="${p.min || ''}" max="${p.max || ''}" step="${p.type === 'int' ? 1 : 0.1}"
          onchange="updateCondParam('${side}',${cond.id},'${p.key}',this.value)">
      </div>`;
    }).join('');

    // 比较值/参考值(事件型为另一个指标选择)
    let valueInput = '';
    if (isEvent) {
      valueInput = `
        <select class="cq-input cq-cond-value" onchange="updateCondValue('${side}',${cond.id},this.value)" style="width:120px;">
          <option value="0" ${cond.value === '0' ? 'selected' : ''}>零线</option>
          ${RULE_INDICATORS.filter(i => i.type === 'value').map(i =>
            `<option value="${i.key}" ${cond.value === i.key ? 'selected' : ''}>${i.name}</option>`
          ).join('')}
        </select>`;
    } else {
      valueInput = `<input type="number" class="cq-input cq-cond-value" value="${cond.value}" step="any"
        placeholder="阈值" onchange="updateCondValue('${side}',${cond.id},this.value)">`;
    }

    return `
      <div class="cq-rule-condition" data-cond-id="${cond.id}">
        <div class="cq-cond-row">
          <select class="cq-input cq-cond-indicator" onchange="changeCondIndicator('${side}',${cond.id},this.value)">
            ${RULE_INDICATORS.map(i => `<option value="${i.key}" ${i.key === cond.indicator ? 'selected' : ''}>${i.name}</option>`).join('')}
          </select>
          <select class="cq-input cq-cond-operator" onchange="updateCondOperator('${side}',${cond.id},this.value)">
            ${operators.map(o => `<option value="${o.key}" ${o.key === cond.operator ? 'selected' : ''}>${o.name}</option>`).join('')}
          </select>
          ${valueInput}
          <button class="cq-cond-remove" onclick="removeRuleCondition('${side}',${cond.id})" title="删除条件">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
          </button>
        </div>
        ${paramInputs ? `<div class="cq-cond-params">${paramInputs}</div>` : ''}
      </div>
    `;
  }).join('');
}

/* ── 条件操作 ── */
function addRuleCondition(side) {
  const cond = _newCondition('price');
  if (side === 'buy') _ruleBuilderState.buyRules.push(cond);
  else _ruleBuilderState.sellRules.push(cond);
  renderRuleConditions(side);
}

function removeRuleCondition(side, condId) {
  if (side === 'buy') _ruleBuilderState.buyRules = _ruleBuilderState.buyRules.filter(c => c.id !== condId);
  else _ruleBuilderState.sellRules = _ruleBuilderState.sellRules.filter(c => c.id !== condId);
  renderRuleConditions(side);
}

function changeCondIndicator(side, condId, indicatorKey) {
  const list = side === 'buy' ? _ruleBuilderState.buyRules : _ruleBuilderState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (!cond) return;

  const ind = RULE_INDICATORS.find(i => i.key === indicatorKey) || RULE_INDICATORS[0];
  cond.indicator = indicatorKey;
  cond.params = {};
  ind.params.forEach(p => { cond.params[p.key] = p.default; });

  // 切换算子
  if (ind.type === 'event') {
    cond.operator = 'cross_up';
    cond.value = '0';
  } else {
    cond.operator = '>';
    cond.value = 0;
  }

  renderRuleConditions(side);
}

function updateCondOperator(side, condId, operator) {
  const list = side === 'buy' ? _ruleBuilderState.buyRules : _ruleBuilderState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (cond) cond.operator = operator;
}

function updateCondValue(side, condId, value) {
  const list = side === 'buy' ? _ruleBuilderState.buyRules : _ruleBuilderState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (!cond) return;
  const ind = RULE_INDICATORS.find(i => i.key === cond.indicator);
  if (ind && ind.type === 'event') cond.value = value;
  else cond.value = parseFloat(value) || 0;
}

function updateCondParam(side, condId, paramKey, value) {
  const list = side === 'buy' ? _ruleBuilderState.buyRules : _ruleBuilderState.sellRules;
  const cond = list.find(c => c.id === condId);
  if (cond) cond.params[paramKey] = parseFloat(value) || 0;
}

function setRuleLogic(side, logic) {
  if (side === 'buy') _ruleBuilderState.buyLogic = logic;
  else _ruleBuilderState.sellLogic = logic;
  renderRuleBuilder();
}

/* ── 从 UI 状态生成规则 DSL JSON ── */
function buildRulesDSL() {
  function buildGroup(conditions, logic) {
    if (conditions.length === 0) return { logic: 'AND', conditions: [] };
    return {
      logic,
      conditions: conditions.map(c => {
        const ind = RULE_INDICATORS.find(i => i.key === c.indicator);
        const cond = {
          indicator: c.indicator,
          params: { ...c.params },
          operator: c.operator,
        };
        // 非事件型直接传数值
        if (ind && ind.type !== 'event') {
          cond.value = c.value;
        } else {
          cond.value = c.value; // 事件型: '0' 表示零线, 或指标 key
        }
        return cond;
      }),
    };
  }

  return {
    buy_rules: buildGroup(_ruleBuilderState.buyRules, _ruleBuilderState.buyLogic),
    sell_rules: buildGroup(_ruleBuilderState.sellRules, _ruleBuilderState.sellLogic),
    risk: {
      stop_loss_percent: _ruleBuilderState.stopLossPct,
      take_profit_percent: _ruleBuilderState.takeProfitPct,
      confidence_base: _ruleBuilderState.confidenceBase,
    },
  };
}

/* ── 预览规则 + 后端校验 ── */
async function previewRules() {
  const dsl = buildRulesDSL();
  const previewEl = document.getElementById('rule-preview-text');
  const msgEl = document.getElementById('rule-validation-msg');

  // 本地预览
  if (previewEl) {
    previewEl.style.display = 'block';
    previewEl.textContent = JSON.stringify(dsl, null, 2);
  }

  // 后端校验
  if (msgEl) {
    msgEl.style.display = 'block';
    msgEl.className = 'cq-rule-validation-msg';
    msgEl.innerHTML = '<span class="cq-spin" style="display:inline-block;width:14px;height:14px;border:2px solid var(--cq-text-tertiary);border-top-color:var(--cq-color-primary);border-radius:50%;animation:cq-spin .7s linear infinite;vertical-align:middle;"></span> 校验中...';
  }

  try {
    const result = await api.validateRules(dsl);
    if (msgEl) {
      if (result.valid) {
        msgEl.className = 'cq-rule-validation-msg cq-rule-valid';
        msgEl.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-profit)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/></svg> 规则校验通过 - ${escapeHtml(result.description)}`;
      } else {
        msgEl.className = 'cq-rule-validation-msg cq-rule-invalid';
        msgEl.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-loss)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="vertical-align:middle;"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg> ${result.errors.map(e => escapeHtml(e)).join('; ')}`;
      }
    }
  } catch (err) {
    if (msgEl) {
      msgEl.className = 'cq-rule-validation-msg cq-rule-invalid';
      msgEl.textContent = '校验请求失败: ' + err.message;
    }
  }
}
