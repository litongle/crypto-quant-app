/**
 * Dashboard 页面逻辑 v2 — 使用设计令牌
 */

/* ── SVG 图标模板 ── */
const ICONS = {
  wallet: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M16 12h.01"/><path d="M2 10h20"/></svg>',
  chart:  '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>',
};

async function loadDashboard() {
  const [summary, positions, equity, instances] = await Promise.all([
    api.getAssetSummary().catch(() => null),
    api.getPortfolioPositions().catch(() => null),
    api.getEquityCurve(30).catch(() => null),
    api.getStrategyInstances('all').catch(() => []),
  ]);

  renderStatGrid({ summary, positions, equity, instances });
  renderPositionTable(positions);
  if (equity && equity.points && equity.points.length > 0) {
    renderEquityCurveChart(equity);
  } else {
    _disposeEquityChart();
    const chartEl = document.getElementById('equityChart');
    if (chartEl) {
      chartEl.innerHTML = `
        <div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--cq-text-tertiary);font-size:var(--cq-text-base);">暂无权益曲线数据</div>`;
    }
  }
}

/* ── 权益曲线天数切换 ── */
async function changeEquityDays(days) {
  // 更新选中态
  document.querySelectorAll('.cq-day-pill').forEach(b => b.classList.remove('is-active'));
  const active = document.querySelector(`.cq-day-pill[data-days="${days}"]`);
  if (active) active.classList.add('is-active');

  try {
    const equity = await api.getEquityCurve(days);
    if (equity && equity.points && equity.points.length > 0) {
      renderEquityCurveChart(equity);
    } else {
      const chartEl = document.getElementById('equityChart');
      if (chartEl) {
        chartEl.parentElement.innerHTML = `
          <div class="cq-card" style="text-align:center;padding:var(--cq-space-10) var(--cq-space-6);">
            <div style="color:var(--cq-text-tertiary);font-size:var(--cq-text-base);">暂无权益曲线数据</div>
          </div>`;
      }
    }
  } catch {
    showToast('加载权益曲线失败', 'error');
  }
}

/* ── Stat Grid icons (单色线性,放在卡标题左侧) ── */
const STAT_ICONS = {
  wallet:    '<svg viewBox="0 0 24 24"><rect x="2" y="6" width="20" height="14" rx="2"/><path d="M16 13h.01"/><path d="M2 11h20"/></svg>',
  trending:  '<svg viewBox="0 0 24 24"><polyline points="3 17 9 11 13 15 21 7"/><polyline points="14 7 21 7 21 14"/></svg>',
  flash:     '<svg viewBox="0 0 24 24"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>',
  shield:    '<svg viewBox="0 0 24 24"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>',
};

/* 子项 avatar 图标(白色 stroke,放在彩色圆里) */
const ROW_ICONS = {
  cash:      '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M14.5 9h-3a1.5 1.5 0 0 0 0 3h2a1.5 1.5 0 0 1 0 3h-3"/><path d="M12 7v1.5M12 15v1"/></svg>',
  history:   '<svg viewBox="0 0 24 24"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/><polyline points="12 8 12 12 15 14"/></svg>',
  arrowUp:   '<svg viewBox="0 0 24 24"><line x1="12" y1="19" x2="12" y2="5"/><polyline points="5 12 12 5 19 12"/></svg>',
  list:      '<svg viewBox="0 0 24 24"><line x1="8" y1="6" x2="21" y2="6"/><line x1="8" y1="12" x2="21" y2="12"/><line x1="8" y1="18" x2="21" y2="18"/><line x1="3" y1="6" x2="3.01" y2="6"/><line x1="3" y1="12" x2="3.01" y2="12"/><line x1="3" y1="18" x2="3.01" y2="18"/></svg>',
  play:      '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><polygon points="10 8 16 12 10 16 10 8"/></svg>',
  signal:    '<svg viewBox="0 0 24 24"><path d="M2 17l10-10 4 4 6-6"/><path d="M16 7h6v6"/></svg>',
  drawdown:  '<svg viewBox="0 0 24 24"><polyline points="3 7 9 13 13 9 21 17"/><polyline points="14 17 21 17 21 10"/></svg>',
  position:  '<svg viewBox="0 0 24 24"><rect x="3" y="11" width="18" height="10" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>',
};

/* 数字 / 百分比格式化辅助 */
function _statNumOrDash(v, prefix = '', suffix = '') {
  if (v == null || isNaN(v)) return '--';
  return `${prefix}${formatNum(v)}${suffix}`;
}
function _statSignedPct(v) {
  if (v == null || isNaN(v)) return '';
  const sign = v >= 0 ? '+' : '';
  return `${sign}${Number(v).toFixed(2)}%`;
}

/* 单个子项行 */
function _statRow({ avatarColor, icon, label, value, valueClass = '', sub = '', subClass = '' }) {
  return `
    <div class="cq-stat-row">
      <span class="cq-stat-avatar cq-stat-avatar--${avatarColor}">${icon}</span>
      <div class="cq-stat-row__body">
        <div class="cq-stat-row__label">${escapeHtml(label)}</div>
        <div class="cq-stat-row__value ${valueClass}">${value}</div>
        ${sub ? `<div class="cq-stat-row__sub ${subClass}">${sub}</div>` : ''}
      </div>
    </div>`;
}

/* ── Stat Grid 主渲染:4 卡 × 2 行 ── */
function renderStatGrid({ summary, positions, equity, instances }) {
  const el = document.getElementById('asset-summary');
  if (!el) return;

  const empty = !summary || (summary.totalAssets === 0 && !summary.totalPnl);
  const emptyPromptHtml = empty ? `
    <div class="cq-card" style="text-align:center;padding:var(--cq-space-8) var(--cq-space-6);margin-bottom:var(--cq-space-6);border:1px dashed var(--cq-border-hover);">
      ${ICONS.wallet}
      <div style="font-size:var(--cq-text-md);font-weight:600;margin-top:var(--cq-space-3);margin-bottom:var(--cq-space-2);">还没有添加交易所账户</div>
      <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);margin-bottom:var(--cq-space-4);">添加交易所账户后，在此查看资产和持仓</div>
      <button class="cq-btn cq-btn--primary cq-btn--sm" onclick="navigate('accounts')">前往添加账户 →</button>
    </div>` : '';
  if (empty) summary = null;

  const totalPnl = summary?.totalPnl;
  const totalPnlPct = summary?.totalPnlPercent;
  const todayPnl = summary?.todayPnl;
  const todayPnlPct = summary?.todayPnlPercent;
  const positionsCount = Array.isArray(positions) ? positions.length : null;
  const list = Array.isArray(instances) ? instances : (instances?.data ?? []);
  const totalInstances = list.length;
  const runningInstances = list.filter(s => s.status === 'running').length;
  const maxDrawdownPct = equity?.maxDrawdown;
  const winRate = equity?.winRate;

  const cards = [
    {
      title: '账户资产',
      icon: STAT_ICONS.wallet,
      action: { label: '充值', onclick: "navigate('accounts')" },
      rows: [
        _statRow({
          avatarColor: 'blue',
          icon: ROW_ICONS.cash,
          label: '总资产 (USDT)',
          value: _statNumOrDash(summary?.totalAssets, '$'),
        }),
        _statRow({
          avatarColor: 'violet',
          icon: ROW_ICONS.history,
          label: '历史盈亏',
          value: totalPnl == null ? '--' : `${totalPnl >= 0 ? '+' : ''}${formatNum(totalPnl)}`,
          valueClass: totalPnl == null ? '' : (totalPnl >= 0 ? 'cq-stat-row__value--profit' : 'cq-stat-row__value--loss'),
          sub: _statSignedPct(totalPnlPct),
          subClass: (totalPnlPct ?? 0) >= 0 ? 'cq-stat-row__sub--profit' : 'cq-stat-row__sub--loss',
        }),
      ],
    },
    {
      title: '今日表现',
      icon: STAT_ICONS.trending,
      rows: [
        _statRow({
          avatarColor: 'green',
          icon: ROW_ICONS.arrowUp,
          label: '今日盈亏',
          value: todayPnl == null ? '--' : `${todayPnl >= 0 ? '+' : ''}${formatNum(todayPnl)}`,
          valueClass: todayPnl == null ? '' : (todayPnl >= 0 ? 'cq-stat-row__value--profit' : 'cq-stat-row__value--loss'),
          sub: _statSignedPct(todayPnlPct),
          subClass: (todayPnlPct ?? 0) >= 0 ? 'cq-stat-row__sub--profit' : 'cq-stat-row__sub--loss',
        }),
        _statRow({
          avatarColor: 'cyan',
          icon: ROW_ICONS.list,
          label: '今日交易次数',
          value: summary?.todayTradeCount == null ? '--' : String(summary.todayTradeCount),
        }),
      ],
    },
    {
      title: '运行中策略',
      icon: STAT_ICONS.flash,
      action: list.length > 0 ? { label: '查看', onclick: "navigate('strategy')" } : null,
      rows: [
        _statRow({
          avatarColor: 'yellow',
          icon: ROW_ICONS.play,
          label: '活跃策略',
          value: list.length === 0 ? '0' : `${runningInstances}<span class="cq-stat-row__sub" style="margin-left:6px;color:var(--cq-text-tertiary);">/ ${totalInstances}</span>`,
        }),
        _statRow({
          avatarColor: 'pink',
          icon: ROW_ICONS.signal,
          label: '累计实例',
          value: totalInstances === 0 ? '--' : String(totalInstances),
        }),
      ],
    },
    {
      title: '风控指标',
      icon: STAT_ICONS.shield,
      rows: [
        _statRow({
          avatarColor: 'orange',
          icon: ROW_ICONS.drawdown,
          label: '最大回撤',
          value: maxDrawdownPct == null ? '--' : `${Number(maxDrawdownPct).toFixed(2)}%`,
          valueClass: maxDrawdownPct == null ? '' : 'cq-stat-row__value--loss',
        }),
        _statRow({
          avatarColor: 'blue',
          icon: ROW_ICONS.position,
          label: '当前持仓',
          value: positionsCount == null ? '--' : String(positionsCount),
        }),
      ],
    },
  ];

  const gridHtml = `
    <div class="cq-stat-grid">
      ${cards.map(c => `
        <div class="cq-stat-card">
          <div class="cq-stat-card__header">
            <div class="cq-stat-card__title">${c.icon}<span>${escapeHtml(c.title)}</span></div>
            ${c.action ? `<button class="cq-stat-card__action" onclick="${c.action.onclick}">${escapeHtml(c.action.label)}</button>` : ''}
          </div>
          ${c.rows.join('')}
        </div>
      `).join('')}
    </div>`;

  el.innerHTML = emptyPromptHtml + gridHtml;
}

function renderPositionTable(positions) {
  const el = document.getElementById('position-section');
  if (!positions || positions.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-8);">
        ${ICONS.chart}
        <h3>暂无持仓</h3>
        <p>运行策略后将在此展示</p>
      </div>`;
    return;
  }

  el.innerHTML = `
    <div class="cq-card" style="padding:0;overflow:hidden;">
      <div class="cq-table-wrap">
      <table class="cq-table">
        <thead>
          <tr>
            <th>交易对</th>
            <th>方向</th>
            <th>数量</th>
            <th>开仓价</th>
            <th>现价</th>
            <th>未实现盈亏</th>
            <th>收益率</th>
          </tr>
        </thead>
        <tbody>
          ${positions.map(p => `
            <tr>
              <td style="font-weight:600;color:var(--cq-text-primary);">${escapeHtml(p.symbol)}</td>
              <td><span class="cq-tag ${p.side === 'long' ? 'cq-tag--profit' : 'cq-tag--loss'}">${p.side === 'long' ? '多' : '空'}</span></td>
              <td class="cq-num">${p.quantity}</td>
              <td class="cq-num">$${formatNum(p.entryPrice)}</td>
              <td class="cq-num">$${formatNum(p.currentPrice)}</td>
              <td class="cq-num" style="color:${p.unrealizedPnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};font-weight:600;">${p.unrealizedPnl >= 0 ? '+' : ''}$${formatNum(p.unrealizedPnl)}</td>
              <td class="cq-num" style="color:${p.unrealizedPnlPercent >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${p.unrealizedPnlPercent >= 0 ? '+' : ''}${p.unrealizedPnlPercent?.toFixed(2)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      </div>
    </div>`;
}

/* 把日期字符串(YYYY-MM-DD 或 ISO)转 UNIX 秒;不合法返回 null */
function _equityParseTime(raw) {
  if (raw == null) return null;
  if (typeof raw === 'number') return raw > 1e11 ? Math.floor(raw / 1000) : Math.floor(raw);
  const t = Date.parse(String(raw));
  return isNaN(t) ? null : Math.floor(t / 1000);
}

function _disposeEquityChart() {
  if (window._equityChart && typeof window._equityChart.remove === 'function') {
    try { window._equityChart.remove(); } catch {}
  }
  window._equityChart = null;
  if (window._equityResizeObserver) {
    try { window._equityResizeObserver.disconnect(); } catch {}
    window._equityResizeObserver = null;
  }
}

function renderEquityCurveChart(equity) {
  const container = document.getElementById('equityChart');
  if (!container || !equity.points) return;
  if (typeof LightweightCharts === 'undefined') return;

  const points = [];
  for (const p of equity.points) {
    const t = _equityParseTime(p.date);
    if (t == null) continue;
    points.push({ time: t, value: Number(p.equity) });
  }
  points.sort((a, b) => a.time - b.time);
  const dedup = [];
  for (const p of points) {
    if (dedup.length === 0 || dedup[dedup.length - 1].time !== p.time) dedup.push(p);
  }
  if (dedup.length === 0) return;

  _disposeEquityChart();
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
    crosshair: {
      mode: LightweightCharts.CrosshairMode.Normal,
      vertLine: { color: isDark ? 'rgba(139,148,158,0.4)' : 'rgba(15,23,42,0.3)', labelBackgroundColor: primary },
      horzLine: { color: isDark ? 'rgba(139,148,158,0.4)' : 'rgba(15,23,42,0.3)', labelBackgroundColor: primary },
    },
    rightPriceScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      scaleMargins: { top: 0.10, bottom: 0.06 },
    },
    timeScale: {
      borderColor: isDark ? 'rgba(139,148,158,0.15)' : 'rgba(15,23,42,0.10)',
      timeVisible: false,
      secondsVisible: false,
    },
    handleScroll: false,
    handleScale: false,
  });

  const series = chart.addAreaSeries({
    lineColor: primary,
    lineWidth: 2,
    topColor: isDark ? 'rgba(99,102,241,0.30)' : 'rgba(79,70,229,0.20)',
    bottomColor: 'rgba(99,102,241,0)',
    priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
  });
  series.setData(dedup);
  chart.timeScale().fitContent();

  const ro = new ResizeObserver(entries => {
    for (const e of entries) {
      const { width, height } = e.contentRect;
      chart.applyOptions({ width: Math.floor(width), height: Math.floor(height) });
    }
  });
  ro.observe(container);

  window._equityChart = chart;
  window._equityCurveData = dedup;
  window._equityResizeObserver = ro;
}

window.addEventListener('cq:theme-change', () => {
  const data = window._equityCurveData;
  if (data && document.getElementById('equityChart')) {
    renderEquityCurveChart({ points: data.map(p => ({ date: p.time * 1000, equity: p.value })) });
  }
});

function formatNum(n) {
  if (n == null || isNaN(n)) return '--';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}

/** Chart.js Y轴自适应刻度：大额显示$k，小额显示原值 */
function formatAxisValue(v) {
  if (Math.abs(v) >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
  if (Math.abs(v) >= 1000) return '$' + (v / 1000).toFixed(1) + 'k';
  return '$' + v.toFixed(0);
}

/** HTML转义，防止XSS */
function escapeHtml(str) {
  if (str == null) return '';
  return String(str).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

/** 获取本地日期 YYYY-MM-DD（避免 toISOString 的 UTC 时区偏差） */
function localDate(d = new Date()) {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}
