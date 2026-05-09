const eventsPageState = {
  type: '',
  range: '24h',
  query: '',
  instanceId: '',
  page: 1,
  limit: 20,
  total: 0,
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
  const sinceEl = document.getElementById('events-filter-since');
  const queryEl = document.getElementById('events-filter-q');
  if (typeEl) typeEl.value = eventsPageState.type;
  if (sinceEl) sinceEl.value = eventsPageState.range;
  if (queryEl) queryEl.value = eventsPageState.query;
}

async function reloadEvents({ preservePage = false } = {}) {
  const typeEl = document.getElementById('events-filter-type');
  const sinceEl = document.getElementById('events-filter-since');
  const queryEl = document.getElementById('events-filter-q');
  eventsPageState.type = typeEl?.value || '';
  eventsPageState.range = sinceEl?.value || '24h';
  eventsPageState.query = queryEl?.value.trim() || '';
  if (!preservePage) eventsPageState.page = 1;
  await refreshEventsPage();
}

async function refreshEventsPage() {
  const container = document.getElementById('events-list');
  if (!container) return;
  container.innerHTML = '<div class="cq-skeleton" style="height:240px;"></div>';
  const response = await api.getEvents({
    event_type: eventsPageState.type || undefined,
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

function renderEventsResults(items) {
  const container = document.getElementById('events-list');
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="cq-empty-state"><h3>没有匹配的事件</h3><p>换个筛选条件试试。</p></div>';
    return;
  }
  container.innerHTML = `
    <div class="cq-event-table">
      ${items.map((item) => `
        <button type="button" class="cq-event-table__row" onclick="${item.instance_id ? `openInstanceDrawer(${item.instance_id})` : 'void(0)'}">
          <span>${escapeHtml(formatEventDateTime(item.at))}</span>
          <span>${escapeHtml(item.type)}</span>
          <span>${item.instance_id ? `#${escapeHtml(item.instance_id)}` : '--'}</span>
          <span>${escapeHtml(item.summary || '--')}</span>
        </button>
      `).join('')}
    </div>
  `;
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
