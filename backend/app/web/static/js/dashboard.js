'use strict';

let dashboardEquityDays = 30;
let dashboardFastTimer = null;
let dashboardSlowTimer = null;
let dashboardFastFailCount = 0;  // 连续失败计数(指数退避用)
let dashboardSlowFailCount = 0;
let dashboardState = {
  instances: [],
  activity: [],
  riskEvents: [],
  runnerStatus: null,
  equity: null,
};

// 高频 5s：策略实例 / 实时活动 / 执行器健康（业务上需要近实时）
// 低频 30s：权益曲线 30 天全量 / 24h 风险事件（变化慢，5s 拉是浪费）
const DASHBOARD_FAST_MS = 5000;
const DASHBOARD_SLOW_MS = 30000;
const POLL_BACKOFF_MAX = 8;  // 退避封顶 8 倍 (5s→40s / 30s→240s),挂久了别再傻打

async function loadDashboard() {
  stopDashboardPolling();
  // 重置失败计数,避免上次的退避状态延续到本次
  dashboardFastFailCount = 0;
  dashboardSlowFailCount = 0;
  await Promise.all([refreshDashboardFast(), refreshDashboardSlow()]);
  _scheduleFastPolling();
  _scheduleSlowPolling();
}

// setTimeout 链而不是 setInterval:确保前一轮 finally 后才启下一轮,
// 网关慢/挂时不会重叠多个 polling 形成错误风暴
function _scheduleFastPolling() {
  const backoff = Math.min(1 << dashboardFastFailCount, POLL_BACKOFF_MAX);
  dashboardFastTimer = setTimeout(() => {
    refreshDashboardFast({ silent: true })
      .then(() => { dashboardFastFailCount = 0; })
      .catch(() => { dashboardFastFailCount = Math.min(dashboardFastFailCount + 1, 3); })
      .finally(() => {
        if (dashboardFastTimer !== null) _scheduleFastPolling();
      });
  }, DASHBOARD_FAST_MS * backoff);
}

function _scheduleSlowPolling() {
  const backoff = Math.min(1 << dashboardSlowFailCount, POLL_BACKOFF_MAX);
  dashboardSlowTimer = setTimeout(() => {
    refreshDashboardSlow({ silent: true })
      .then(() => { dashboardSlowFailCount = 0; })
      .catch(() => { dashboardSlowFailCount = Math.min(dashboardSlowFailCount + 1, 3); })
      .finally(() => {
        if (dashboardSlowTimer !== null) _scheduleSlowPolling();
      });
  }, DASHBOARD_SLOW_MS * backoff);
}

function stopDashboardPolling() {
  if (dashboardFastTimer) {
    clearTimeout(dashboardFastTimer);
    dashboardFastTimer = null;
  }
  if (dashboardSlowTimer) {
    clearTimeout(dashboardSlowTimer);
    dashboardSlowTimer = null;
  }
}

// 登出后停止 polling — 避免 token 过期后 polling 持续打 401/400 死循环
window.addEventListener('cq:logged-out', stopDashboardPolling);

async function refreshDashboardFast({ silent = false } = {}) {
  // 实时活动剔除 system 启停（这类事件下沉到日志页查）。走后端 exclude_system 比
  // 前端 filter 更准确(total/分页都对得上)。
  // hasFailure 标记 — 任一接口失败让外层 _scheduleFastPolling 走指数退避,
  // 各接口仍 .catch 兜底返默认值,保证 render 永远跑(避免"加载中..."卡死)
  let hasFailure = false;
  const fail = (defaultVal) => () => { hasFailure = true; return defaultVal; };
  const [instances, activityResp, runnerStatus] = await Promise.all([
    api.getStrategyInstances('all').catch(fail([])),
    api.getEvents({ limit: 50, exclude_system: true }).catch(fail({ items: [] })),
    api.getRunnerStatus().catch(fail(null)),
  ]);

  dashboardState.instances = Array.isArray(instances) ? instances : [];
  dashboardState.activity = Array.isArray(activityResp?.items) ? activityResp.items : [];
  dashboardState.runnerStatus = runnerStatus;

  renderInstanceList(dashboardState.instances);
  renderActivityStream(dashboardState.activity);
  renderSystemStatus(dashboardState.runnerStatus);

  if (!silent && typeof window.refreshEventsPageIfVisible === 'function') {
    window.refreshEventsPageIfVisible();
  }
  if (hasFailure) throw new Error('partial polling failure');
}

async function refreshDashboardSlow({ silent = false } = {}) {
  let hasFailure = false;
  const fail = (defaultVal) => () => { hasFailure = true; return defaultVal; };
  const [riskResp, equity] = await Promise.all([
    api.getEvents({ event_type: 'auto_pause', since: resolveSinceParam('24h'), limit: 50 }).catch(fail({ items: [] })),
    api.getEquityCurve(dashboardEquityDays).catch(fail(null)),
  ]);

  dashboardState.riskEvents = Array.isArray(riskResp?.items) ? riskResp.items : [];
  dashboardState.equity = equity;

  renderRiskEvents(dashboardState.riskEvents);
  _renderEquityChart(equity);
  if (hasFailure) throw new Error('partial polling failure');
}

// equity 曲线渲染抽出 — refreshDashboardSlow 和 changeEquityDays 共用,
// 后者切日期时只拉 equity 不再连带 events（旧实现注释自己说"没必要
// 全量"却仍调 refreshDashboardSlow 拉两个 API）
function _renderEquityChart(equity) {
  const chartEl = document.getElementById('dashboard-equity-chart');
  if (equity?.points?.length) {
    renderEquityCurveChart(equity, 'dashboard-equity-chart');
  } else if (equity === null) {
    // API 失败(常见 502/网络抖) — 区分"无数据"与"拉失败",前者真实无数据,
    // 后者下一个 30s polling 周期会自动重试,提示更明确避免误以为坏了
    disposeEquityChart('dashboard-equity-chart');
    if (chartEl) chartEl.innerHTML = '<div class="cq-empty-inline">加载失败,30 秒后自动重试</div>';
  } else {
    disposeEquityChart('dashboard-equity-chart');
    if (chartEl) chartEl.innerHTML = '<div class="cq-empty-inline">暂无权益曲线数据</div>';
  }
}

async function changeEquityDays(days) {
  dashboardEquityDays = days;
  document.querySelectorAll('.cq-day-pill').forEach((button) => {
    button.classList.toggle('is-active', String(button.dataset.days) === String(days));
  });
  // 只重拉 equity，不连带 events — 切日期不该刷新风险事件列表
  const chartEl = document.getElementById('dashboard-equity-chart');
  if (chartEl) chartEl.innerHTML = '<div class="cq-skeleton" style="height:100%;"></div>';
  const equity = await api.getEquityCurve(dashboardEquityDays).catch(() => null);
  dashboardState.equity = equity;
  _renderEquityChart(equity);
}

function renderInstanceList(instances) {
  const container = document.getElementById('dashboard-instance-list');
  if (!container) return;
  if (!instances.length) {
    // 空状态加 CTA button — 之前只文字「去策略页创建...」用户得自己去找侧栏入口
    container.innerHTML = `<div class="cq-empty-state cq-empty-state--compact">
      <h3>还没有策略实例</h3>
      <p>去策略页创建并启动一个实例，这里就会亮起来。</p>
      <button class="cq-btn cq-btn--primary cq-btn--sm" onclick="navigate('strategy')">去策略中心</button>
    </div>`;
    return;
  }

  container.innerHTML = `
    <div class="cq-instance-table">
      ${instances.map((item) => {
        // 全行点击 → 打开 drawer（drawer 内才有真正的暂停/停止按钮）。
        //   旧实现在最右侧画「暂停 / 恢复」label 像按钮，但点了只能开抽屉，
        //   误导用户以为快捷操作。统一文案为「查看 →」消除歧义。
        const pnlNum = Number(item.totalPnl || 0);
        const pnlColor = pnlNum === 0
          ? 'var(--cq-text-secondary)'
          : pnlNum > 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)';
        // zombie 检测：status=running 但 runtimeActive=false（task 异常退出 /
        // 等系统资源），dot 仍是绿色 + 「运行中」label，但 metric 显「闲置」—
        // 三处自相矛盾。zombie 时整体偏红：metric 显「⚠ 执行器异常」红色
        const isRunning = String(item.status || '').toLowerCase() === 'running';
        const isZombie = isRunning && item.runtimeActive === false;
        let runtimeMetric;
        if (isZombie) {
          runtimeMetric = '<span style="color:var(--cq-color-loss);">⚠ 执行器异常</span>';
        } else if (item.runtimeActive) {
          runtimeMetric = '在线';
        } else {
          runtimeMetric = '闲置';
        }
        return `
          <button class="cq-instance-row" type="button" onclick="openInstanceDrawer(${item.id})" aria-label="查看实例 ${escapeHtml(item.name || `#${item.id}`)}">
            <span class="cq-instance-row__status cq-instance-row__status--${escapeHtml(item.status)}"></span>
            <span class="cq-instance-row__main">
              <span class="cq-instance-row__title">${escapeHtml(item.name || item.templateName || `实例 #${item.id}`)}</span>
              <span class="cq-instance-row__meta">${escapeHtml(item.symbol || '--')} · ${escapeHtml(getInstanceStatusLabel(item.status))}</span>
            </span>
            <span class="cq-instance-row__metric" style="color:${pnlColor};">${formatSignedPnl(item.totalPnl)}</span>
            <span class="cq-instance-row__metric">${runtimeMetric}</span>
            <span class="cq-instance-row__action">查看 →</span>
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
  // 文案对齐数据：实际只拉 type=auto_pause，empty 提示也用「自动暂停」
  // 而不是宽泛的「风险事件」（含 risk_alert 等其他类型）
  container.innerHTML = renderEventListMarkup(items, '24 小时内没有自动暂停事件');
}

function renderSystemStatus(status) {
  const container = document.getElementById('dashboard-system-status');
  if (!container) return;
  // status 为 null(API 失败 / 冷启动还没拉)时给明确占位,避免"卡片只剩标题"
  if (!status) {
    container.innerHTML = '<div class="cq-empty-state cq-empty-state--compact"><p>系统状态加载中…</p></div>';
    return;
  }
  const runner = status.strategy_runner;
  const exchanges = Array.isArray(status.exchanges) ? status.exchanges : [];
  // 执行器状态分 3 档：无任务（中性）/ 全部就绪（profit）/ 部分异常（loss）
  // 旧版只显示 "0/0 就绪" 含糊不清 — 是没策略还是 runner 挂了？
  let runnerLine;
  if (!runner) {
    runnerLine = '<div class="cq-status-list__item"><span>执行器</span><span>--</span></div>';
  } else if ((runner.task_count || 0) === 0) {
    runnerLine = '<div class="cq-status-list__item"><span>执行器</span><span style="color:var(--cq-text-tertiary);">空闲（无运行实例）</span></div>';
  } else if (runner.alive_count < runner.task_count) {
    const failed = runner.task_count - runner.alive_count;
    runnerLine = `<div class="cq-status-list__item"><span>执行器</span><span style="color:var(--cq-color-loss);">${runner.alive_count}/${runner.task_count} 就绪（${failed} 异常）</span></div>`;
  } else {
    runnerLine = `<div class="cq-status-list__item"><span>执行器</span><span style="color:var(--cq-color-profit);">${runner.alive_count}/${runner.task_count} 就绪</span></div>`;
  }
  container.innerHTML = `
    <div class="cq-status-list">
      ${runnerLine}
      ${exchanges.map((item) => {
        // ws_connected=true 但 latency=null（刚连上还没探活）— 显示「已连接」
        //   比「--ms」清晰；ws_connected=false → 离线（红）
        let valueHtml;
        if (!item.ws_connected) {
          valueHtml = '<span style="color:var(--cq-color-loss);">离线</span>';
        } else if (item.rest_latency_ms == null) {
          valueHtml = '<span style="color:var(--cq-color-profit);">已连接</span>';
        } else {
          valueHtml = `<span class="cq-num">${item.rest_latency_ms}ms</span>`;
        }
        return `
          <div class="cq-status-list__item">
            <span>${escapeHtml(getExchangeLabel(item.name))}</span>
            ${valueHtml}
          </div>
        `;
      }).join('')}
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
        // 时间字段统一用 <time datetime> + title hover 完整 ISO,跟 events / logs
        // 抽屉一致 — 之前 dashboard 用 <span> 没机器可读时间戳
        const atIso = String(item.at || '');
        const timeHtml = `<time datetime="${escapeHtml(atIso)}" class="cq-event-list__time" title="${escapeHtml(atIso)}">${escapeHtml(formatEventTime(item.at))}</time>`;
        // 有 instance_id 才是可点击 button（打开实例 drawer）；否则用 div
        // 渲染，视觉上仍是列表项但 hover 没 button affordance，避免点了无反应
        if (item.instance_id) {
          return `
            <button class="cq-event-list__item cq-event-list__item--sev-${escapeHtml(sev)}" type="button" onclick="openInstanceDrawer(${item.instance_id})" title="查看实例 #${escapeHtml(String(item.instance_id))} 详情">
              ${timeHtml}
              <span class="cq-event-list__type cq-log-card__type--${escapeHtml(item.type)}">${escapeHtml(typeLabel)}</span>
              <span class="cq-event-list__summary">${escapeHtml(item.summary || '--')}</span>
            </button>
          `;
        }
        return `
          <div class="cq-event-list__item cq-event-list__item--sev-${escapeHtml(sev)} is-static" title="${escapeHtml(item.summary || '')}">
            ${timeHtml}
            <span class="cq-event-list__type cq-log-card__type--${escapeHtml(item.type)}">${escapeHtml(typeLabel)}</span>
            <span class="cq-event-list__summary">${escapeHtml(item.summary || '--')}</span>
          </div>
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
  App.state.equityCharts = App.state.equityCharts || {};
  const current = App.state.equityCharts[containerId];
  if (!current) return;
  try { current.ro?.disconnect(); } catch {}
  try { current.chart?.remove(); } catch {}
  delete App.state.equityCharts[containerId];
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
  App.state.equityCharts = App.state.equityCharts || {};
  App.state.equityCharts[containerId] = { chart, ro, points };
}

function parseEquityTime(raw) {
  if (raw == null) return null;
  if (typeof raw === 'number') return raw > 1e11 ? Math.floor(raw / 1000) : Math.floor(raw);
  const parsed = Date.parse(String(raw));
  return Number.isNaN(parsed) ? null : Math.floor(parsed / 1000);
}

window.addEventListener('cq:theme-change', () => {
  // 切主题: 只要内存里有 equity 数据就 re-render (色板从 CSS var 重新读)。
  // 之前判断 App.state.equityCharts 是否存在 — 一旦图表曾被 dispose(API 抖一次,
  // 或者切页面后回来),缓存清空, 主题切换就再也不画了,看起来"图表消失"。
  if (dashboardState.equity?.points?.length) {
    renderEquityCurveChart(dashboardState.equity, 'dashboard-equity-chart');
  }
});

function formatNum(n) {
  if (n == null || Number.isNaN(Number(n))) return '--';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}
