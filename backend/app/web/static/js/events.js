const eventsPageState = {
  type: '',
  severity: '',
  range: '24h',
  query: '',
  instanceId: '',
  page: 1,
  limit: 20,
  total: 0,
  expandedIds: new Set(),
  // 默认隐藏 system 启停（避免淹没业务事件）；勾选「显示系统事件」或 type=system 时关掉
  hideSystem: true,
};

function presetEventsFilters({ instanceId = '' } = {}) {
  eventsPageState.instanceId = instanceId ? String(instanceId) : '';
  eventsPageState.page = 1;
}

async function loadEventsPage() {
  syncEventsControls();
  await reloadEvents();
}

async function refreshEventsPageIfVisible() {
  if (_currentPage === 'events') {
    await reloadEvents({ preservePage: true });
  }
}

function syncEventsControls() {
  const typeEl = document.getElementById('events-filter-type');
  const sevEl = document.getElementById('events-filter-severity');
  const sinceEl = document.getElementById('events-filter-since');
  const queryEl = document.getElementById('events-filter-q');
  const sysEl = document.getElementById('events-filter-show-system');
  if (typeEl) typeEl.value = eventsPageState.type;
  if (sevEl) sevEl.value = eventsPageState.severity;
  if (sinceEl) sinceEl.value = eventsPageState.range;
  if (queryEl) queryEl.value = eventsPageState.query;
  if (sysEl) sysEl.checked = !eventsPageState.hideSystem;
}

async function reloadEvents({ preservePage = false } = {}) {
  const typeEl = document.getElementById('events-filter-type');
  const sevEl = document.getElementById('events-filter-severity');
  const sinceEl = document.getElementById('events-filter-since');
  const queryEl = document.getElementById('events-filter-q');
  const sysEl = document.getElementById('events-filter-show-system');
  eventsPageState.type = typeEl?.value || '';
  eventsPageState.severity = sevEl?.value || '';
  eventsPageState.range = sinceEl?.value || '24h';
  eventsPageState.query = queryEl?.value.trim() || '';
  // 复选框未勾 → 隐藏 system；勾上 → 显示
  eventsPageState.hideSystem = sysEl ? !sysEl.checked : true;
  if (!preservePage) {
    eventsPageState.page = 1;
    eventsPageState.expandedIds.clear();
  }
  await refreshEventsPage();
}

async function refreshEventsPage() {
  const container = document.getElementById('events-list');
  if (!container) return;
  container.innerHTML = '<div class="cq-skeleton" style="height:240px;"></div>';
  const response = await api.getEvents({
    event_type: eventsPageState.type || undefined,
    severity: eventsPageState.severity || undefined,
    since: resolveSinceParam(eventsPageState.range),
    q: eventsPageState.query || undefined,
    instance_id: eventsPageState.instanceId || undefined,
    // 用户选了 type=system 时复选框应被忽略（用户显式想看系统事件）
    exclude_system: eventsPageState.hideSystem && eventsPageState.type !== 'system' ? true : undefined,
    limit: eventsPageState.limit,
    offset: (eventsPageState.page - 1) * eventsPageState.limit,
  }).catch(() => ({ items: [], total: 0, limit: eventsPageState.limit, offset: 0 }));
  eventsPageState.total = Number(response.total || 0);
  renderEventsResults(response.items || []);
  renderEventsPagination();
}

function toggleEventDetail(id) {
  if (eventsPageState.expandedIds.has(id)) {
    eventsPageState.expandedIds.delete(id);
  } else {
    eventsPageState.expandedIds.add(id);
  }
  refreshEventsPage();
}

function renderEventsResults(items) {
  const container = document.getElementById('events-list');
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="cq-empty-state"><h3>没有匹配的事件</h3><p>换个筛选条件试试。</p></div>';
    return;
  }
  container.innerHTML = `
    <div class="cq-log-feed">
      ${items.map(renderEventCard).join('')}
    </div>
  `;
}

// 把 event.id 转成可作为 DOM id 的形式（"signal:30" → "signal_30"）
function _eventDomId(id) {
  return 'event-' + String(id).replace(/[^a-zA-Z0-9_-]/g, '_');
}

function renderEventCard(item) {
  const id = item.id || '';
  const expanded = eventsPageState.expandedIds.has(id);
  const severity = item.severity || 'info';
  const detail = item.detail && typeof item.detail === 'object' ? item.detail : {};
  const hasDetail = Object.keys(detail).length > 0;
  return `
    <article id="${escapeHtml(_eventDomId(id))}" class="cq-log-card cq-log-card--sev-${escapeHtml(severity)}">
      <header class="cq-log-card__head">
        <div style="display:flex;gap:var(--cq-space-2);align-items:center;flex-wrap:wrap;">
          <span class="cq-log-card__type cq-log-card__type--${escapeHtml(item.type)}">${escapeHtml(getEventTypeLabel(item.type))}</span>
          ${severity !== 'info' ? `<span class="cq-log-card__sev cq-log-card__sev--${escapeHtml(severity)}">${escapeHtml(getEventSeverityLabel(severity))}</span>` : ''}
          ${item.instance_id ? `<button class="cq-log-card__link" type="button" onclick="event.stopPropagation();openInstanceDrawer(${escapeHtml(String(item.instance_id))})">#${escapeHtml(String(item.instance_id))}</button>` : ''}
        </div>
        <time class="cq-log-card__time">${escapeHtml(formatEventDateTime(item.at))}</time>
      </header>
      <p class="cq-log-card__summary">${escapeHtml(item.summary || '--')}</p>
      ${hasDetail ? `
        <button class="cq-log-card__toggle" type="button" onclick="toggleEventDetail('${escapeHtml(id)}')">${expanded ? '收起' : '展开详情'}</button>
        ${expanded ? renderEventDetail(detail) : ''}
      ` : ''}
    </article>
  `;
}

// 点信号 detail 里的"关联订单" chip → 滚到对应 order 卡片。
// 关联订单事件可能不在当前页/被筛选掉,要按 type 分两种处理:
//   1. 已在 DOM 里 → scrollIntoView + 高亮
//   2. 不在 → 提示用户当前筛选/分页排除了它,给个"跳转过去"快捷操作
async function jumpToOrderEvent(orderId) {
  const targetId = _eventDomId('order:' + orderId);
  let el = document.getElementById(targetId);
  if (!el) {
    // 当前列表里没有 — 尝试清类型筛选 + 切到全时间窗 + 翻页找。简单做法:
    // 把类型清成 'order',强制 since='30d',重载后再找一次。
    const typeEl = document.getElementById('events-filter-type');
    const sevEl = document.getElementById('events-filter-severity');
    const sinceEl = document.getElementById('events-filter-since');
    if (typeEl) typeEl.value = 'order';
    if (sevEl) sevEl.value = '';
    if (sinceEl) sinceEl.value = '30d';
    eventsPageState.expandedIds.add('order:' + orderId);  // 自动展开目标
    await reloadEvents();
    el = document.getElementById(targetId);
  }
  if (!el) {
    alert(`未找到订单 #${orderId} 的事件，可能已超出 30 天范围或被删除`);
    return;
  }
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  el.classList.add('cq-log-card--highlight');
  setTimeout(() => el.classList.remove('cq-log-card--highlight'), 2000);
}

const _EVENT_DETAIL_LABELS = {
  symbol: '交易对',
  action: '动作',
  side: '方向',
  status: '状态',
  reason: '原因',
  instance_name: '实例名',
  order_id: '关联订单',
  order_status: '订单状态',
  signal_id: '关联信号',
  entry_price: '信号价',
  fill_price: '成交价',
  avg_fill_price: '成交均价',
  quantity: '数量',
  filled_quantity: '已成交',
  commission: '手续费',
  pnl: '盈亏',
  exchange_order_id: '交易所订单 ID',
  error_message: '错误信息',
  order_type: '订单类型',
  alert_type: '告警类型',
  message: '消息',
  metrics: '指标',
  event: '事件',
  environment: '环境',
  version: '版本',
};

function renderEventDetail(detail) {
  const rows = Object.entries(detail)
    .filter(([, v]) => v !== null && v !== undefined && v !== '')
    .map(([k, v]) => {
      const label = _EVENT_DETAIL_LABELS[k] || k;
      const value = typeof v === 'object' ? JSON.stringify(v) : String(v);
      const isOrderLink = k === 'order_id';
      return `<div class="cq-log-card__kv"><span class="cq-log-card__k">${escapeHtml(label)}</span><span class="cq-log-card__v">${isOrderLink ? `<button type="button" class="cq-log-card__link" onclick="event.stopPropagation();jumpToOrderEvent('${escapeHtml(value)}')">#${escapeHtml(value)} ↗</button>` : escapeHtml(value)}</span></div>`;
    }).join('');
  return rows ? `<div class="cq-log-card__detail">${rows}</div>` : '';
}

function renderEventsPagination() {
  const container = document.getElementById('events-pagination');
  if (!container) return;
  const totalPages = Math.max(1, Math.ceil(eventsPageState.total / eventsPageState.limit));
  container.innerHTML = `
    <div class="cq-event-pagination">
      <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="changeEventsPage(-1)" ${eventsPageState.page <= 1 ? 'disabled' : ''}>上一页</button>
      <span>第 ${eventsPageState.page} / ${totalPages} 页</span>
      <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="changeEventsPage(1)" ${eventsPageState.page >= totalPages ? 'disabled' : ''}>下一页</button>
    </div>
  `;
}

function changeEventsPage(delta) {
  const totalPages = Math.max(1, Math.ceil(eventsPageState.total / eventsPageState.limit));
  eventsPageState.page = Math.min(totalPages, Math.max(1, eventsPageState.page + delta));
  refreshEventsPage();
}
