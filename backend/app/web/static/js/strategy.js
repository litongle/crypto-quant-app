/**
 * 策略中心页面逻辑 v5 - 策略仓库 / 工作台
 */
let selectedTemplateId = null;
let strategyLibraryFilter = 'all';
let workbenchBusy = false;
let workbenchInitialSnapshot = null;

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

const TEMPLATE_GROUPS = [
  {
    title: '快速模板',
    hint: '选中后在工作台配置，保存进入策略仓库，按需启动到实盘或模拟运行',
    ids: ['ma_cross', 'rsi', 'bollinger', 'grid', 'martingale', 'rsi_layered', 'dca', 'multi_symbol'],
  },
];

const CUSTOM_TEMPLATE_ID = 'rule_custom';

function getStrategyIcon(templateId) {
  const key = String(templateId || '').toLowerCase();
  for (const [iconKey, iconSvg] of Object.entries(STRATEGY_ICONS)) {
    if (key.includes(iconKey)) return iconSvg;
  }
  return STRATEGY_ICONS.default;
}

function resetRuleBuilderState() {
  _ruleBuilderState = {
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

function getExchangeLabel(exchange) {
  return { binance: 'Binance', okx: 'OKX', htx: 'HTX' }[exchange] || exchange || '-';
}

function getStatusTag(status, instance = null) {
  if (status === 'running' && instance?.runtimeActive === false) {
    return '<span class="cq-tag cq-tag--warn">运行异常</span>';
  }
  if (status === 'running') {
    return '<span class="cq-tag cq-tag--profit"><span class="cq-pulse-dot" style="width:6px;height:6px;margin-right:4px;"></span>运行中</span>';
  }
  if (status === 'draft') return '<span class="cq-tag cq-tag--info">未启动</span>';
  if (status === 'paused') return '<span class="cq-tag cq-tag--warn">已暂停</span>';
  return '<span class="cq-tag cq-tag--neutral">已停止</span>';
}

function getModeTag(instance) {
  const isLive = Boolean(instance.isLive);
  return isLive
    ? '<span class="cq-tag cq-tag--profit" style="font-size:10px;padding:1px 6px;">实盘</span>'
    : '<span class="cq-tag cq-tag--neutral" style="font-size:10px;padding:1px 6px;">模拟</span>';
}

function formatMoney(value) {
  const num = Number(value ?? 0);
  return `${num >= 0 ? '+' : ''}$${num.toFixed(2)}`;
}

function formatPercent(value, digits = 1) {
  const num = Number(value ?? 0);
  return `${num >= 0 ? '+' : ''}${num.toFixed(digits)}%`;
}

function formatTimestamp(ts) {
  if (!ts) return '--';
  const date = new Date(ts);
  if (Number.isNaN(date.getTime())) return '--';
  return date.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function normalizeWorkbenchValue(value) {
  if (value === undefined || value === null || value === '') return null;
  return value;
}

function stableStringify(value) {
  if (Array.isArray(value)) {
    return `[${value.map(stableStringify).join(',')}]`;
  }
  if (value && typeof value === 'object') {
    return `{${Object.keys(value).sort().map(key => `${JSON.stringify(key)}:${stableStringify(value[key])}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

function formatRuntime(instance) {
  const startValue = instance.lastStartedAt || instance.startedAt;
  if (!startValue) return '待同步';
  const start = new Date(startValue);
  if (Number.isNaN(start.getTime())) return '待同步';
  const diffMs = Date.now() - start.getTime();
  if (diffMs <= 0) return '刚刚启动';

  const minutes = Math.floor(diffMs / 60000);
  const hours = Math.floor(diffMs / 3600000);
  const days = Math.floor(hours / 24);
  if (days > 0) return `${days}天${hours % 24}时`;
  if (hours > 0) return `${hours}时${minutes % 60}分`;
  return `${minutes}分钟`;
}

function normalizeWorkspaceState(instance) {
  const workspaceState = String(instance.workspaceState || '').toLowerCase();
  const status = String(instance.status || '').toLowerCase();

  if (status === 'running' && instance.runtimeActive === false) return 'library';
  if (status === 'running') return 'running';
  if (['draft', 'editing', 'workbench', 'workspace', 'drafts'].includes(workspaceState)) return 'draft';
  if (['running', 'active', 'live'].includes(workspaceState)) return 'running';
  if (['library', 'saved', 'warehouse', 'catalog'].includes(workspaceState)) return 'library';
  if (status === 'paused' || status === 'stopped' || status === 'idle') return 'library';
  return 'library';
}

function groupStrategyInstances(instances) {
  const groups = { running: [], library: [], drafts: [] };
  for (const instance of instances || []) {
    const bucket = normalizeWorkspaceState(instance);
    if (bucket === 'running') groups.running.push(instance);
    else if (bucket === 'draft') groups.drafts.push(instance);
    else groups.library.push(instance);
  }
  return groups;
}

const STRATEGY_LIBRARY_FILTERS = [
  { key: 'all', label: '全部' },
  { key: 'running', label: '运行中' },
  { key: 'idle', label: '未运行' },
];

function getFormalStrategies(instances) {
  const groups = groupStrategyInstances(instances || []);
  return [...groups.running, ...groups.library].sort((left, right) => {
    const leftBucket = normalizeWorkspaceState(left) === 'running' ? 0 : 1;
    const rightBucket = normalizeWorkspaceState(right) === 'running' ? 0 : 1;
    if (leftBucket !== rightBucket) return leftBucket - rightBucket;

    const leftTime = new Date(left.lastStartedAt || left.startedAt || left.updatedAt || left.createdAt || 0).getTime();
    const rightTime = new Date(right.lastStartedAt || right.startedAt || right.updatedAt || right.createdAt || 0).getTime();
    return rightTime - leftTime;
  });
}

function getFilteredLibraryStrategies(instances) {
  if (strategyLibraryFilter === 'running') {
    return (instances || []).filter(instance => normalizeWorkspaceState(instance) === 'running');
  }
  if (strategyLibraryFilter === 'idle') {
    return (instances || []).filter(instance => normalizeWorkspaceState(instance) !== 'running');
  }
  return instances || [];
}

function getLibraryFilterCounts(instances) {
  const counts = { all: 0, running: 0, idle: 0 };
  for (const instance of instances || []) {
    counts.all += 1;
    if (normalizeWorkspaceState(instance) === 'running') counts.running += 1;
    else counts.idle += 1;
  }
  return counts;
}

function findTemplate(templateId) {
  return (window._cachedTemplates || []).find(template => template.id === templateId);
}

function getTemplateName(instance) {
  return instance.templateName || findTemplate(instance.templateId)?.name || instance.templateId || '策略';
}

function renderLoadingSkeletons() {
  const libraryList = document.getElementById('strategy-library-list');
  const libraryFilters = document.getElementById('strategy-library-filters');
  const draftList = document.getElementById('workbench-draft-list');
  const emptyState = document.getElementById('workbench-empty');
  const formWrap = document.getElementById('create-form-wrap');
  if (libraryFilters) libraryFilters.innerHTML = '<div class="cq-skeleton" style="height:36px;width:220px;border-radius:999px;"></div>';
  if (libraryList) libraryList.innerHTML = '<div class="cq-skeleton" style="height:140px;border-radius:var(--cq-radius-lg);"></div>';
  if (draftList) draftList.innerHTML = '<div class="cq-skeleton" style="height:44px;width:220px;border-radius:999px;"></div>';
  if (emptyState) emptyState.style.display = 'none';
  if (formWrap) formWrap.style.display = 'none';
  workbenchInitialSnapshot = null;
}

async function loadStrategyPage() {
  renderLoadingSkeletons();

  try {
    window._connectedAccounts = await api.getExchangeAccounts();
  } catch (error) {
    console.warn('预加载交易所账户失败:', error);
  }

  try {
    const [templates, instances] = await Promise.all([
      api.getStrategyTemplates().catch(() => []),
      api.getStrategyInstances().catch(() => []),
    ]);

    window._cachedTemplates = templates;
    window._strategyInstances = instances;

    const groups = groupStrategyInstances(instances);
    renderStrategyLibrary(getFormalStrategies(instances));
    renderTemplatePills(templates);
    renderWorkbenchDraftList(groups.drafts);

    const draftId = chooseWorkbenchDraft(groups.drafts);
    if (draftId) {
      await openDraftInWorkbench(draftId, { scroll: false });
      return;
    }

    if (selectedTemplateId) {
      await openTemplateWorkbench(selectedTemplateId, { scroll: false });
      return;
    }

    deselectTemplate({ keepSelection: false, silent: true });
  } catch (error) {
    const message = `<div class="cq-card cq-empty-state"><h3>${escapeHtml(error.message)}</h3></div>`;
    document.getElementById('strategy-library-list').innerHTML = message;
    const filterEl = document.getElementById('strategy-library-filters');
    if (filterEl) filterEl.innerHTML = '';
    document.getElementById('workbench-draft-list').innerHTML = '';
    showWorkbenchEmpty();
  }
}

function chooseWorkbenchDraft(drafts) {
  const currentId = window._editingInstanceId ? Number(window._editingInstanceId) : null;
  const focusedId = window._strategyFocusDraftId ? Number(window._strategyFocusDraftId) : null;
  const focusedSourceId = window._strategyFocusSourceInstanceId ? Number(window._strategyFocusSourceInstanceId) : null;

  const pick = drafts.find(item => item.id === focusedId)
    || drafts.find(item => item.id === currentId)
    || drafts.find(item => focusedSourceId && Number(item.sourceInstanceId) === focusedSourceId)
    || drafts[0];

  window._strategyFocusDraftId = null;
  window._strategyFocusSourceInstanceId = null;
  return pick ? pick.id : null;
}

function renderStrategyLibrary(instances) {
  const el = document.getElementById('strategy-library-list');
  const filterEl = document.getElementById('strategy-library-filters');
  if (!el) return;

  const counts = getLibraryFilterCounts(instances);
  if (filterEl) {
    filterEl.innerHTML = STRATEGY_LIBRARY_FILTERS.map(filter => `
      <button
        type="button"
        class="cq-strategy-filter-tab${strategyLibraryFilter === filter.key ? ' is-active' : ''}"
        onclick="setStrategyLibraryFilter('${filter.key}')"
      >
        <span>${filter.label}</span>
        <span class="cq-strategy-filter-tab__count">${counts[filter.key] ?? 0}</span>
      </button>
    `).join('');
  }

  const filteredInstances = getFilteredLibraryStrategies(instances);
  if (!instances || instances.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <rect x="3" y="3" width="7" height="7" rx="1"/>
          <rect x="14" y="3" width="7" height="7" rx="1"/>
          <rect x="3" y="14" width="7" height="7" rx="1"/>
          <rect x="14" y="14" width="7" height="7" rx="1"/>
        </svg>
        <h3>策略仓库还是空的</h3>
        <p>先从下面的「快速模板」选一个开始，保存后正式策略就会出现在这里。</p>
        <button class="cq-btn cq-btn--primary" onclick="document.getElementById('workbench-section')?.scrollIntoView({behavior:'smooth',block:'start'})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          从模板新建
        </button>
      </div>`;
    return;
  }

  if (!filteredInstances || filteredInstances.length === 0) {
    const emptyMap = {
      running: {
        title: '当前没有运行中的策略',
        text: '从工作台或未运行策略里启动后，会立即出现在这里。',
      },
      idle: {
        title: '当前没有未运行策略',
        text: '已停止的正式策略会出现在这里，方便继续编辑或再次启动。',
      },
      all: {
        title: '策略仓库还是空的',
        text: '先在工作台保存一个草案，保存后就会进入这里。',
      },
    };
    const emptyState = emptyMap[strategyLibraryFilter] || emptyMap.all;
    el.innerHTML = `
      <div class="cq-card cq-empty-state">
        <h3>${emptyState.title}</h3>
        <p>${emptyState.text}</p>
      </div>`;
    return;
  }

  el.innerHTML = `<div class="cq-strategy-list">${filteredInstances.map(renderLibraryCard).join('')}</div>`;
}

function renderLibraryCard(instance) {
  const pnl = Number(instance.totalPnl ?? 0);
  const totalTrades = Number(instance.totalTrades ?? 0);
  const runtimeActive = instance.runtimeActive !== false;
  const isRunning = normalizeWorkspaceState(instance) === 'running';
  const isZombie = String(instance.status || '').toLowerCase() === 'running' && !runtimeActive;
  const runtime = formatRuntime(instance);
  const lastStarted = formatTimestamp(instance.lastStartedAt);
  const lastRun = formatTimestamp(instance.lastRunAt);
  const lastStopped = formatTimestamp(instance.lastStoppedAt);
  const primaryAction = isRunning
    ? `
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="toggleStrategy(${instance.id}, 'stop')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>
          停止
        </button>`
    : isZombie
    ? `
        <button class="cq-btn cq-btn--primary cq-btn--sm" onclick="toggleStrategy(${instance.id}, 'start')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 2v6h-6"/><path d="M3 12a9 9 0 0 1 15.5-6.36L21 8"/><path d="M3 22v-6h6"/><path d="M21 12a9 9 0 0 1-15.5 6.36L3 16"/></svg>
          重新启动
        </button>`
    : `
        <button class="cq-btn cq-btn--primary cq-btn--sm" onclick="toggleStrategy(${instance.id}, 'start')">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
          启动
        </button>`;
  const editActionLabel = '复制为草案';
  const metrics = isRunning
    ? `
        <span>累计交易 ${totalTrades} 笔</span>
        <span class="sep">·</span>
        <span>本次运行 ${escapeHtml(runtime)}</span>
        <span class="sep">·</span>
        <span>启动时间 ${escapeHtml(lastStarted)}</span>`
    : isZombie
    ? `
        <span>Runner 未活跃</span>
        <span class="sep">·</span>
        <span>最近成功执行 ${escapeHtml(lastRun)}</span>
        <span class="sep">·</span>
        <span>${escapeHtml(instance.runtimeMessage || '请重新启动策略')}</span>`
    : (!instance.lastStartedAt && !instance.lastStoppedAt)
    ? `
        <span>累计交易 ${totalTrades} 笔</span>
        <span class="sep">·</span>
        <span>从未启动</span>
        <span class="sep">·</span>
        <span>创建于 ${escapeHtml(formatTimestamp(instance.createdAt))}</span>`
    : `
        <span>${totalTrades} 笔交易</span>
        <span class="sep">·</span>
        <span>上次启动 ${escapeHtml(lastStarted)}</span>
        <span class="sep">·</span>
        <span>上次停止 ${escapeHtml(lastStopped)}</span>`;

  return `
    <div class="cq-card cq-instance-card">
      <div class="cq-instance-card__header">
        <div class="cq-instance-card__info">
          <div class="cq-instance-card__name-row">
            <span class="cq-instance-card__name">${escapeHtml(instance.name)}</span>
            ${getStatusTag(instance.status, instance)}
            ${getModeTag(instance)}
          </div>
          <div class="cq-instance-card__meta">
            <span>${escapeHtml(getTemplateName(instance))}</span>
            <span class="sep">·</span>
            <span>${escapeHtml(getExchangeLabel(instance.exchange))}</span>
            <span class="sep">·</span>
            <span class="cq-num">${escapeHtml(instance.symbol || '-')}</span>
            <span class="sep">·</span>
            ${metrics}
          </div>
        </div>
        <div class="cq-instance-card__pnl">
          <div class="cq-instance-card__pnl-value" style="color:${pnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${formatMoney(pnl)}</div>
          <div class="cq-instance-card__pnl-rate">${formatPercent(instance.winRate ?? 0, 1)} 胜率</div>
        </div>
      </div>
      <div class="cq-instance-card__actions">
        ${primaryAction}
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="cloneStrategyToWorkbench(${instance.id})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
          ${editActionLabel}
        </button>
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="showStrategyPerformance(${instance.id})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
          绩效
        </button>
        ${isRunning ? '' : `
        <button class="cq-btn cq-btn--danger cq-btn--sm" onclick="deleteStrategyInst(${instance.id})">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
          删除
        </button>`}
      </div>
    </div>`;
}

function setStrategyLibraryFilter(filterKey) {
  strategyLibraryFilter = STRATEGY_LIBRARY_FILTERS.some(filter => filter.key === filterKey) ? filterKey : 'all';
  renderStrategyLibrary(getFormalStrategies(window._strategyInstances || []));
}

function renderTemplateButton(template) {
  const isSelected = !window._editingInstanceId && selectedTemplateId === template.id;
  const desc = template.description || '';
  return `
    <button class="cq-template-card${isSelected ? ' is-selected' : ''}" id="pill-${template.id}" onclick="quickLaunchTemplate('${template.id}')" title="${escapeHtml(desc || template.name)}">
      <span class="cq-template-card__icon">${getStrategyIcon(template.icon || template.id)}</span>
      <span class="cq-template-card__body">
        <span class="cq-template-card__name">${escapeHtml(template.name)}</span>
        ${desc ? `<span class="cq-template-card__desc">${escapeHtml(desc)}</span>` : ''}
      </span>
      <svg class="cq-template-card__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="9 18 15 12 9 6"/>
      </svg>
    </button>`;
}

function renderTemplatePills(templates) {
  const el = document.getElementById('template-list');
  if (!el) return;
  if (!templates || templates.length === 0) {
    el.innerHTML = '<div style="color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">暂无策略模板</div>';
    return;
  }

  const templateMap = new Map(templates.map(template => [template.id, template]));
  const customTemplate = templateMap.get(CUSTOM_TEMPLATE_ID) || null;
  const groupedIds = new Set([...TEMPLATE_GROUPS.flatMap(group => group.ids), CUSTOM_TEMPLATE_ID]);
  const groups = TEMPLATE_GROUPS.map(group => ({
    ...group,
    templates: group.ids.map(id => templateMap.get(id)).filter(Boolean),
  })).filter(group => group.templates.length > 0);

  const restTemplates = templates.filter(template => !groupedIds.has(template.id));
  if (restTemplates.length > 0) {
    groups.push({
      title: '其他模板',
      hint: '保留已有能力，直接在工作台里继续配置',
      templates: restTemplates,
    });
  }

  const groupHtml = groups.map(group => `
    <div class="cq-template-group">
      <div class="cq-template-group__header">
        <span class="cq-template-group__title">${group.title}</span>
        <span class="cq-template-group__hint">${group.hint}</span>
      </div>
      <div class="cq-template-card-grid">
        ${group.templates.map(renderTemplateButton).join('')}
      </div>
    </div>`).join('');

  el.innerHTML = groupHtml + (customTemplate ? renderTemplateBanner(customTemplate) : '');
}

function renderTemplateBanner(template) {
  const desc = template.description || '用规则构建器组合指标条件，拼出你自己的策略草案';
  return `
    <div class="cq-template-banner">
      <div class="cq-template-banner__body">
        <div class="cq-template-banner__title">不满意预设？自己拼一个</div>
        <div class="cq-template-banner__desc">${escapeHtml(desc)}</div>
      </div>
      <button class="cq-btn cq-btn--primary cq-template-banner__action" onclick="quickLaunchTemplate('${template.id}')">
        ${escapeHtml(template.name || '自定义规则策略')}
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
      </button>
    </div>`;
}

function renderWorkbenchDraftList(drafts) {
  const el = document.getElementById('workbench-draft-list');
  if (!el) return;

  if (!drafts || drafts.length === 0) {
    el.innerHTML = '<span style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">暂无草案</span>';
    return;
  }

  el.innerHTML = drafts.map(draft => {
    const isActive = Number(window._editingInstanceId) === Number(draft.id);
    return `
      <button class="cq-workbench-draft-pill${isActive ? ' is-active' : ''}" onclick="selectTemplate('draft_${draft.id}')">
        <div class="cq-pill__icon">${getStrategyIcon(draft.templateId)}</div>
        <span class="cq-workbench-draft-pill__text">
          <span class="cq-workbench-draft-pill__name">${escapeHtml(draft.name)}</span>
          <span class="cq-workbench-draft-pill__meta">${escapeHtml(getTemplateName(draft))}</span>
        </span>
      </button>`;
  }).join('');
}

function showWorkbenchEmpty() {
  const emptyState = document.getElementById('workbench-empty');
  const formWrap = document.getElementById('create-form-wrap');
  if (emptyState) emptyState.style.display = 'block';
  if (formWrap) formWrap.style.display = 'none';
}

function showWorkbenchForm() {
  const emptyState = document.getElementById('workbench-empty');
  const formWrap = document.getElementById('create-form-wrap');
  if (emptyState) emptyState.style.display = 'none';
  if (formWrap) formWrap.style.display = 'block';
}

function ensureTradeHintListeners() {
  const accountSelect = document.getElementById('new-strategy-account');
  const paramsRoot = document.getElementById('param-sliders');
  if (accountSelect && !accountSelect.dataset.tradeHintBound) {
    accountSelect.addEventListener('change', () => updateStrategyTradeHint());
    accountSelect.dataset.tradeHintBound = '1';
  }
  if (paramsRoot && !paramsRoot.dataset.tradeHintBound) {
    paramsRoot.addEventListener('change', () => updateStrategyTradeHint());
    paramsRoot.dataset.tradeHintBound = '1';
  }
}

function markTemplateSelection(templateId) {
  document.querySelectorAll('#template-list .cq-template-card').forEach(card => card.classList.remove('is-selected'));
  if (!templateId) return;
  const pill = document.getElementById(`pill-${templateId}`);
  if (pill) pill.classList.add('is-selected');
}

function markDraftSelection(draftId) {
  window._editingInstanceId = draftId ? Number(draftId) : null;
  renderWorkbenchDraftList(groupStrategyInstances(window._strategyInstances || []).drafts);
}

/** 根据当前选中的交易所过滤账户下拉 */
function filterAccountsByExchange() {
  const exSelect = document.getElementById('new-strategy-exchange');
  const accountSelect = document.getElementById('new-strategy-account');
  if (!exSelect || !accountSelect) return;

  const template = findTemplate(selectedTemplateId);
  if (template && !template.liveTradingSupported) {
    accountSelect.disabled = true;
    accountSelect.innerHTML = '<option value="">仅信号/模拟运行（该模板暂不支持自动下单）</option>';
    updateStrategyTradeHint(template);
    return;
  }

  const selectedExchange = exSelect.value;
  const accounts = window._connectedAccounts || [];
  const filtered = accounts.filter(account => account.exchange === selectedExchange);

  accountSelect.disabled = false;
  accountSelect.innerHTML = '<option value="">模拟模式(不下单)</option>'
    + filtered.map(account => `<option value="${account.id}">${escapeHtml(account.account_name || account.exchange)} (${escapeHtml(account.exchange)})</option>`).join('');

  if (filtered.length === 0) {
    const opt = document.createElement('option');
    opt.disabled = true;
    opt.textContent = '- 该交易所暂无已连接账户 -';
    accountSelect.appendChild(opt);
  }

  updateStrategyTradeHint(template);
}

function updateStrategyTradeHint(template = findTemplate(selectedTemplateId)) {
  const hintEl = document.getElementById('strategy-live-hint');
  if (!hintEl) return;

  if (!template) {
    hintEl.textContent = '选择已连接的交易所账户启用实盘自动下单，留空则仅产生模拟信号';
    return;
  }

  if (!template.liveTradingSupported) {
    hintEl.textContent = '该模板暂不支持真实自动下单，仅可做信号或模拟运行';
    return;
  }

  let params = {};
  try {
    params = collectStrategyParams();
  } catch {}
  const autoTradeEnabled = Boolean(params.auto_trade);
  const accountId = document.getElementById('new-strategy-account')?.value;
  if (autoTradeEnabled && accountId) {
    hintEl.textContent = '已开启自动下单，启动后将按策略信号执行真实下单';
    return;
  }
  if (autoTradeEnabled) {
    hintEl.textContent = '已开启自动下单，但还未绑定交易所账户，启动时会被拦截';
    return;
  }
  hintEl.textContent = '默认仅产生信号；勾选参数区的自动下单并绑定账户后才会真实下单';
}

async function ensureWorkbenchFormInfra() {
  if (typeof preloadSymbolSelectorData === 'function') {
    await preloadSymbolSelectorData();
  }

  if (!window._strategySymbolSel) {
    const selectorHost = document.getElementById('strategy-symbol-selector');
    if (selectorHost) {
      window._strategySymbolSel = new SymbolSelector({
        containerId: 'strategy-symbol-selector',
        value: 'BTCUSDT',
        exchangeFilter: 'new-strategy-exchange',
      });
    }
  } else if (typeof window._strategySymbolSel.refreshData === 'function') {
    window._strategySymbolSel.refreshData();
  }

  try {
    const accounts = window._connectedAccounts || await api.getExchangeAccounts();
    window._connectedAccounts = accounts;
    const exSelect = document.getElementById('new-strategy-exchange');
    if (exSelect && !exSelect.dataset.initialized) {
      const connectedExchanges = [...new Set(accounts.map(account => account.exchange).filter(Boolean))];
      const allExchanges = [
        { value: 'binance', label: 'Binance' },
        { value: 'okx', label: 'OKX' },
        { value: 'htx', label: 'HTX' },
      ];
      exSelect.innerHTML = allExchanges.map(exchange => {
        const connected = connectedExchanges.includes(exchange.value);
        return `<option value="${exchange.value}">${exchange.label}${connected ? ' ✓' : '(未连接)'}</option>`;
      }).join('');
      exSelect.addEventListener('change', () => filterAccountsByExchange());
      exSelect.dataset.initialized = '1';
    }
    filterAccountsByExchange();
  } catch (error) {
    console.warn('加载交易所账户失败:', error);
  }
}

async function quickLaunchTemplate(templateId) {
  if (!await ensureWorkbenchCanLeave('切换模板将丢失当前未保存的修改，确定继续吗？')) return;
  return openTemplateWorkbench(templateId);
}

async function selectTemplate(id) {
  if (!await ensureWorkbenchCanLeave('切换工作台内容将丢失当前未保存的修改，确定继续吗？', id)) return;
  if (String(id).startsWith('draft_')) {
    return openDraftInWorkbench(Number(String(id).replace('draft_', '')));
  }
  return openTemplateWorkbench(id);
}

function deselectTemplate(options = {}) {
  const { keepSelection = false, silent = false } = options;
  if (!keepSelection) selectedTemplateId = null;
  window._editingInstanceId = null;
  resetRuleBuilderState();
  workbenchInitialSnapshot = null;
  markTemplateSelection(null);
  renderWorkbenchDraftList(groupStrategyInstances(window._strategyInstances || []).drafts);
  showWorkbenchEmpty();
  const statusTag = document.getElementById('create-form-status');
  if (statusTag) {
    statusTag.style.display = 'none';
    statusTag.textContent = '';
  }
  const deleteBtn = document.getElementById('delete-strategy-btn');
  if (deleteBtn) deleteBtn.style.display = 'none';
  if (!silent) {
    const nameInput = document.getElementById('new-strategy-name');
    if (nameInput) nameInput.value = '';
  }
}

async function openTemplateWorkbench(templateId, options = {}) {
  const template = findTemplate(templateId);
  if (!template) {
    showToast('模板信息加载失败', 'error');
    return;
  }

  selectedTemplateId = templateId;
  window._editingInstanceId = null;
  await showCreateForm(templateId, {
    title: `新建草案 · ${template.name}`,
    statusText: '未保存',
    strategy: {
      name: '',
      exchange: 'binance',
      symbol: 'BTCUSDT',
      accountId: '',
      params: {},
    },
  });

  markTemplateSelection(templateId);
  markDraftSelection(null);
  if (options.scroll !== false) {
    document.getElementById('workbench-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
}

async function openDraftInWorkbench(instanceId, options = {}) {
  try {
    const detail = await api.getStrategyDetail(instanceId);
    selectedTemplateId = detail.templateId;
    await showCreateForm(detail.templateId, {
      title: `编辑草案 · ${detail.name}`,
      statusText: detail.sourceInstanceId ? '复制草案' : '草案',
      strategy: detail,
    });
    markTemplateSelection(null);
    markDraftSelection(instanceId);
    if (options.scroll !== false) {
      document.getElementById('workbench-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  } catch (error) {
    showToast(`加载草案失败: ${error.message}`, 'error');
  }
}

async function showCreateForm(templateId, options = {}) {
  const template = findTemplate(templateId);
  if (!template) {
    showToast('模板信息加载失败', 'error');
    return;
  }

  showWorkbenchForm();
  await ensureWorkbenchFormInfra();
  ensureTradeHintListeners();
  const strategy = options.strategy || {};
  const titleEl = document.getElementById('create-form-title');
  const statusEl = document.getElementById('create-form-status');
  const deleteBtn = document.getElementById('delete-strategy-btn');

  if (titleEl) titleEl.textContent = options.title || `新建草案 · ${template.name}`;
  if (statusEl) {
    statusEl.textContent = options.statusText || '';
    statusEl.style.display = options.statusText ? 'inline-flex' : 'none';
  }
  if (deleteBtn) deleteBtn.style.display = strategy.id ? 'inline-flex' : 'none';

  resetRuleBuilderState();

  if (template.strategyType === 'rule') {
    if (strategy.params && strategy.params.rules) {
      loadRulesFromDSL(strategy.params.rules);
    }
    renderRuleBuilder();
  } else if (template.params && template.params.length > 0) {
    renderParamSliders(template.params);
    applyParamValues(template.params, strategy.params || {});
  } else {
    document.getElementById('param-sliders').innerHTML = '<div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">此策略无需配置参数</div>';
  }

  const nameInput = document.getElementById('new-strategy-name');
  const exchangeSelect = document.getElementById('new-strategy-exchange');
  const accountSelect = document.getElementById('new-strategy-account');
  if (nameInput) nameInput.value = strategy.name || '';
  if (exchangeSelect) exchangeSelect.value = strategy.exchange || 'binance';
  filterAccountsByExchange();
  if (accountSelect && !accountSelect.disabled) {
    accountSelect.value = strategy.accountId ? String(strategy.accountId) : '';
  }
  if (window._strategySymbolSel && strategy.symbol) {
    try { window._strategySymbolSel.setValue(strategy.symbol); } catch {}
  }
  updateStrategyTradeHint(template);
  captureWorkbenchInitialSnapshot();
}

function applyParamValues(paramDefs, values) {
  for (const param of paramDefs || []) {
    if (param.type === 'rules') continue;
    const value = values[param.key] ?? param.default;
    const input = document.getElementById(`param-${param.key}`) || document.getElementById(`sl-${param.key}`);
    if (!input) continue;

    if (param.type === 'bool') {
      input.checked = Boolean(value);
      continue;
    }

    if (param.type === 'array_int' || param.type === 'array_double') {
      input.value = Array.isArray(value) ? value.join(', ') : (value ?? '');
      continue;
    }

    if (param.type === 'json') {
      input.value = typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2);
      continue;
    }

    input.value = value;
    const valueLabel = document.getElementById(`val-${param.key}`);
    if (valueLabel) valueLabel.textContent = value;
  }
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
  if (!root) return out;

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

  // int / double: range slider
  root.querySelectorAll('input[type="range"][data-key]').forEach(el => {
    const t = el.dataset.type;
    out[el.dataset.key] = t === 'int' ? parseInt(el.value, 10) : parseFloat(el.value);
  });

  return out;
}

function buildCurrentWorkbenchSnapshot() {
  if (!selectedTemplateId) return null;

  const name = document.getElementById('new-strategy-name')?.value?.trim() || '';
  const exchange = document.getElementById('new-strategy-exchange')?.value || 'binance';
  const symbol = window._strategySymbolSel ? window._strategySymbolSel.getValue() : 'BTCUSDT';
  const accountRaw = document.getElementById('new-strategy-account')?.value;
  const accountId = accountRaw ? parseInt(accountRaw, 10) || null : null;

  let params = {};
  try {
    params = collectStrategyParams();
  } catch {
    params = {};
  }

  if (findTemplate(selectedTemplateId)?.strategyType === 'rule') {
    params.rules = buildRulesDSL();
  }

  return {
    templateId: selectedTemplateId,
    editingInstanceId: window._editingInstanceId ? Number(window._editingInstanceId) : null,
    name,
    exchange,
    symbol,
    accountId,
    params,
  };
}

function captureWorkbenchInitialSnapshot() {
  workbenchInitialSnapshot = buildCurrentWorkbenchSnapshot();
}

function hasUnsavedWorkbenchChanges() {
  const formWrap = document.getElementById('create-form-wrap');
  if (!formWrap || formWrap.style.display === 'none' || !workbenchInitialSnapshot) return false;
  return stableStringify(buildCurrentWorkbenchSnapshot()) !== stableStringify(workbenchInitialSnapshot);
}

function isSameWorkbenchTarget(targetId) {
  const currentDraftId = window._editingInstanceId ? `draft_${window._editingInstanceId}` : null;
  const currentTemplateId = !window._editingInstanceId ? selectedTemplateId : null;
  return targetId === currentDraftId || targetId === currentTemplateId;
}

async function ensureWorkbenchCanLeave(message, targetId = null) {
  if (workbenchBusy) return false;
  if (targetId && isSameWorkbenchTarget(targetId)) return true;
  if (!hasUnsavedWorkbenchChanges()) return true;
  return confirmWorkbenchLeave('放弃未保存的更改？', message || '当前工作台还有未保存的修改，继续操作会丢失这些内容。');
}

function setWorkbenchBusyState(busy) {
  workbenchBusy = busy;
  ['save-strategy-btn', 'start-strategy-btn', 'delete-strategy-btn', 'close-workbench-btn'].forEach(id => {
    const element = document.getElementById(id);
    if (element) element.disabled = busy;
  });
}

async function persistWorkbenchStrategy({ startAfterSave }) {
  if (workbenchBusy) return;
  if (!selectedTemplateId) { showToast('请先选择策略模板', 'warn'); return; }

  const name = document.getElementById('new-strategy-name').value.trim();
  if (!name) { showToast('请输入策略名称', 'warn'); return; }

  const exchange = document.getElementById('new-strategy-exchange').value;
  const symbol = window._strategySymbolSel ? window._strategySymbolSel.getValue() : 'BTCUSDT';
  const accountEl = document.getElementById('new-strategy-account');
  const accountId = accountEl ? (parseInt(accountEl.value) || undefined) : undefined;

  let params;
  try {
    params = collectStrategyParams();
  } catch (e) {
    showToast(e.message, 'error');
    return;
  }

  const isRuleTemplate = findTemplate(selectedTemplateId)?.strategyType === 'rule';
  if (isRuleTemplate) {
    const buyEmpty = _ruleBuilderState.buyRules.length === 0;
    const sellEmpty = _ruleBuilderState.sellRules.length === 0;
    if (buyEmpty && sellEmpty) {
      showToast('请至少添加一个买入或卖出条件', 'warn');
      return;
    }
    params.rules = buildRulesDSL();
  }

  setWorkbenchBusyState(true);
  try {
    let instanceId = window._editingInstanceId ? Number(window._editingInstanceId) : null;
    const isEditingDraft = Boolean(window._editingInstanceId);
    if (window._editingInstanceId) {
      const updatePayload = {
        name,
        exchange,
        symbol,
        accountId: accountId ?? null,
        params,
      };
      if (!startAfterSave) {
        updatePayload.workspaceState = 'library';
      }
      await api.updateStrategy(window._editingInstanceId, {
        ...updatePayload,
      });
      captureWorkbenchInitialSnapshot();
      if (!startAfterSave) {
        showToast('策略已保存并进入仓库', 'success');
      }
    } else {
      const result = await api.createStrategyInstance({
        name,
        templateId: selectedTemplateId,
        exchange,
        symbol,
        accountId,
        params,
      });
      instanceId = parseInt(result.id, 10);
      if (!startAfterSave) {
        showToast('策略已保存', 'success');
      }
    }

    if (startAfterSave && instanceId) {
      try {
        await api.startStrategy(instanceId);
        showToast('策略已启动', 'success');
      } catch (err) {
        if (isEditingDraft) {
          showToast(`启动失败，草案仍保留在工作台: ${err.message}`, 'error');
          return;
        }
        deselectTemplate({ keepSelection: false, silent: true });
        await loadStrategyPage();
        document.getElementById('strategy-library-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
        showToast(`启动失败，策略已保存到仓库: ${err.message}`, 'error');
        return;
      }
    }

    deselectTemplate({ keepSelection: false, silent: true });
    await loadStrategyPage();
  } catch (err) {
    showToast((startAfterSave ? '启动失败: ' : '保存失败: ') + err.message, 'error');
  } finally {
    setWorkbenchBusyState(false);
  }
}

async function saveStrategyToLibrary() {
  return persistWorkbenchStrategy({ startAfterSave: false });
}

async function startStrategyFromWorkbench() {
  return persistWorkbenchStrategy({ startAfterSave: true });
}

async function createStrategyInstance() {
  return startStrategyFromWorkbench();
}

async function toggleStrategy(instanceId, action) {
  try {
    if (action === 'start') await api.startStrategy(instanceId);
    else await api.stopStrategy(instanceId);
    showToast(`策略已${action === 'start' ? '启动' : '停止'}`, 'success');
    await loadStrategyPage();
  } catch (err) {
    showToast('操作失败: ' + err.message, 'error');
  }
}

async function deleteStrategyInst(instanceId) {
  const numericId = Number(instanceId);
  const inst = window._strategyInstances?.find(i => Number(i.id) === numericId);
  const isRunning = normalizeWorkspaceState(inst || {}) === 'running';
  const isDraft = normalizeWorkspaceState(inst || {}) === 'draft';

  const bodyHtml = isRunning
    ? `<p style="color:var(--cq-text-secondary);margin-bottom:8px;">该策略<strong style="color:var(--cq-color-loss);">正在运行</strong>，将先停止再删除。</p>
       <div class="cq-alert cq-alert--warn" style="padding:8px 12px;border-radius:4px;font-size:var(--cq-text-sm);">
         <span style="font-weight:600;">⚠️ 不可逆操作</span>：删除后所有交易记录和绩效数据将永久丢失。
       </div>`
    : isDraft
    ? `<p style="color:var(--cq-text-secondary);margin-bottom:8px;">确认删除这个工作台草案？</p>
       <div class="cq-alert cq-alert--warn" style="padding:8px 12px;border-radius:4px;font-size:var(--cq-text-sm);">
         <span style="font-weight:600;">⚠️ 不可逆操作</span>：删除后草案内容将永久丢失。
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
      await api.stopStrategy(numericId);
    }
    await api.deleteStrategy(numericId);
    if (Number(window._editingInstanceId) === numericId) {
      window._editingInstanceId = null;
      selectedTemplateId = null;
    }
    showToast(isDraft ? '草案已删除' : '策略已删除', 'success');
    await loadStrategyPage();
  } catch (err) {
    showToast('删除失败: ' + err.message, 'error');
  }
}

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

async function showStrategyEdit(instanceId) {
  return cloneStrategyToWorkbench(instanceId);
}

async function submitStrategyEdit() {
  showToast('旧编辑弹窗已下线，请在工作台中编辑策略', 'warn');
  closeStrategyEditModal();
  document.getElementById('workbench-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function closeStrategyEditModal() {
  const modal = document.getElementById('strategy-edit-modal');
  if (modal) modal.classList.remove('is-visible');
}

async function cloneStrategyToWorkbench(instanceId) {
  if (!await ensureWorkbenchCanLeave('复制为草案并打开工作台，会丢失当前未保存的修改，确定继续吗？', `clone_${instanceId}`)) return;
  try {
    const result = await api.cloneStrategyToDraft(instanceId);
    const clonedId = Number(result?.id ?? result?.instanceId ?? result?.instance_id ?? 0);
    if (clonedId) {
      window._strategyFocusDraftId = clonedId;
    } else {
      window._strategyFocusSourceInstanceId = Number(instanceId);
    }
    selectedTemplateId = null;
    window._editingInstanceId = null;
    showToast('已打开工作台草案', 'success');
    await loadStrategyPage();
    document.getElementById('workbench-section')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  } catch (error) {
    showToast(`复制草案失败: ${error.message}`, 'error');
  }
}

async function requestCloseWorkbench() {
  if (!await ensureWorkbenchCanLeave('关闭工作台会丢失当前未保存的修改，确定继续吗？')) return;
  deselectTemplate();
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
