'use strict';

// 用 IIFE 收敛模块边界：内部辅助（refreshEventsPage / renderEventCard 等）不再泄露到 window，
// 只 expose 真正的 public API（inline onclick 与其他模块依赖的部分）。
(function () {
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
    try {
      syncEventsControls();
      await reloadEvents();
    } catch (err) {
      // 入口出错时 toast + 兜底渲染空列表，避免 unhandled rejection 卡 UI
      console.error('[events] loadEventsPage failed:', err);
      if (typeof showToast === 'function') showToast(err?.message || '加载日志页失败', 'error');
      const container = document.getElementById('events-list');
      if (container) container.innerHTML = '<div class="cq-empty-state"><h3>加载失败</h3><p>请刷新重试。</p></div>';
    }
  }

  async function refreshEventsPageIfVisible() {
    if (_currentPage === 'events') {
      try {
        await reloadEvents({ preservePage: true });
      } catch (err) {
        console.error('[events] background refresh failed:', err);
      }
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

  // 展开/折叠纯前端切换 — 不再回头拉接口（旧实现 refreshEventsPage 重渲染列表
   //   导致 skeleton 闪一下 + 浪费一次请求）。state 仍记一份，给 jumpToOrderEvent
   //   预先标记目标卡片用。
  function toggleEventDetail(id) {
    if (eventsPageState.expandedIds.has(id)) {
      eventsPageState.expandedIds.delete(id);
    } else {
      eventsPageState.expandedIds.add(id);
    }
    const card = document.getElementById(_eventDomId(id));
    if (!card) {
      // 目标卡不在 DOM（例如 jumpToOrderEvent 在 reload 前预标记）— 等下一次 render 时由 state 自动展开
      return;
    }
    const wrap = card.querySelector('.cq-log-card__detail-wrap');
    const btn = card.querySelector('.cq-log-card__toggle');
    if (!wrap || !btn) return;
    const willExpand = eventsPageState.expandedIds.has(id);
    wrap.hidden = !willExpand;
    btn.textContent = willExpand ? '收起' : '展开详情';
    btn.setAttribute('aria-expanded', String(willExpand));
  }

  function renderEventsResults(items) {
    const container = document.getElementById('events-list');
    if (!container) return;
    if (!items.length) {
      // 用户能否判断"没有匹配"是因为筛选太严？显示「清空筛选」CTA 一键复位
      container.innerHTML = `<div class="cq-empty-state">
        <h3>没有匹配的事件</h3>
        <p>换个筛选条件试试，或一键清空所有筛选。</p>
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="clearEventsFilters()">清空筛选</button>
      </div>`;
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
    // detail 永远渲染（即使 collapsed），用 hidden 控制显隐 — toggle 无需 re-fetch
    return `
      <article id="${escapeHtml(_eventDomId(id))}" class="cq-log-card cq-log-card--sev-${escapeHtml(severity)}">
        <header class="cq-log-card__head">
          <div style="display:flex;gap:var(--cq-space-2);align-items:center;flex-wrap:wrap;">
            <span class="cq-log-card__type cq-log-card__type--${escapeHtml(item.type)}">${escapeHtml(getEventTypeLabel(item.type))}</span>
            ${severity !== 'info' ? `<span class="cq-log-card__sev cq-log-card__sev--${escapeHtml(severity)}">${escapeHtml(getEventSeverityLabel(severity))}</span>` : ''}
            ${item.instance_id ? `<button class="cq-log-card__link" type="button" data-instance-id="${escapeHtml(String(item.instance_id))}" onclick="event.stopPropagation();openInstanceDrawerFromBtn(this)">#${escapeHtml(String(item.instance_id))}</button>` : ''}
          </div>
          <time class="cq-log-card__time">${escapeHtml(formatEventDateTime(item.at))}</time>
        </header>
        <p class="cq-log-card__summary">${escapeHtml(item.summary || '--')}</p>
        ${hasDetail ? `
          <button class="cq-log-card__toggle" type="button" data-event-id="${escapeHtml(id)}" aria-expanded="${expanded ? 'true' : 'false'}" onclick="toggleEventDetailFromBtn(this)">${expanded ? '收起' : '展开详情'}</button>
          <div class="cq-log-card__detail-wrap"${expanded ? '' : ' hidden'}>${renderEventDetail(detail)}</div>
        ` : ''}
      </article>
    `;
  }

  // 点信号 detail 里的"关联订单" chip → 滚到对应 order 卡片。
  // 关联订单事件可能不在当前页/被筛选掉,要按 type 分两种处理:
  //   1. 已在 DOM 里 → scrollIntoView + 高亮
  //   2. 不在 → 强切筛选到 type=order + 30d 后重载，再找一次。toast 告诉用户
  async function jumpToOrderEvent(orderId) {
    try {
      const targetId = _eventDomId('order:' + orderId);
      let el = document.getElementById(targetId);
      if (!el) {
        // 当前列表里没有 — 强切类型 + 时间窗。告知用户避免"筛选条件被神秘改了"
        const typeEl = document.getElementById('events-filter-type');
        const sevEl = document.getElementById('events-filter-severity');
        const sinceEl = document.getElementById('events-filter-since');
        if (typeEl) typeEl.value = 'order';
        if (sevEl) sevEl.value = '';
        if (sinceEl) sinceEl.value = '30d';
        eventsPageState.expandedIds.add('order:' + orderId);  // 自动展开目标
        if (typeof showToast === 'function') {
          showToast('已切换到「订单 · 最近 30 天」筛选以定位该订单', 'info');
        }
        await reloadEvents();
        el = document.getElementById(targetId);
      }
      if (!el) {
        if (typeof showToast === 'function') {
          showToast(`未找到订单 #${orderId} 的事件，可能已超出 30 天范围或被删除`, 'warn');
        }
        return;
      }
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
      el.classList.add('cq-log-card--highlight');
      setTimeout(() => el.classList.remove('cq-log-card--highlight'), 2000);
    } catch (err) {
      console.error('[events] jumpToOrderEvent failed:', err);
      if (typeof showToast === 'function') showToast(err?.message || '跳转订单失败', 'error');
    }
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
        const isObj = v !== null && typeof v === 'object';
        // 嵌套对象（如 metrics）格式化两空格缩进，单值直接 toString。
        const value = isObj ? JSON.stringify(v, null, 2) : String(v);
        const isOrderLink = k === 'order_id';
        const valueHtml = isObj
          ? `<pre class="cq-log-card__json">${escapeHtml(value)}</pre>`
          : isOrderLink
            ? `<button type="button" class="cq-log-card__link" data-order-id="${escapeHtml(value)}" onclick="event.stopPropagation();jumpToOrderEventFromBtn(this)">#${escapeHtml(value)} ↗</button>`
            : escapeHtml(value);
        return `<div class="cq-log-card__kv"><span class="cq-log-card__k">${escapeHtml(label)}</span><span class="cq-log-card__v">${valueHtml}</span></div>`;
      }).join('');
    return rows ? `<div class="cq-log-card__detail">${rows}</div>` : '';
  }

  function renderEventsPagination() {
    const container = document.getElementById('events-pagination');
    if (!container) return;
    const totalPages = Math.max(1, Math.ceil(eventsPageState.total / eventsPageState.limit));
    // 单页就别画分页 — 0 数据时显示「第 1/1 页」纯噪音
    if (totalPages <= 1) {
      container.innerHTML = '';
      return;
    }
    container.innerHTML = `
      <div class="cq-event-pagination">
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="changeEventsPage(-1)" ${eventsPageState.page <= 1 ? 'disabled' : ''}>上一页</button>
        <span>第 ${eventsPageState.page} / ${totalPages} 页（共 ${eventsPageState.total} 条）</span>
        <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="changeEventsPage(1)" ${eventsPageState.page >= totalPages ? 'disabled' : ''}>下一页</button>
      </div>
    `;
  }

  function changeEventsPage(delta) {
    const totalPages = Math.max(1, Math.ceil(eventsPageState.total / eventsPageState.limit));
    eventsPageState.page = Math.min(totalPages, Math.max(1, eventsPageState.page + delta));
    refreshEventsPage().catch((err) => console.error('[events] pagination refresh failed:', err));
  }

  // 清空所有筛选回到默认（type/severity 清空、since=24h、query 清空、不显示 system）
  function clearEventsFilters() {
    const typeEl = document.getElementById('events-filter-type');
    const sevEl = document.getElementById('events-filter-severity');
    const sinceEl = document.getElementById('events-filter-since');
    const queryEl = document.getElementById('events-filter-q');
    const sysEl = document.getElementById('events-filter-show-system');
    if (typeEl) typeEl.value = '';
    if (sevEl) sevEl.value = '';
    if (sinceEl) sinceEl.value = '24h';
    if (queryEl) queryEl.value = '';
    if (sysEl) sysEl.checked = false;
    reloadEvents().catch((err) => console.error('[events] clearEventsFilters reload failed:', err));
  }

  // 走 data-* 而非 inline 字符串参数:onclick 是 HTML attribute,浏览器解码一次
  // 再交给 JS 解析,直接把 escapeHtml 后的 ' (&#39;) 还原成 ',撑破 JS 字符串字面量
  // (escapeHtml 也挡不住 `)` `;` 的 JS breakout)。data-* 走 dataset 读取,无 JS 解码。
  function toggleEventDetailFromBtn(btn) {
    toggleEventDetail(btn.dataset.eventId || '');
  }
  function jumpToOrderEventFromBtn(btn) {
    jumpToOrderEvent(btn.dataset.orderId || '');
  }
  function openInstanceDrawerFromBtn(btn) {
    const id = Number(btn.dataset.instanceId);
    if (Number.isFinite(id) && id > 0) openInstanceDrawer(id);
  }

  // ───── public API（inline onclick / 其他模块依赖）─────
  // refreshEventsPage / renderEventCard / renderEventDetail / _eventDomId / _EVENT_DETAIL_LABELS
  // syncEventsControls / renderEventsResults / renderEventsPagination 都不外露
  window.presetEventsFilters = presetEventsFilters;
  window.loadEventsPage = loadEventsPage;
  window.refreshEventsPageIfVisible = refreshEventsPageIfVisible;
  window.reloadEvents = reloadEvents;
  window.toggleEventDetail = toggleEventDetail;
  window.jumpToOrderEvent = jumpToOrderEvent;
  window.changeEventsPage = changeEventsPage;
  window.clearEventsFilters = clearEventsFilters;
  window.toggleEventDetailFromBtn = toggleEventDetailFromBtn;
  window.jumpToOrderEventFromBtn = jumpToOrderEventFromBtn;
  window.openInstanceDrawerFromBtn = openInstanceDrawerFromBtn;
})();
