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
  if (typeEl) typeEl.value = eventsPageState.type;
  if (sevEl) sevEl.value = eventsPageState.severity;
  if (sinceEl) sinceEl.value = eventsPageState.range;
  if (queryEl) queryEl.value = eventsPageState.query;
}

async function reloadEvents({ preservePage = false } = {}) {
  const typeEl = document.getElementById('events-filter-type');
  const sevEl = document.getElementById('events-filter-severity');
  const sinceEl = document.getElementById('events-filter-since');
  const queryEl = document.getElementById('events-filter-q');
  eventsPageState.type = typeEl?.value || '';
  eventsPageState.severity = sevEl?.value || '';
  eventsPageState.range = sinceEl?.value || '24h';
  eventsPageState.query = queryEl?.value.trim() || '';
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

function renderEventCard(item) {
  const id = item.id || '';
  const expanded = eventsPageState.expandedIds.has(id);
  const severity = item.severity || 'info';
  const detail = item.detail && typeof item.detail === 'object' ? item.detail : {};
  const hasDetail = Object.keys(detail).length > 0;
  return `
    <article class="cq-log-card cq-log-card--sev-${escapeHtml(severity)}">
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
  slippage_pct: '滑点(%)',
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
      return `<div class="cq-log-card__kv"><span class="cq-log-card__k">${escapeHtml(label)}</span><span class="cq-log-card__v">${isOrderLink ? `<a href="#" onclick="event.preventDefault();reloadEvents()">#${escapeHtml(value)}</a>` : escapeHtml(value)}</span></div>`;
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
