'use strict';

// 单实例日志抽屉 — 点策略卡片「日志」打开，只展示该 instance 的日志（含类型/时间筛选 + 分页）。
// 与全局「日志」页解耦，不污染该页 filter 状态。
//
// IIFE 收敛：refreshInstanceLogs / renderLogCard / renderInstanceLogsResults /
// renderInstanceLogsPagination / instanceLogsState 都在闭包内，
// 只 expose openInstanceLogsDrawer / openInstanceLogsDrawerFromBtn /
// closeInstanceLogsDrawer / reloadInstanceLogs / changeInstanceLogsPage。
(function () {
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
    // 互斥：打开前关其他抽屉
    if (typeof closeSettingsDrawer === 'function') closeSettingsDrawer();
    if (typeof closeInstanceDrawer === 'function') closeInstanceDrawer();
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

    try {
      await refreshInstanceLogs();
    } catch (err) {
      // drawer 已经打开，refresh 出错时降级到错误占位，不要让 unhandled rejection 卡住后续操作
      console.error('[instance-logs] initial refresh failed:', err);
      if (typeof showToast === 'function') showToast(err?.message || '加载日志失败', 'error');
      const container = document.getElementById('instance-logs-list');
      if (container) container.innerHTML = '<div class="cq-empty-state cq-empty-state--compact"><p>加载失败，请重试</p></div>';
    }
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
    try {
      await refreshInstanceLogs();
    } catch (err) {
      console.error('[instance-logs] reload failed:', err);
      if (typeof showToast === 'function') showToast(err?.message || '刷新日志失败', 'error');
    }
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
      <div class="cq-log-feed">
        ${items.map(renderLogCard).join('')}
      </div>
    `;
  }

  const _LOG_DETAIL_LABELS = {
    symbol: '交易对',
    action: '动作',
    side: '方向',
    status: '状态',
    reason: '原因',
    instance_name: '实例',
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

  function renderLogCard(item) {
    const detail = item.detail && typeof item.detail === 'object' ? item.detail : {};
    const severity = item.severity || 'info';
    const detailRows = Object.entries(detail)
      .filter(([, v]) => v !== null && v !== undefined && v !== '')
      .map(([k, v]) => {
        const label = _LOG_DETAIL_LABELS[k] || k;
        const isObj = v !== null && typeof v === 'object';
        // 嵌套对象（如 metrics）pretty-print 多行展示，避免大对象挤成一坨
        const value = isObj ? JSON.stringify(v, null, 2) : String(v);
        const valueHtml = isObj
          ? `<pre class="cq-log-card__json">${escapeHtml(value)}</pre>`
          : escapeHtml(value);
        return `<div class="cq-log-card__kv"><span class="cq-log-card__k">${escapeHtml(label)}</span><span class="cq-log-card__v">${valueHtml}</span></div>`;
      }).join('');
    const hasDetail = detailRows.length > 0;

    return `
      <article class="cq-log-card cq-log-card--sev-${escapeHtml(severity)}">
        <header class="cq-log-card__head">
          <div style="display:flex;gap:var(--cq-space-2);align-items:center;flex-wrap:wrap;">
            <span class="cq-log-card__type cq-log-card__type--${escapeHtml(item.type)}">${escapeHtml(getEventTypeLabel(item.type))}</span>
            ${severity !== 'info' ? `<span class="cq-log-card__sev cq-log-card__sev--${escapeHtml(severity)}">${escapeHtml(getEventSeverityLabel(severity))}</span>` : ''}
          </div>
          <time datetime="${escapeHtml(String(item.at || ''))}" class="cq-log-card__time" title="${escapeHtml(String(item.at || ''))}">${escapeHtml(formatEventDateTime(item.at))}</time>
        </header>
        <p class="cq-log-card__summary">${escapeHtml(item.summary || '--')}</p>
        ${hasDetail ? `
          <button class="cq-log-card__toggle" type="button" aria-expanded="false" onclick="_instanceLogsToggleDetail(this)">展开详情</button>
          <div class="cq-log-card__detail-wrap" hidden>${detailRows}</div>
        ` : ''}
      </article>
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
    refreshInstanceLogs().catch((err) => console.error('[instance-logs] pagination refresh failed:', err));
  }

  // 单实例日志卡 detail 展开/折叠 — 跟 events.js 一致体验,detail 默认折叠,
  // 否则 20 张卡 metrics 大对象同时展开屏幕被刷爆
  function _toggleDetail(btn) {
    const card = btn.closest('article');
    if (!card) return;
    const wrap = card.querySelector('.cq-log-card__detail-wrap');
    if (!wrap) return;
    const willExpand = wrap.hidden;
    wrap.hidden = !willExpand;
    btn.textContent = willExpand ? '收起' : '展开详情';
    btn.setAttribute('aria-expanded', String(willExpand));
  }

  // ───── public API ─────
  window.openInstanceLogsDrawer = openInstanceLogsDrawer;
  window.openInstanceLogsDrawerFromBtn = openInstanceLogsDrawerFromBtn;
  window.closeInstanceLogsDrawer = closeInstanceLogsDrawer;
  window.reloadInstanceLogs = reloadInstanceLogs;
  window.changeInstanceLogsPage = changeInstanceLogsPage;
  window._instanceLogsToggleDetail = _toggleDetail;
})();
