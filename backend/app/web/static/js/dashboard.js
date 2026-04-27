/**
 * Dashboard 页面逻辑 v2 — 使用设计令牌
 */

/* ── SVG 图标模板 ── */
const ICONS = {
  wallet: '<svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"/><path d="M16 12h.01"/><path d="M2 10h20"/></svg>',
  chart:  '<svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10"/><path d="M12 20V4"/><path d="M6 20v-6"/></svg>',
};

async function loadDashboard() {
  const [summary, positions, equity] = await Promise.all([
    api.getAssetSummary().catch(() => null),
    api.getPortfolioPositions().catch(() => null),
    api.getEquityCurve(30).catch(() => null),
  ]);

  renderAssetSummary(summary);
  renderPositionTable(positions);
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

function renderAssetSummary(summary) {
  const el = document.getElementById('asset-summary');
  if (!summary || (summary.totalAssets === 0 && !summary.totalPnl)) {
    el.innerHTML = `
      <div class="cq-card" style="text-align:center;padding:var(--cq-space-8) var(--cq-space-6);margin-bottom:var(--cq-space-4);border:1px dashed var(--cq-border-hover);">
        ${ICONS.wallet}
        <div style="font-size:var(--cq-text-md);font-weight:600;margin-top:var(--cq-space-3);margin-bottom:var(--cq-space-2);">还没有添加交易所账户</div>
        <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);margin-bottom:var(--cq-space-4);">添加交易所账户后，在此查看资产和持仓</div>
        <button class="cq-btn cq-btn--primary cq-btn--sm" onclick="navigate('accounts')">前往添加账户 →</button>
      </div>
      <div class="cq-grid-4">
        <div class="cq-card stat-card"><div class="stat-label">总资产 (USDT)</div><div class="stat-value" style="color:var(--cq-text-tertiary);">--</div></div>
        <div class="cq-card stat-card"><div class="stat-label">可用余额</div><div class="stat-value" style="color:var(--cq-text-tertiary);">--</div></div>
        <div class="cq-card stat-card"><div class="stat-label">冻结余额</div><div class="stat-value" style="color:var(--cq-text-tertiary);">--</div></div>
        <div class="cq-card stat-card"><div class="stat-label">今日盈亏</div><div class="stat-value" style="color:var(--cq-text-tertiary);">--</div></div>
      </div>`;
    return;
  }

  const pnlColor = summary.totalPnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)';
  const pnlSign = summary.totalPnl >= 0 ? '+' : '';

  document.getElementById('asset-summary').innerHTML = `
    <div class="cq-grid-4" style="margin-bottom:var(--cq-space-6);">
      <div class="cq-card stat-card">
        <div class="stat-label">总资产 (USDT)</div>
        <div class="stat-value cq-num">$${formatNum(summary.totalAssets)}</div>
        <div class="stat-sub" style="color:${pnlColor}">${pnlSign}${formatNum(summary.totalPnl)} (${pnlSign}${summary.totalPnlPercent?.toFixed(2) || 0}%)</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">可用余额</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-primary-hover);">$${formatNum(summary.availableBalance)}</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">冻结余额</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-warning);">$${formatNum(summary.frozenBalance)}</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">今日盈亏</div>
        <div class="stat-value cq-num" style="color:${summary.todayPnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${summary.todayPnl >= 0 ? '+' : ''}$${formatNum(summary.todayPnl)}</div>
      </div>
    </div>`;
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

function renderEquityCurveChart(equity) {
  const canvas = document.getElementById('equityChart');
  if (!canvas || !equity.points) return;

  const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
  const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1';
  const gridColor = isDark ? 'rgba(139,148,158,0.12)' : 'rgba(15,23,42,0.06)';
  const tickColor = isDark ? '#6E7681' : '#94A3B8';

  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 200);
  gradient.addColorStop(0, isDark ? 'rgba(99,102,241,0.15)' : 'rgba(79,70,229,0.10)');
  gradient.addColorStop(1, 'rgba(99,102,241,0)');

  if (window._equityChart) window._equityChart.destroy();

  window._equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: equity.points.map(p => p.date),
      datasets: [{
        label: '权益 (USDT)',
        data: equity.points.map(p => p.equity),
        borderColor: primaryColor,
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 4,
        pointHoverBackgroundColor: primaryColor,
        pointHoverBorderColor: isDark ? '#fff' : '#0F172A',
        pointHoverBorderWidth: 2,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10, family: "'Geist', sans-serif" }, maxTicksLimit: 8 } },
        y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10, family: "'JetBrains Mono', monospace" }, callback: formatAxisValue } }
      }
    }
  });
}

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
