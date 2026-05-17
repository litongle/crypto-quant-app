let dashboardEquityDays = 30;
let dashboardRefreshTimer = null;
let dashboardState = {
  instances: [],
  activity: [],
  riskEvents: [],
  runnerStatus: null,
  equity: null,
};

async function loadDashboard() {
  stopDashboardPolling();
  await refreshDashboard();
  dashboardRefreshTimer = setInterval(() => {
    refreshDashboard({ silent: true }).catch(() => {});
  }, 5000);
}

function stopDashboardPolling() {
  if (dashboardRefreshTimer) {
    clearInterval(dashboardRefreshTimer);
    dashboardRefreshTimer = null;
  }
}

// 登出后停止 polling — 避免 token 过期后 polling 持续打 401/400 死循环
window.addEventListener('cq:logged-out', stopDashboardPolling);

async function refreshDashboard({ silent = false } = {}) {
  // 实时活动剔除 system 启停（这类事件下沉到日志页查）。走后端 exclude_system 比
  // 前端 filter 更准确(total/分页都对得上)。
  const [
    instances,
    activityResp,
    riskResp,
    equity,
    runnerStatus,
  ] = await Promise.all([
    api.getStrategyInstances('all').catch(() => []),
    api.getEvents({ limit: 50, exclude_system: true }).catch(() => ({ items: [] })),
    api.getEvents({ event_type: 'auto_pause', since: resolveSinceParam('24h'), limit: 50 }).catch(() => ({ items: [] })),
    api.getEquityCurve(dashboardEquityDays).catch(() => null),
    api.getRunnerStatus().catch(() => null),
  ]);

  dashboardState = {
    instances: Array.isArray(instances) ? instances : [],
    activity: Array.isArray(activityResp?.items) ? activityResp.items : [],
    riskEvents: Array.isArray(riskResp?.items) ? riskResp.items : [],
    runnerStatus,
    equity,
  };

  renderInstanceList(dashboardState.instances);
  renderActivityStream(dashboardState.activity);
  renderRiskEvents(dashboardState.riskEvents);
  renderSystemStatus(dashboardState.runnerStatus);

  if (equity?.points?.length) {
    renderEquityCurveChart(equity, 'dashboard-equity-chart');
  } else {
    disposeEquityChart('dashboard-equity-chart');
    const chartEl = document.getElementById('dashboard-equity-chart');
    if (chartEl) chartEl.innerHTML = '<div class="cq-empty-inline">暂无权益曲线数据</div>';
  }

  if (!silent && typeof window.refreshEventsPageIfVisible === 'function') {
    window.refreshEventsPageIfVisible();
  }
}

async function changeEquityDays(days) {
  dashboardEquityDays = days;
  document.querySelectorAll('.cq-day-pill').forEach((button) => {
    button.classList.toggle('is-active', String(button.dataset.days) === String(days));
  });
  await refreshDashboard({ silent: true });
}

function renderInstanceList(instances) {
  const container = document.getElementById('dashboard-instance-list');
  if (!container) return;
  if (!instances.length) {
    container.innerHTML = '<div class="cq-empty-state cq-empty-state--compact"><h3>还没有策略实例</h3><p>去策略页创建并启动一个实例，这里就会亮起来。</p></div>';
    return;
  }

  container.innerHTML = `
    <div class="cq-instance-table">
      ${instances.map((item) => {
        const canStop = item.status === 'running' || item.status === 'paused';
        const stopLabel = item.status === 'stopped' ? '恢复' : item.status === 'paused' ? '恢复' : '暂停';
        return `
          <button class="cq-instance-row" type="button" onclick="openInstanceDrawer(${item.id})">
            <span class="cq-instance-row__status cq-instance-row__status--${escapeHtml(item.status)}"></span>
            <span class="cq-instance-row__main">
              <span class="cq-instance-row__title">${escapeHtml(item.name || item.templateName || `实例 #${item.id}`)}</span>
              <span class="cq-instance-row__meta">${escapeHtml(item.symbol || '--')} · ${escapeHtml(getInstanceStatusLabel(item.status))}</span>
            </span>
            <span class="cq-instance-row__metric">${formatSignedPnl(item.totalPnl)}</span>
            <span class="cq-instance-row__metric">${item.runtimeActive ? '在线' : '闲置'}</span>
            <span class="cq-instance-row__action">${canStop ? stopLabel : '查看'}</span>
          </button>
        `;
      }).join('')}
    </div>
  `;
}

function renderActivityStream(items) {
  const container = document.getElementById('dashboard-activity-stream');
  if (!container) return;
  container.innerHTML = renderEventListMarkup(items, '最近没有活动');
}

function renderRiskEvents(items) {
  const container = document.getElementById('dashboard-risk-events');
  if (!container) return;
  container.innerHTML = renderEventListMarkup(items, '24 小时内没有风险事件');
}

function renderSystemStatus(status) {
  const container = document.getElementById('dashboard-system-status');
  if (!container) return;
  const runner = status?.strategy_runner;
  const exchanges = Array.isArray(status?.exchanges) ? status.exchanges : [];
  const runnerLine = runner
    ? `<div class="cq-status-list__item"><span>执行器</span><span>${runner.alive_count}/${runner.task_count} 就绪</span></div>`
    : '<div class="cq-status-list__item"><span>执行器</span><span>--</span></div>';
  container.innerHTML = `
    <div class="cq-status-list">
      ${runnerLine}
      ${exchanges.map((item) => `
        <div class="cq-status-list__item">
          <span>${escapeHtml(getExchangeLabel(item.name))}</span>
          <span>${item.ws_connected ? `${item.rest_latency_ms ?? '--'}ms` : '离线'}</span>
        </div>
      `).join('')}
    </div>
  `;
}

function renderEventListMarkup(items, emptyText) {
  if (!items?.length) {
    return `<div class="cq-empty-state cq-empty-state--compact"><p>${escapeHtml(emptyText)}</p></div>`;
  }
  return `
    <div class="cq-event-list">
      ${items.slice(0, 50).map((item) => {
        const sev = item.severity || 'info';
        const typeLabel = getEventTypeLabel(item.type);
        return `
          <button class="cq-event-list__item cq-event-list__item--sev-${escapeHtml(sev)}" type="button" onclick="${item.instance_id ? `openInstanceDrawer(${item.instance_id})` : 'void(0)'}">
            <span class="cq-event-list__time">${escapeHtml(formatEventTime(item.at))}</span>
            <span class="cq-event-list__type cq-log-card__type--${escapeHtml(item.type)}">${escapeHtml(typeLabel)}</span>
            <span class="cq-event-list__summary">${escapeHtml(item.summary || '--')}</span>
          </button>
        `;
      }).join('')}
    </div>
  `;
}

function formatEventTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit' });
}

function formatSignedPnl(value) {
  const num = Number(value || 0);
  const sign = num >= 0 ? '+' : '';
  return `${sign}${formatNum(num)}U`;
}

function disposeEquityChart(containerId = 'dashboard-equity-chart') {
  window._equityCharts = window._equityCharts || {};
  const current = window._equityCharts[containerId];
  if (!current) return;
  try { current.ro?.disconnect(); } catch {}
  try { current.chart?.remove(); } catch {}
  delete window._equityCharts[containerId];
}

function renderEquityCurveChart(equity, containerId = 'dashboard-equity-chart') {
  const container = document.getElementById(containerId);
  if (!container || !equity?.points || typeof LightweightCharts === 'undefined') return;

  const points = [];
  for (const point of equity.points) {
    const time = parseEquityTime(point.date);
    if (time == null) continue;
    points.push({ time, value: Number(point.equity) });
  }
  points.sort((a, b) => a.time - b.time);
  if (!points.length) return;

  disposeEquityChart(containerId);
  container.innerHTML = '';

  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const primary = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1';
  const chart = LightweightCharts.createChart(container, {
    width: container.clientWidth,
    height: container.clientHeight,
    layout: {
      background: { type: 'solid', color: 'transparent' },
      textColor: isDark ? '#8B949E' : '#475569',
      fontFamily: "'Geist', 'JetBrains Mono', sans-serif",
      fontSize: 11,
    },
    grid: {
      vertLines: { color: isDark ? 'rgba(139,148,158,0.10)' : 'rgba(15,23,42,0.05)' },
      horzLines: { color: isDark ? 'rgba(139,148,158,0.10)' : 'rgba(15,23,42,0.05)' },
    },
    rightPriceScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
    },
    timeScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
    },
    handleScroll: false,
    handleScale: false,
  });
  const series = chart.addAreaSeries({
    lineColor: primary,
    lineWidth: 2,
    topColor: isDark ? 'rgba(99,102,241,0.28)' : 'rgba(79,70,229,0.18)',
    bottomColor: 'rgba(99,102,241,0)',
  });
  series.setData(points);
  chart.timeScale().fitContent();

  const ro = new ResizeObserver((entries) => {
    for (const entry of entries) {
      chart.applyOptions({
        width: Math.floor(entry.contentRect.width),
        height: Math.floor(entry.contentRect.height),
      });
    }
  });
  ro.observe(container);
  window._equityCharts = window._equityCharts || {};
  window._equityCharts[containerId] = { chart, ro, points };
}

function parseEquityTime(raw) {
  if (raw == null) return null;
  if (typeof raw === 'number') return raw > 1e11 ? Math.floor(raw / 1000) : Math.floor(raw);
  const parsed = Date.parse(String(raw));
  return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000);
}

window.addEventListener('cq:theme-change', () => {
  const chart = window._equityCharts?.['dashboard-equity-chart'];
  if (chart?.points?.length && dashboardState.equity) {
    renderEquityCurveChart(dashboardState.equity, 'dashboard-equity-chart');
  }
});

function formatNum(n) {
  if (n == null || Number.isNaN(Number(n))) return '--';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}
