// 单实例日志抽屉 — 点策略卡片「日志」打开，只展示该 instance 的事件流（含类型/时间筛选 + 分页）。
// 与 events 全局事件页解耦，不污染该页 filter 状态。

const instanceLogsState = {
  instanceId: null,
  instanceName: '',
  type: '',
  range: '24h',
  page: 1,
  limit: 20,
  total: 0,
};

// 卡片 onclick proxy：用 data-* 而非 inline 字符串参数，避免 escapeHtml 后 ' (&#39;) 被
// 浏览器 attribute 解码器还原成 ' 撑破 JS 字符串字面量（详见 paper.js bug #1）
function openInstanceLogsDrawerFromBtn(btn) {
  return openInstanceLogsDrawer(Number(btn.dataset.instanceId), btn.dataset.instanceName || '');
}

async function openInstanceLogsDrawer(instanceId, instanceName) {
  const drawer = document.getElementById('instance-logs-drawer');
  if (!drawer) return;
  instanceLogsState.instanceId = instanceId;
  instanceLogsState.instanceName = instanceName || `实例 #${instanceId}`;
  instanceLogsState.type = '';
  instanceLogsState.range = '24h';
  instanceLogsState.page = 1;

  document.getElementById('instance-logs-drawer-title').textContent = `${instanceLogsState.instanceName} · 日志`;
  const typeEl = document.getElementById('instance-logs-filter-type');
  const sinceEl = document.getElementById('instance-logs-filter-since');
  if (typeEl) typeEl.value = '';
  if (sinceEl) sinceEl.value = '24h';

  drawer.hidden = false;
  document.body.classList.add('is-drawer-open');

  await refreshInstanceLogs();
}

function closeInstanceLogsDrawer() {
  const drawer = document.getElementById('instance-logs-drawer');
  if (!drawer) return;
  drawer.hidden = true;
  document.body.classList.remove('is-drawer-open');
  instanceLogsState.instanceId = null;
}

async function reloadInstanceLogs() {
  instanceLogsState.type = document.getElementById('instance-logs-filter-type')?.value || '';
  instanceLogsState.range = document.getElementById('instance-logs-filter-since')?.value || '24h';
  instanceLogsState.page = 1;
  await refreshInstanceLogs();
}

async function refreshInstanceLogs() {
  const container = document.getElementById('instance-logs-list');
  if (!container || !instanceLogsState.instanceId) return;
  container.innerHTML = '<div class="cq-skeleton" style="height:240px;"></div>';

  const response = await api.getEvents({
    instance_id: instanceLogsState.instanceId,
    event_type: instanceLogsState.type || undefined,
    since: resolveSinceParam(instanceLogsState.range),
    limit: instanceLogsState.limit,
    offset: (instanceLogsState.page - 1) * instanceLogsState.limit,
  }).catch(() => ({ items: [], total: 0 }));

  instanceLogsState.total = Number(response.total || 0);
  renderInstanceLogsResults(response.items || []);
  renderInstanceLogsPagination();
}

function renderInstanceLogsResults(items) {
  const container = document.getElementById('instance-logs-list');
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="cq-empty-state cq-empty-state--compact"><p>该时间窗内没有匹配的事件</p></div>';
    return;
  }
  container.innerHTML = `
    <div class="cq-event-table">
      ${items.map((item) => `
        <div class="cq-event-table__row" style="cursor:default;grid-template-columns:auto auto 1fr;">
          <span>${escapeHtml(formatEventDateTime(item.at))}</span>
          <span>${escapeHtml(getEventTypeLabel(item.type))}</span>
          <span>${escapeHtml(item.summary || '--')}</span>
        </div>
      `).join('')}
    </div>
  `;
}

function renderInstanceLogsPagination() {
  const container = document.getElementById('instance-logs-pagination');
  if (!container) return;
  const totalPages = Math.max(1, Math.ceil(instanceLogsState.total / instanceLogsState.limit));
  if (totalPages <= 1) {
    container.innerHTML = '';
    return;
  }
  container.innerHTML = `
    <div class="cq-event-pagination">
      <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="changeInstanceLogsPage(-1)" ${instanceLogsState.page <= 1 ? 'disabled' : ''}>上一页</button>
      <span>第 ${instanceLogsState.page} / ${totalPages} 页</span>
      <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="changeInstanceLogsPage(1)" ${instanceLogsState.page >= totalPages ? 'disabled' : ''}>下一页</button>
    </div>
  `;
}

function changeInstanceLogsPage(delta) {
  const totalPages = Math.max(1, Math.ceil(instanceLogsState.total / instanceLogsState.limit));
  instanceLogsState.page = Math.min(totalPages, Math.max(1, instanceLogsState.page + delta));
  refreshInstanceLogs();
}
