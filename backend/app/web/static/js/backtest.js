/**
 * 回测页面逻辑 v2 — 使用设计令牌
 */
async function loadBacktestPage() {
  try {
    const templates = await api.getStrategyTemplates();
    renderBacktestTemplateSelect(templates);
  } catch {
    document.getElementById('backtest-template-select').innerHTML = '<option value="">加载失败</option>';
  }
  try {
    const history = await api.getBacktestHistory(10);
    renderBacktestHistory(history);
  } catch {}
}

function renderBacktestTemplateSelect(templates) {
  const sel = document.getElementById('backtest-template-select');
  sel.innerHTML = '<option value="">选择策略模板</option>' +
    templates.map(t => `<option value="${t.id}">${t.name}</option>`).join('');
}

async function runBacktest() {
  const templateId = document.getElementById('backtest-template-select').value;
  if (!templateId) { showToast('请选择策略模板', 'warn'); return; }

  const symbol = document.getElementById('backtest-symbol').value.trim() || 'BTCUSDT';
  const startDate = document.getElementById('backtest-start').value || '2024-01-01';
  const endDate = document.getElementById('backtest-end').value || '2025-12-31';
  const initialCapital = parseFloat(document.getElementById('backtest-capital').value) || 100000;

  // 计算日期跨度，给提示
  const daysDiff = Math.ceil((new Date(endDate) - new Date(startDate)) / 86400000);
  let intervalHint = '';
  if (daysDiff > 800) intervalHint = '（将使用日线级别）';
  else if (daysDiff > 200) intervalHint = '（将使用4小时级别）';
  else intervalHint = '（1小时级别）';

  const params = {};
  document.querySelectorAll('#backtest-params input[type="range"]').forEach(sl => {
    const key = sl.id.replace('sl-bt-', '');
    params[key] = parseFloat(sl.value);
  });

  const btn = document.getElementById('run-backtest-btn');
  btn.disabled = true;
  btn.innerHTML = '<svg class="cq-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg> 回测运行中' + intervalHint + '...';

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
    const extra = result.interval ? ` (${result.interval}级别, ${result.klineCount}根K线, ${result.elapsedSeconds || '?'}秒)` : '';
    showToast('回测完成！' + extra, 'success');
  } catch (err) {
    showToast('回测失败: ' + err.message, 'error');
    document.getElementById('backtest-results').innerHTML = `
      <div class="cq-card cq-empty-state">
        <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-loss)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>
        <h3>${err.message}</h3>
      </div>`;
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg> 开始回测';
  }
}

function renderBacktestResults(result) {
  const el = document.getElementById('backtest-results');

  const metrics = result.metrics || result;
  const totalReturn = metrics.totalReturn ?? metrics.total_return ?? 0;
  const maxDrawdown = metrics.maxDrawdown ?? metrics.max_drawdown ?? 0;
  const sharpeRatio = metrics.sharpeRatio ?? metrics.sharpe_ratio ?? 0;
  const winRate = metrics.winRate ?? metrics.win_rate ?? 0;
  const totalTrades = metrics.totalTrades ?? metrics.total_trades ?? 0;
  const profitFactor = metrics.profitFactor ?? metrics.profit_factor ?? 0;

  el.innerHTML = `
    <div class="cq-grid-3" style="margin-bottom:var(--cq-space-6);">
      <div class="cq-card stat-card">
        <div class="stat-label">总收益率</div>
        <div class="stat-value cq-num" style="color:${totalReturn >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${totalReturn >= 0 ? '+' : ''}${totalReturn.toFixed(2)}%</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">夏普比率</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-primary-hover);">${sharpeRatio.toFixed(2)}</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">最大回撤</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-loss);">${maxDrawdown.toFixed(2)}%</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">胜率</div>
        <div class="stat-value cq-num" style="color:var(--cq-color-profit);">${winRate.toFixed(1)}%</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">盈亏比</div>
        <div class="stat-value cq-num">${profitFactor.toFixed(2)}</div>
      </div>
      <div class="cq-card stat-card">
        <div class="stat-label">总交易次数</div>
        <div class="stat-value cq-num">${totalTrades} 笔</div>
      </div>
    </div>
    <div class="cq-card" style="margin-bottom:var(--cq-space-4);">
      <div class="cq-section-title" style="margin-bottom:var(--cq-space-3);">
        <h3>收益曲线</h3>
      </div>
      <canvas id="backtestResultChart" height="200"></canvas>
    </div>`;

  const points = result.equityCurve || result.points || [];
  if (points.length > 0) {
    const canvas = document.getElementById('backtestResultChart');
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, 'rgba(99,102,241,0.12)');
    gradient.addColorStop(1, 'rgba(99,102,241,0)');

    if (window._btChart) window._btChart.destroy();
    window._btChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: points.map(p => p.date || ''),
        datasets: [{
          label: '策略权益',
          data: points.map(p => p.equity),
          borderColor: '#6366F1',
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
          x: { grid: { color: 'rgba(31,41,55,0.5)' }, ticks: { color: '#64748B', font: { size: 10, family: "'Inter', sans-serif" }, maxTicksLimit: 8 } },
          y: { grid: { color: 'rgba(31,41,55,0.5)' }, ticks: { color: '#64748B', font: { size: 10, family: "'JetBrains Mono', monospace" }, callback: v => '$' + (v/1000).toFixed(0) + 'k' } }
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
            <div style="margin-bottom:var(--cq-space-3);">
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:var(--cq-space-2);">
                <label class="cq-label" style="margin-bottom:0;">${p.name}</label>
                <span class="cq-num" style="font-size:var(--cq-text-sm);font-weight:600;color:var(--cq-color-primary-hover);" id="val-bt-${p.key}">${p.default}</span>
              </div>
              <input type="range" class="cq-slider" id="sl-bt-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
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

  const resultsEl = document.getElementById('backtest-results');
  const parentEl = resultsEl.parentElement;

  let historyEl = document.getElementById('backtest-history');
  if (!historyEl) {
    historyEl = document.createElement('div');
    historyEl.id = 'backtest-history';
    historyEl.style.cssText = 'grid-column:1/-1;margin-top:var(--cq-space-4);';
    parentEl.appendChild(historyEl);
  }

  historyEl.innerHTML = `
    <div class="cq-card">
      <div style="font-size:var(--cq-text-md);font-weight:600;margin-bottom:var(--cq-space-3);display:flex;align-items:center;gap:var(--cq-space-2);">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
        最近回测记录
      </div>
      <div class="cq-table-wrap">
      <table class="cq-table">
        <thead>
          <tr>
            <th>策略</th>
            <th>交易对</th>
            <th style="text-align:right;">收益率</th>
            <th style="text-align:right;">夏普</th>
            <th style="text-align:right;">回撤</th>
            <th style="text-align:right;">胜率</th>
            <th style="text-align:right;">交易数</th>
            <th style="text-align:right;">时间</th>
          </tr>
        </thead>
        <tbody>
          ${history.map(h => `
            <tr style="cursor:pointer;" onclick="viewBacktestDetail(${h.id})">
              <td style="color:var(--cq-text-primary);font-weight:500;">${h.templateId}</td>
              <td style="color:var(--cq-text-secondary);">${h.symbol}</td>
              <td class="cq-num" style="text-align:right;color:${h.totalReturnPercent >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${h.totalReturnPercent >= 0 ? '+' : ''}${h.totalReturnPercent.toFixed(2)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-primary-hover);">${h.sharpeRatio.toFixed(2)}</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-loss);">${h.maxDrawdown.toFixed(2)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-profit);">${h.winRate.toFixed(1)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-text-secondary);">${h.totalTrades}</td>
              <td style="text-align:right;color:var(--cq-text-tertiary);">${h.createdAt ? h.createdAt.substring(0, 10) : ''}</td>
            </tr>
          `).join('')}
        </tbody>
      </table>
      </div>
    </div>`;
}

async function viewBacktestDetail(id) {
  try {
    const result = await api.getBacktestResults(id);
    renderBacktestResults(result);
    document.getElementById('backtest-results').scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    showToast('加载回测详情失败', 'error');
  }
}
