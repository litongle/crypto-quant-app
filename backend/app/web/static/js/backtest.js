/**
 * 回测页面逻辑 v2 — 使用设计令牌
 */
async function loadBacktestPage() {
  // 设置默认日期（动态，不过期）
  const startEl = document.getElementById('backtest-start');
  const endEl = document.getElementById('backtest-end');
  const today = localDate();
  if (endEl && !endEl.value) {
    endEl.value = today;
  }
  if (startEl && !startEl.value) {
    const d = new Date();
    d.setFullYear(d.getFullYear() - 1);
    startEl.value = localDate(d);
  }
  // 限制日期不能选未来
  if (startEl) startEl.max = today;
  if (endEl) endEl.max = today;

  // 初始化交易对选择器（只创建一次）
  if (!window._backtestSymbolSel) {
    const selEl = document.getElementById('backtest-symbol-selector');
    if (selEl) {
      window._backtestSymbolSel = new SymbolSelector({
        containerId: 'backtest-symbol-selector',
        value: 'BTCUSDT',
      });
    }
  }

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

  const symbol = window._backtestSymbolSel ? window._backtestSymbolSel.getValue() : 'BTCUSDT';
  const startDate = document.getElementById('backtest-start').value || (() => { const d = new Date(); d.setFullYear(d.getFullYear() - 1); return localDate(d); })();
  const endDate = document.getElementById('backtest-end').value || localDate();

  // 日期校验
  const today = localDate();
  if (startDate > endDate) { showToast('开始日期不能晚于结束日期', 'warn'); return; }
  if (endDate > today) { showToast('结束日期不能是未来日期', 'warn'); return; }
  if (startDate > today) { showToast('开始日期不能是未来日期', 'warn'); return; }

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
        <h3>${escapeHtml(err.message)}</h3>
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
  // 扩展指标
  const annualReturn = metrics.annualReturn ?? metrics.annual_return ?? 0;
  const calmarRatio = metrics.calmarRatio ?? metrics.calmar_ratio ?? 0;
  const profitTrades = metrics.profitTrades ?? metrics.profit_trades ?? 0;
  const lossTrades = metrics.lossTrades ?? metrics.loss_trades ?? 0;
  const avgProfit = metrics.avgProfit ?? metrics.avg_profit ?? 0;
  const avgLoss = metrics.avgLoss ?? metrics.avg_loss ?? 0;
  const maxConWins = metrics.maxConsecutiveWins ?? metrics.max_consecutive_wins ?? 0;
  const maxConLosses = metrics.maxConsecutiveLosses ?? metrics.max_consecutive_losses ?? 0;
  const duration = metrics.duration ?? 0;
  const initialCapital = metrics.initialCapital ?? result.initialCapital ?? 100000;
  const finalCapital = metrics.finalCapital ?? result.finalCapital ?? 100000;
  const trades = result.trades || [];

  el.innerHTML = `
    <div class="cq-grid-3" style="margin-bottom:var(--cq-space-4);">
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

    <!-- 扩展指标：2列布局，紧凑风格 -->
    <div class="cq-card cq-metrics-detail" style="margin-bottom:var(--cq-space-4);">
      <div class="cq-metrics-detail__header" onclick="this.parentElement.classList.toggle('is-collapsed')">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3v18h18"/><path d="M18.7 8l-5.1 5.2-2.8-2.7L7 14.3"/></svg>
          <span style="font-size:var(--cq-text-md);font-weight:600;">详细指标</span>
        </div>
        <svg class="cq-metrics-detail__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
      </div>
      <div class="cq-metrics-detail__body">
        <div class="cq-metrics-detail__grid">
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">年化收益率</span><span class="cq-metrics-detail__value cq-num" style="color:${annualReturn >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${annualReturn >= 0 ? '+' : ''}${annualReturn.toFixed(2)}%</span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">卡玛比率</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-primary-hover);">${calmarRatio.toFixed(2)}</span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">盈利 / 亏损次数</span><span class="cq-metrics-detail__value cq-num"><span style="color:var(--cq-color-profit);">${profitTrades}</span> / <span style="color:var(--cq-color-loss);">${lossTrades}</span></span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">平均盈利</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-profit);">+${avgProfit.toFixed(2)}</span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">平均亏损</span><span class="cq-metrics-detail__value cq-num" style="color:var(--cq-color-loss);">${avgLoss.toFixed(2)}</span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">最大连胜 / 连亏</span><span class="cq-metrics-detail__value cq-num"><span style="color:var(--cq-color-profit);">${maxConWins}</span> / <span style="color:var(--cq-color-loss);">${maxConLosses}</span></span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">交易天数</span><span class="cq-metrics-detail__value cq-num">${duration} 天</span></div>
          <div class="cq-metrics-detail__item"><span class="cq-metrics-detail__label">初始 / 最终权益</span><span class="cq-metrics-detail__value cq-num">${formatAxisValue(initialCapital)} → ${formatAxisValue(finalCapital)}</span></div>
        </div>
      </div>
    </div>

    <div class="cq-card" style="margin-bottom:var(--cq-space-4);">
      <div class="cq-section-title" style="margin-bottom:var(--cq-space-3);">
        <h3>收益曲线</h3>
      </div>
      <div style="position:relative;height:280px;width:100%;">
        <canvas id="backtestResultChart"></canvas>
      </div>
    </div>

    <!-- 交易明细表 -->
    ${trades.length > 0 ? `
    <div class="cq-card cq-trades-detail">
      <div class="cq-metrics-detail__header" onclick="this.parentElement.classList.toggle('is-collapsed')">
        <div style="display:flex;align-items:center;gap:var(--cq-space-2);">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-primary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span style="font-size:var(--cq-text-md);font-weight:600;">交易明细</span>
          <span class="cq-tag cq-tag--neutral" style="margin-left:var(--cq-space-1);">${trades.length} 笔</span>
        </div>
        <svg class="cq-metrics-detail__chevron" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-tertiary)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 9l6 6 6-6"/></svg>
      </div>
      <div class="cq-metrics-detail__body">
        <div class="cq-table-wrap">
        <table class="cq-table cq-trades-table">
          <thead>
            <tr>
              <th>#</th>
              <th>方向</th>
              <th style="text-align:right;">开仓价</th>
              <th style="text-align:right;">平仓价</th>
              <th style="text-align:right;">数量</th>
              <th style="text-align:right;">盈亏</th>
              <th>开仓时间</th>
              <th>平仓时间</th>
            </tr>
          </thead>
          <tbody>
            ${trades.map((t, i) => {
              const pnl = t.pnl ?? 0;
              const sideLabel = t.side === 'long' ? '多' : '空';
              const sideClass = t.side === 'long' ? 'cq-tag--profit' : 'cq-tag--loss';
              const entryPrice = t.entryPrice ?? 0;
              const exitPrice = t.exitPrice ?? 0;
              const qty = t.quantity ?? 0;
              const entryTime = t.entryTime ? t.entryTime.substring(0, 16).replace('T', ' ') : '--';
              const exitTime = t.exitTime ? t.exitTime.substring(0, 16).replace('T', ' ') : '--';
              return `
              <tr>
                <td style="color:var(--cq-text-tertiary);">${i + 1}</td>
                <td><span class="cq-tag ${sideClass}">${sideLabel}</span></td>
                <td class="cq-num" style="text-align:right;">${entryPrice.toFixed(2)}</td>
                <td class="cq-num" style="text-align:right;">${exitPrice.toFixed(2)}</td>
                <td class="cq-num" style="text-align:right;">${qty.toFixed(4)}</td>
                <td class="cq-num" style="text-align:right;color:${pnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};font-weight:500;">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</td>
                <td style="color:var(--cq-text-secondary);font-size:var(--cq-text-sm);">${entryTime}</td>
                <td style="color:var(--cq-text-secondary);font-size:var(--cq-text-sm);">${exitTime}</td>
              </tr>`;
            }).join('')}
          </tbody>
        </table>
        </div>
      </div>
    </div>` : ''}`;

  const points = result.equityCurve || result.points || [];
  if (points.length > 0) {
    const isDark = document.documentElement.getAttribute('data-theme') !== 'light';
    const primaryColor = getComputedStyle(document.documentElement).getPropertyValue('--cq-color-primary').trim() || '#6366F1';
    const gridColor = isDark ? 'rgba(139,148,158,0.12)' : 'rgba(15,23,42,0.06)';
    const tickColor = isDark ? '#6E7681' : '#94A3B8';

    const canvas = document.getElementById('backtestResultChart');
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createLinearGradient(0, 0, 0, 200);
    gradient.addColorStop(0, isDark ? 'rgba(99,102,241,0.12)' : 'rgba(79,70,229,0.08)');
    gradient.addColorStop(1, 'rgba(99,102,241,0)');

    if (window._backtestChart) window._backtestChart.destroy();
    window._backtestChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels: points.map(p => p.date || ''),
        datasets: [{
          label: '策略权益',
          data: points.map(p => p.equity),
          borderColor: primaryColor,
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
          x: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10, family: "'Geist', sans-serif" }, maxTicksLimit: 8 } },
          y: { grid: { color: gridColor }, ticks: { color: tickColor, font: { size: 10, family: "'JetBrains Mono', monospace" }, callback: formatAxisValue } }
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
          ${history.map(h => {
            const ret = h.totalReturnPercent ?? 0;
            const sharpe = h.sharpeRatio ?? 0;
            const dd = h.maxDrawdown ?? 0;
            const wr = h.winRate ?? 0;
            const trades = h.totalTrades ?? 0;
            return `
            <tr style="cursor:pointer;" onclick="viewBacktestDetail(${h.id})">
              <td style="color:var(--cq-text-primary);font-weight:500;">${escapeHtml(h.templateName || h.templateId)}</td>
              <td style="color:var(--cq-text-secondary);">${escapeHtml(h.symbol)}</td>
              <td class="cq-num" style="text-align:right;color:${ret >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};">${ret >= 0 ? '+' : ''}${ret.toFixed(2)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-primary-hover);">${sharpe.toFixed(2)}</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-loss);">${dd.toFixed(2)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-color-profit);">${wr.toFixed(1)}%</td>
              <td class="cq-num" style="text-align:right;color:var(--cq-text-secondary);">${trades}</td>
              <td style="text-align:right;color:var(--cq-text-tertiary);">${h.createdAt ? h.createdAt.substring(0, 10) : ''}</td>
            </tr>`;
          }).join('')}
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
