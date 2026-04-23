/**
 * Dashboard 页面逻辑
 */
async function loadDashboard() {
  const container = document.getElementById('dashboard-content');
  container.innerHTML = '<div class="skeleton" style="height:200px;margin-bottom:16px;"></div><div class="grid-4"><div class="skeleton" style="height:80px;"></div><div class="skeleton" style="height:80px;"></div><div class="skeleton" style="height:80px;"></div><div class="skeleton" style="height:80px;"></div></div>';

  try {
    const [summary, positions, equity] = await Promise.all([
      api.getAssetSummary().catch(() => null),
      api.getPositions().catch(() => []),
      api.getEquityCurve(30).catch(() => null),
    ]);

    renderAssetSummary(summary);
    renderPositionTable(positions);
    if (equity) renderEquityCurveChart(equity);
  } catch (err) {
    container.innerHTML = `<div class="card" style="text-align:center;padding:40px;"><div style="font-size:36px;margin-bottom:12px;">📡</div><div style="font-size:15px;font-weight:600;margin-bottom:8px;">数据加载失败</div><div style="font-size:13px;color:#64748b;">${err.message}</div><button class="btn-secondary" style="margin-top:16px;" onclick="loadDashboard()">重试</button></div>`;
  }
}

function renderAssetSummary(summary) {
  if (!summary) {
    document.getElementById('asset-summary').innerHTML = '<div class="stat-card"><div class="stat-label">总资产</div><div class="stat-value" style="color:#64748b;">--</div></div>';
    return;
  }

  const pnlColor = summary.totalPnl >= 0 ? '#22c55e' : '#ef4444';
  const pnlSign = summary.totalPnl >= 0 ? '+' : '';

  document.getElementById('asset-summary').innerHTML = `
    <div class="grid-4" style="margin-bottom:24px;">
      <div class="card stat-card">
        <div class="stat-label">总资产 (USDT)</div>
        <div class="stat-value">$${formatNum(summary.totalAssets)}</div>
        <div class="stat-sub" style="color:${pnlColor}">${pnlSign}${formatNum(summary.totalPnl)} (${pnlSign}${summary.totalPnlPercent?.toFixed(2) || 0}%)</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">可用余额</div>
        <div class="stat-value" style="color:#22d3ee;">$${formatNum(summary.availableBalance)}</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">冻结余额</div>
        <div class="stat-value" style="color:#facc15;">$${formatNum(summary.frozenBalance)}</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">今日盈亏</div>
        <div class="stat-value" style="color:${summary.todayPnl >= 0 ? '#22c55e' : '#ef4444'};">${summary.todayPnl >= 0 ? '+' : ''}$${formatNum(summary.todayPnl)}</div>
      </div>
    </div>
  `;
}

function renderPositionTable(positions) {
  const el = document.getElementById('position-section');
  if (!positions || positions.length === 0) {
    el.innerHTML = `<div class="card" style="text-align:center;padding:32px;"><div style="font-size:28px;margin-bottom:8px;">📊</div><div style="font-size:13px;color:#64748b;">暂无持仓</div></div>`;
    return;
  }

  el.innerHTML = `
    <div class="card" style="padding:0;overflow:hidden;">
      <table class="data-table">
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
              <td style="font-weight:700;">${p.symbol}</td>
              <td><span class="tag ${p.side === 'long' ? 'tag-green' : 'tag-red'}">${p.side === 'long' ? '多' : '空'}</span></td>
              <td>${p.quantity}</td>
              <td>$${formatNum(p.entryPrice)}</td>
              <td>$${formatNum(p.currentPrice)}</td>
              <td style="color:${p.unrealizedPnl >= 0 ? '#22c55e' : '#ef4444'};font-weight:700;">${p.unrealizedPnl >= 0 ? '+' : ''}$${formatNum(p.unrealizedPnl)}</td>
              <td style="color:${p.unrealizedPnlPercent >= 0 ? '#22c55e' : '#ef4444'};">${p.unrealizedPnlPercent >= 0 ? '+' : ''}${p.unrealizedPnlPercent?.toFixed(2)}%</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    </div>
  `;
}

function renderEquityCurveChart(equity) {
  const canvas = document.getElementById('equityChart');
  if (!canvas || !equity.points) return;

  const ctx = canvas.getContext('2d');
  const gradient = ctx.createLinearGradient(0, 0, 0, 200);
  gradient.addColorStop(0, 'rgba(34,211,238,0.2)');
  gradient.addColorStop(1, 'rgba(34,211,238,0)');

  if (window._equityChart) window._equityChart.destroy();

  window._equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: equity.points.map(p => p.date),
      datasets: [{
        label: '权益 (USDT)',
        data: equity.points.map(p => p.equity),
        borderColor: '#22d3ee',
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.4,
        pointRadius: 0,
        pointHoverRadius: 4,
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { color: '#1f2937' }, ticks: { color: '#475569', font: { size: 10 }, maxTicksLimit: 8 } },
        y: { grid: { color: '#1f2937' }, ticks: { color: '#475569', font: { size: 10 }, callback: v => '$' + (v/1000).toFixed(1) + 'k' } }
      }
    }
  });
}

function formatNum(n) {
  if (n == null || isNaN(n)) return '--';
  return Number(n).toLocaleString('en-US', { maximumFractionDigits: 2 });
}
