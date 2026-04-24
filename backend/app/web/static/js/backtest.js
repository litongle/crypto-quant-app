/**
 * 回测页面逻辑
 */
async function loadBacktestPage() {
  // 加载策略模板供选择
  try {
    const templates = await api.getStrategyTemplates();
    renderBacktestTemplateSelect(templates);
  } catch {
    document.getElementById('backtest-template-select').innerHTML = '<option value="">加载失败</option>';
  }
  // 加载回测历史
  try {
    const history = await api.getBacktestHistory(10);
    renderBacktestHistory(history);
  } catch {
    // 静默失败
  }
}

function renderBacktestTemplateSelect(templates) {
  const sel = document.getElementById('backtest-template-select');
  sel.innerHTML = '<option value="">选择策略模板</option>' +
    templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
}

async function runBacktest() {
  const templateId = document.getElementById('backtest-template-select').value;
  if (!templateId) { showToast('⚠️ 请选择策略模板'); return; }

  const symbol = document.getElementById('backtest-symbol').value.trim() || 'BTCUSDT';
  const startDate = document.getElementById('backtest-start').value || '2024-01-01';
  const endDate = document.getElementById('backtest-end').value || '2025-12-31';
  const initialCapital = parseFloat(document.getElementById('backtest-capital').value) || 100000;

  // 收集参数
  const params = {};
  document.querySelectorAll('#backtest-params input[type="range"]').forEach(sl => {
    const key = sl.id.replace('sl-bt-', '');
    params[key] = parseFloat(sl.value);
  });

  const btn = document.getElementById('run-backtest-btn');
  btn.disabled = true;
  btn.textContent = '⏳ 回测运行中...';

  try {
    const result = await api.runBacktest({
      templateId,
      symbol,
      startDate,
      endDate,
      initialCapital,
      params,
    });

    renderBacktestResults(result);
    showToast('✅ 回测完成！');
  } catch (err) {
    showToast('❌ 回测失败: ' + err.message);
    document.getElementById('backtest-results').innerHTML = `<div class="card" style="text-align:center;padding:32px;color:#64748b;">${err.message}</div>`;
  } finally {
    btn.disabled = false;
    btn.textContent = '🚀 开始回测';
  }
}

function renderBacktestResults(result) {
  const el = document.getElementById('backtest-results');

  // 如果后端返回的是简化数据，做兜底
  const metrics = result.metrics || result;
  const totalReturn = metrics.totalReturn ?? metrics.total_return ?? 0;
  const maxDrawdown = metrics.maxDrawdown ?? metrics.max_drawdown ?? 0;
  const sharpeRatio = metrics.sharpeRatio ?? metrics.sharpe_ratio ?? 0;
  const winRate = metrics.winRate ?? metrics.win_rate ?? 0;
  const totalTrades = metrics.totalTrades ?? metrics.total_trades ?? 0;
  const profitFactor = metrics.profitFactor ?? metrics.profit_factor ?? 0;

  el.innerHTML = `
    <div class="grid-3" style="margin-bottom:24px;">
      <div class="card stat-card">
        <div class="stat-label">总收益率</div>
        <div class="stat-value" style="color:${totalReturn >= 0 ? '#22c55e' : '#ef4444'};">${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">夏普比率</div>
        <div class="stat-value" style="color:#22d3ee;">${sharpeRatio.toFixed(2)}</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">最大回撤</div>
        <div class="stat-value" style="color:#ef4444;">${maxDrawdown.toFixed(2)}%</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">胜率</div>
        <div class="stat-value" style="color:#22c55e;">${winRate.toFixed(1)}%</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">盈亏比</div>
        <div class="stat-value">${profitFactor.toFixed(2)}</div>
      </div>
      <div class="card stat-card">
        <div class="stat-label">总交易次数</div>
        <div class="stat-value">${totalTrades} 笔</div>
      </div>
    </div>
    <div class="card" style="margin-bottom:16px;">
      <div style="font-size:13px;font-weight:700;margin-bottom:12px;color:#e2e8f0;">收益曲线</div>
      <canvas id="backtestResultChart" height="200"></canvas>
    </div>
  `;

  // 绘制曲线
  const points = result.equityCurve || result.points || [];
  if (points.length > 0) {
    const canvas = document.getElementById('backtestResultChart');
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, 'rgba(34,211,238,0.15)');
    gradient.addColorStop(1, 'rgba(34,211,238,0)');

    if (window._btChart) window._btChart.destroy();
    window._btChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: points.map(p => p.date || ''),
        datasets: [{
          label: '策略权益',
          data: points.map(p => p.equity),
          borderColor: '#22d3ee',
          backgroundColor: gradient,
          borderWidth: 2,
          fill: true,
          tension: 0.4,
          pointRadius: 0,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: '#1f2937' }, ticks: { color: '#475569', font: { size: 10 }, maxTicksLimit: 8 } },
          y: { grid: { color: '#1f2937' }, ticks: { color: '#475569', font: { size: 10 }, callback: v => '$' + (v/1000).toFixed(0) + 'k' } }
        }
      }
    });
  }
}

// 监听模板选择变化，渲染参数
document.addEventListener('DOMContentLoaded', () => {
  const sel = document.getElementById('backtest-template-select');
  if (sel) {
    sel.addEventListener('change', async () => {
      const templateId = sel.value;
      if (!templateId) { document.getElementById('backtest-params').innerHTML = ''; return; }
      try {
        const templates = await api.getStrategyTemplates();
        const tmpl = templates.find(t => t.id === templateId);
        if (tmpl && tmpl.params) {
          document.getElementById('backtest-params').innerHTML = tmpl.params.map(p => `
            <div style="margin-bottom:14px;">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                <label style="font-size:12px;color:#e2e8f0;">${p.name}</label>
                <span style="font-size:12px;font-weight:700;color:#22d3ee;" id="val-bt-${p.key}">${p.default}</span>
              </div>
              <input type="range" class="slider-track" id="sl-bt-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
                oninput="document.getElementById('val-bt-${p.key}').textContent=this.value">
            </div>
          `).join('');
        }
      } catch {}
    });
  }
});

/**
 * 渲染回测历史列表
 */
function renderBacktestHistory(history) {
  if (!history || history.length === 0) return;

  // 在回测结果区域下方添加历史记录
  const resultsEl = document.getElementById('backtest-results');
  const parentEl = resultsEl.parentElement;

  // 检查是否已有历史区域
  let historyEl = document.getElementById('backtest-history');
  if (!historyEl) {
    historyEl = document.createElement('div');
    historyEl.id = 'backtest-history';
    historyEl.style.cssText = 'grid-column:1/-1;margin-top:16px;';
    parentEl.appendChild(historyEl);
  }

  historyEl.innerHTML = `
    <div class="card">
      <div style="font-size:13px;font-weight:700;margin-bottom:14px;color:#e2e8f0;">📋 最近回测记录</div>
      <div class="table-wrap">
      <table style="width:100%;border-collapse:collapse;font-size:12px;min-width:600px;">
        <thead>
          <tr style="border-bottom:1px solid #1f2937;">
            <th style="text-align:left;padding:8px 4px;color:#64748b;">策略</th>
            <th style="text-align:left;padding:8px 4px;color:#64748b;">交易对</th>
            <th style="text-align:right;padding:8px 4px;color:#64748b;">收益率</th>
            <th style="text-align:right;padding:8px 4px;color:#64748b;">夏普</th>
            <th style="text-align:right;padding:8px 4px;color:#64748b;">回撤</th>
            <th style="text-align:right;padding:8px 4px;color:#64748b;">胜率</th>
            <th style="text-align:right;padding:8px 4px;color:#64748b;">交易数</th>
            <th style="text-align:right;padding:8px 4px;color:#64748b;">时间</th>
          </tr>
        </thead>
        <tbody>
          ${history.map(h => `
            <tr style="border-bottom:1px solid #111827;cursor:pointer;" onclick="viewBacktestDetail(${h.id})"
                onmouseenter="this.style.background='#111827'" onmouseleave="this.style.background=''">
              <td style="padding:8px 4px;color:#e2e8f0;">${h.templateId}</td>
              <td style="padding:8px 4px;color:#94a3b8;">${h.symbol}</td>
              <td style="padding:8px 4px;text-align:right;color:${h.totalReturnPercent >= 0 ? '#22c55e' : '#ef4444'};">${h.totalReturnPercent >= 0 ? '+' : ''}${h.totalReturnPercent.toFixed(2)}%</td>
              <td style="padding:8px 4px;text-align:right;color:#22d3ee;">${h.sharpeRatio.toFixed(2)}</td>
              <td style="padding:8px 4px;text-align:right;color:#ef4444;">${h.maxDrawdown.toFixed(2)}%</td>
              <td style="padding:8px 4px;text-align:right;color:#22c55e;">${h.winRate.toFixed(1)}%</td>
              <td style="padding:8px 4px;text-align:right;color:#94a3b8;">${h.totalTrades}</td>
              <td style="padding:8px 4px;text-align:right;color:#64748b;">${h.createdAt ? h.createdAt.substring(0, 10) : ''}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      </div>
    </div>
  `;
}

/**
 * 查看回测详情
 */
async function viewBacktestDetail(id) {
  try {
    const result = await api.getBacktestResults(id);
    renderBacktestResults(result);
    document.getElementById('backtest-results').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    showToast('❌ 加载回测详情失败');
  }
}
