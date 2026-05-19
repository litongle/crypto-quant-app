'use strict';

const instanceDrawerState = {
  instance: null,
  klineLoaded: false,
};

async function openInstanceDrawer(instanceId) {
  const drawer = document.getElementById('instance-drawer');
  if (!drawer) return;
  drawer.hidden = false;
  document.body.classList.add('is-drawer-open');
  instanceDrawerState.klineLoaded = false;
  document.getElementById('instance-drawer-title').textContent = '加载中...';
  document.getElementById('instance-drawer-summary').innerHTML = '<div class="cq-skeleton" style="height:96px;"></div>';
  document.getElementById('instance-drawer-positions').innerHTML = '';
  document.getElementById('instance-drawer-orders').innerHTML = '';

  const [instance, snapshot] = await Promise.all([
    api.getStrategyDetail(instanceId),
    api.getStrategySnapshot(instanceId).catch(() => ({ positions: [], orders: [] })),
  ]);

  instanceDrawerState.instance = instance;
  const positions = Array.isArray(snapshot?.positions) ? snapshot.positions : [];
  const orders = Array.isArray(snapshot?.orders) ? snapshot.orders : [];

  document.getElementById('instance-drawer-title').textContent = instance.name || instance.templateName || `实例 #${instance.id}`;
  document.getElementById('instance-drawer-summary').innerHTML = renderInstanceSummary(instance);
  document.getElementById('instance-drawer-positions').innerHTML = renderInstancePositions(positions);
  document.getElementById('instance-drawer-orders').innerHTML = renderInstanceOrders(orders);
  syncInstanceDrawerActions(instance);

  const details = document.querySelector('#instance-drawer .cq-instance-kline');
  if (details && !details.dataset.bound) {
    details.addEventListener('toggle', () => {
      if (details.open) loadInstanceDrawerKline().catch(() => {});
      else destroyKlineChart('instance-drawer-kline-wrap');
    });
    details.dataset.bound = '1';
  }
}

function closeInstanceDrawer() {
  const drawer = document.getElementById('instance-drawer');
  if (!drawer) return;
  drawer.hidden = true;
  document.body.classList.remove('is-drawer-open');
  destroyKlineChart('instance-drawer-kline-wrap');
  const details = document.querySelector('#instance-drawer .cq-instance-kline');
  if (details) details.open = false;
  instanceDrawerState.instance = null;
  instanceDrawerState.klineLoaded = false;
}

async function loadInstanceDrawerKline() {
  if (!instanceDrawerState.instance || instanceDrawerState.klineLoaded) return;
  const instance = instanceDrawerState.instance;
  const market = String(instance.symbol || '').endsWith('.P') ? 'perp' : 'spot';
  const symbol = String(instance.symbol || '').replace(/\.P$/, '');
  const exchange = instance.exchange || 'binance';
  try {
    const response = await api.getKline(symbol, '1h', 120, exchange, market);
    renderKlineChart('instance-drawer-kline-wrap', response.klines || response || [], { height: 320 });
    instanceDrawerState.klineLoaded = true;
  } catch (err) {
    // 调用方吞错防 unhandled rejection；这里负责给用户反馈，避免 K 线区一片空白没解释
    const wrap = document.getElementById('instance-drawer-kline-wrap');
    if (wrap) {
      wrap.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">K 线加载失败：${escapeHtml(err?.message || '未知错误')}</div>`;
    }
    throw err;
  }
}

function renderInstanceSummary(instance) {
  return `
    <div class="cq-instance-summary__grid">
      <div><span>状态</span><strong>${escapeHtml(getInstanceStatusLabel(instance.status))}</strong></div>
      <div><span>交易对</span><strong>${escapeHtml(instance.symbol || '--')}</strong></div>
      <div><span>盈亏</span><strong>${formatSignedPnl(instance.totalPnl)}</strong></div>
      <div><span>启动时间</span><strong>${escapeHtml(instance.lastStartedAt ? formatEventDateTime(instance.lastStartedAt) : '--')}</strong></div>
    </div>
  `;
}

function syncInstanceDrawerActions(instance) {
  const pauseBtn = document.getElementById('instance-drawer-pause-btn');
  const stopBtn = document.getElementById('instance-drawer-stop-btn');
  const logsBtn = document.getElementById('instance-drawer-logs-btn');
  // 在 events 页打开 drawer 时隐藏「查看完整日志」，避免回路（点事件 → drawer → 又回到 events）
  if (logsBtn) logsBtn.hidden = _currentPage === 'events';
  if (!pauseBtn || !stopBtn) return;

  if (instance.status === 'running') {
    pauseBtn.textContent = '暂停';
    pauseBtn.disabled = false;
    stopBtn.disabled = false;
    return;
  }

  if (instance.status === 'paused' || instance.status === 'stopped') {
    pauseBtn.textContent = '恢复';
    pauseBtn.disabled = false;
    stopBtn.disabled = instance.status === 'stopped';
    return;
  }

  pauseBtn.textContent = '暂停';
  pauseBtn.disabled = true;
  stopBtn.disabled = true;
}

function renderInstancePositions(positions) {
  return `
    <div class="cq-section-title"><h3>持仓</h3></div>
    ${positions?.length ? `
      <div class="cq-table-wrap">
        <table class="cq-table">
          <thead><tr><th>交易对</th><th>方向</th><th>数量</th><th>开仓价</th><th>现价</th></tr></thead>
          <tbody>
            ${positions.map((position) => `
              <tr>
                <td>${escapeHtml(position.symbol)}</td>
                <td>${escapeHtml(getOrderSideLabel(position.side))}</td>
                <td class="cq-num">${escapeHtml(position.quantity)}</td>
                <td class="cq-num">${escapeHtml(position.entryPrice ?? position.entry_price ?? '--')}</td>
                <td class="cq-num">${escapeHtml(position.currentPrice ?? position.current_price ?? '--')}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>` : '<div class="cq-empty-inline">当前没有持仓</div>'}
  `;
}

function renderInstanceOrders(events) {
  return `
    <div class="cq-section-title"><h3>最近订单</h3></div>
    ${events?.length ? `
      <div class="cq-table-wrap">
        <table class="cq-table">
          <thead><tr><th>时间</th><th>方向</th><th>数量</th><th>成交价</th><th>状态</th></tr></thead>
          <tbody>
            ${events.map((item) => `
              <tr>
                <td>${escapeHtml(item.createdAt ? formatEventDateTime(item.createdAt) : '--')}</td>
                <td>${escapeHtml(getOrderSideLabel(item.side))}</td>
                <td class="cq-num">${escapeHtml(item.filledQuantity || item.quantity || '--')}</td>
                <td class="cq-num">${escapeHtml(item.avgFillPrice || item.price || '--')}</td>
                <td>${escapeHtml(getOrderStatusLabel(item.status))}</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>` : '<div class="cq-empty-inline">暂无相关订单</div>'}
  `;
}

async function instanceDrawerPause() {
  if (!instanceDrawerState.instance) return;
  try {
    if (instanceDrawerState.instance.status === 'running') {
      await api.pauseStrategy(instanceDrawerState.instance.id);
      showToast('策略已暂停', 'success');
    } else if (instanceDrawerState.instance.status === 'paused' || instanceDrawerState.instance.status === 'stopped') {
      await api.startStrategy(instanceDrawerState.instance.id);
      showToast('策略已恢复', 'success');
    } else {
      return;
    }
    closeInstanceDrawer();
    if (_currentPage === 'dashboard') await loadDashboard();
  } catch (err) {
    showToast(err.message || '操作失败', 'error');
  }
}

async function instanceDrawerStop() {
  if (!instanceDrawerState.instance) return;
  if (instanceDrawerState.instance.status === 'stopped') return;
  try {
    await api.stopStrategy(instanceDrawerState.instance.id);
    showToast('策略已停止', 'success');
    closeInstanceDrawer();
    if (_currentPage === 'dashboard') await loadDashboard();
  } catch (err) {
    showToast(err.message || '停止失败', 'error');
  }
}

function instanceDrawerViewLogs() {
  if (!instanceDrawerState.instance) return;
  const inst = instanceDrawerState.instance;
  const name = inst.name || inst.templateName || `实例 #${inst.id}`;
  closeInstanceDrawer();
  openInstanceLogsDrawer(inst.id, name);
}

function formatEventDateTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}
