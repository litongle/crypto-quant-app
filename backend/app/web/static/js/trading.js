/**
 * 交易页面逻辑 v1 — 下单 + 订单历史 + 持仓操作
 */

/* 下单表单状态 */
let tradingForm = {
  accountId: null,
  symbol: 'BTCUSDT',
  side: 'buy',
  orderType: 'market',
  quantity: '',
  price: '',
};

/* ── 加载交易页面 ── */
async function loadTradingPage() {
  // 加载账户列表
  try {
    const accounts = await api.getExchangeAccounts();
    window._tradingAccounts = accounts;
    renderTradingAccountSelect(accounts);
  } catch {
    window._tradingAccounts = [];
    renderTradingAccountSelect([]);
  }

  // 初始化交易对选择器
  if (!window._tradingSymbolSel) {
    const selEl = document.getElementById('trading-symbol-selector');
    if (selEl) {
      window._tradingSymbolSel = new SymbolSelector({
        containerId: 'trading-symbol-selector',
        value: 'BTCUSDT',
      });
    }
  }

  // 加载持仓和订单
  await refreshTradingData();
}

/* ── 账户下拉 ── */
function renderTradingAccountSelect(accounts) {
  const sel = document.getElementById('trading-account-select');
  if (!sel) return;

  if (accounts.length === 0) {
    sel.innerHTML = '<option value="">请先添加交易所账户</option>';
    return;
  }

  sel.innerHTML = accounts.map(a => {
    const meta = { binance: 'Binance', okx: 'OKX', huobi: 'HTX' }[a.exchange] || a.exchange;
    return `<option value="${a.id}">${escapeHtml(a.account_name || meta)} (${meta}) — ${Number(a.balance || 0).toFixed(2)} USDT</option>`;
  }).join('');

  tradingForm.accountId = parseInt(sel.value) || null;
}

/* ── 买卖切换 ── */
function setTradingSide(side) {
  tradingForm.side = side;
  document.querySelectorAll('.cq-side-btn').forEach(b => b.classList.remove('is-active'));
  const active = document.querySelector(`.cq-side-btn[data-side="${side}"]`);
  if (active) active.classList.add('is-active');
}

/* ── 订单类型切换 ── */
function setTradingOrderType(type) {
  tradingForm.orderType = type;
  const priceField = document.getElementById('trading-price-field');
  if (priceField) {
    priceField.style.display = type === 'limit' ? 'block' : 'none';
  }
}

/* ── 提交下单 ── */
async function submitOrder() {
  const accountSelect = document.getElementById('trading-account-select');
  const accountId = parseInt(accountSelect?.value);
  if (!accountId) {
    showToast('请选择交易所账户', 'warn');
    return;
  }

  const symbol = window._tradingSymbolSel ? window._tradingSymbolSel.getValue() : 'BTCUSDT';
  const quantity = document.getElementById('trading-quantity')?.value;
  if (!quantity || parseFloat(quantity) <= 0) {
    showToast('请输入有效数量', 'warn');
    return;
  }

  const price = tradingForm.orderType === 'limit' ? document.getElementById('trading-price')?.value : null;
  if (tradingForm.orderType === 'limit' && (!price || parseFloat(price) <= 0)) {
    showToast('限价单请输入有效价格', 'warn');
    return;
  }

  const btn = document.getElementById('trading-submit-btn');
  btn.disabled = true;
  const origHtml = btn.innerHTML;
  const sideLabel = tradingForm.side === 'buy' ? '买入' : '卖出';
  btn.innerHTML = `<svg class="cq-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg> ${sideLabel}中...`;

  try {
    await api.createOrder({
      accountId,
      symbol,
      side: tradingForm.side,
      orderType: tradingForm.orderType,
      quantity,
      price,
    });
    showToast(`${sideLabel}订单已提交`, 'success');
    // 清空数量
    const qtyInput = document.getElementById('trading-quantity');
    if (qtyInput) qtyInput.value = '';
    // 刷新数据
    refreshTradingData();
  } catch (err) {
    showToast('下单失败: ' + err.message, 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = origHtml;
  }
}

/* ── 刷新持仓和订单 ── */
async function refreshTradingData() {
  const [positions, orders] = await Promise.all([
    api.getPositions().catch(() => []),
    api.getOrders({ limit: 50 }).catch(() => []),
  ]);

  renderTradingPositions(positions);
  renderTradingOrders(orders);
}

/* ── 持仓列表（带操作按钮） ── */
function renderTradingPositions(positions) {
  const el = document.getElementById('trading-positions');
  if (!el) return;

  if (!positions || positions.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-6);"><h3>暂无持仓</h3></div>`;
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
            <th>止损</th>
            <th>止盈</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${positions.map(p => {
            const pnl = p.unrealizedPnl ?? p.unrealized_pnl ?? 0;
            const pnlPct = p.unrealizedPnlPercent ?? p.unrealized_pnl_percent ?? 0;
            const sl = p.stopLoss ?? p.stop_loss ?? null;
            const tp = p.takeProfit ?? p.take_profit ?? null;
            const posId = p.id;
            const accountId = p.accountId ?? p.account_id ?? '';
            return `
            <tr>
              <td style="font-weight:600;">${escapeHtml(p.symbol)}</td>
              <td><span class="cq-tag ${p.side === 'long' ? 'cq-tag--profit' : 'cq-tag--loss'}">${p.side === 'long' ? '多' : '空'}</span></td>
              <td class="cq-num">${p.quantity}</td>
              <td class="cq-num">$${formatNum(p.entryPrice ?? p.entry_price)}</td>
              <td class="cq-num">$${formatNum(p.currentPrice ?? p.current_price)}</td>
              <td class="cq-num" style="color:${pnl >= 0 ? 'var(--cq-color-profit)' : 'var(--cq-color-loss)'};font-weight:600;">${pnl >= 0 ? '+' : ''}$${formatNum(pnl)}</td>
              <td class="cq-num" style="color:var(--cq-color-loss);font-size:var(--cq-text-sm);">${sl ? '$' + Number(sl).toFixed(2) : '--'}</td>
              <td class="cq-num" style="color:var(--cq-color-profit);font-size:var(--cq-text-sm);">${tp ? '$' + Number(tp).toFixed(2) : '--'}</td>
              <td style="white-space:nowrap;">
                <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="showSlTpDialog(${posId}, ${accountId})" title="设置止损止盈">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/></svg>
                </button>
                <button class="cq-btn cq-btn--danger cq-btn--sm" onclick="closePositionAction(${posId})" title="平仓">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>
    </div>

    <div style="margin-top:var(--cq-space-3);display:flex;justify-content:flex-end;">
      <button class="cq-btn cq-btn--danger" onclick="emergencyCloseAllAction()" style="font-size:var(--cq-text-sm);">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        紧急一键平仓
      </button>
    </div>`;
}

/* ── 订单历史 ── */
function renderTradingOrders(orders) {
  const el = document.getElementById('trading-orders');
  if (!el) return;

  if (!orders || orders.length === 0) {
    el.innerHTML = `
      <div class="cq-card cq-empty-state" style="padding:var(--cq-space-6);"><h3>暂无订单记录</h3></div>`;
    return;
  }

  const statusMap = {
    pending: '<span class="cq-tag cq-tag--warn">待提交</span>',
    submitted: '<span class="cq-tag cq-tag--info">已提交</span>',
    partial: '<span class="cq-tag cq-tag--info">部分成交</span>',
    filled: '<span class="cq-tag cq-tag--profit">已成交</span>',
    cancelled: '<span class="cq-tag cq-tag--neutral">已取消</span>',
    rejected: '<span class="cq-tag cq-tag--loss">已拒绝</span>',
    error: '<span class="cq-tag cq-tag--loss">异常</span>',
  };

  el.innerHTML = `
    <div class="cq-card" style="padding:0;overflow:hidden;">
      <div class="cq-table-wrap">
      <table class="cq-table">
        <thead>
          <tr>
            <th>交易对</th>
            <th>方向</th>
            <th>类型</th>
            <th style="text-align:right;">数量</th>
            <th style="text-align:right;">价格</th>
            <th>状态</th>
            <th>时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${orders.slice(0, 50).map(o => {
            const status = (o.status || '').toLowerCase();
            const statusHtml = statusMap[status] || `<span class="cq-tag cq-tag--neutral">${escapeHtml(o.status)}</span>`;
            const time = o.createdAt || o.created_at || '';
            const timeStr = time ? time.substring(0, 16).replace('T', ' ') : '--';
            const canCancel = ['pending', 'submitted', 'partial'].includes(status);
            return `
            <tr>
              <td style="font-weight:600;">${escapeHtml(o.symbol)}</td>
              <td><span class="cq-tag ${o.side === 'buy' ? 'cq-tag--profit' : 'cq-tag--loss'}">${o.side === 'buy' ? '买' : '卖'}</span></td>
              <td style="color:var(--cq-text-secondary);">${o.orderType || o.order_type || '--'}</td>
              <td class="cq-num" style="text-align:right;">${o.quantity || '--'}</td>
              <td class="cq-num" style="text-align:right;">${o.price ? '$' + Number(o.price).toFixed(2) : '--'}</td>
              <td>${statusHtml}</td>
              <td style="color:var(--cq-text-tertiary);font-size:var(--cq-text-sm);">${timeStr}</td>
              <td>${canCancel ? `<button class="cq-btn cq-btn--danger cq-btn--sm" onclick="cancelOrderAction(${o.id})">撤单</button>` : ''}</td>
            </tr>`;
          }).join('')}
        </tbody>
      </table>
      </div>
    </div>`;
}

/* ── 持仓操作：止损止盈弹窗 ── */
function showSlTpDialog(positionId, accountId) {
  const el = document.getElementById('sltp-dialog');
  if (!el) return;
  el.dataset.positionId = positionId;
  el.dataset.accountId = accountId;
  el.classList.add('is-visible');
  // 清空输入
  const slInput = document.getElementById('sltp-stop-price');
  const tpInput = document.getElementById('sltp-take-price');
  if (slInput) slInput.value = '';
  if (tpInput) tpInput.value = '';
}

function closeSlTpDialog() {
  const el = document.getElementById('sltp-dialog');
  if (el) el.classList.remove('is-visible');
}

async function submitSlTp() {
  const el = document.getElementById('sltp-dialog');
  const positionId = el?.dataset.positionId;
  const accountId = el?.dataset.accountId;
  const stopPrice = document.getElementById('sltp-stop-price')?.value;
  const takePrice = document.getElementById('sltp-take-price')?.value;

  try {
    if (stopPrice && parseFloat(stopPrice) > 0) {
      await api.setStopLoss(positionId, accountId, stopPrice);
      showToast('止损已设置', 'success');
    }
    if (takePrice && parseFloat(takePrice) > 0) {
      await api.setTakeProfit(positionId, accountId, takePrice);
      showToast('止盈已设置', 'success');
    }
    closeSlTpDialog();
    refreshTradingData();
  } catch (err) {
    showToast('设置失败: ' + err.message, 'error');
  }
}

/* ── 平仓 ── */
async function closePositionAction(positionId) {
  if (!confirm('确认平仓此仓位？')) return;
  try {
    await api.closePosition(positionId);
    showToast('平仓成功', 'success');
    refreshTradingData();
  } catch (err) {
    showToast('平仓失败: ' + err.message, 'error');
  }
}

/* ── 紧急一键平仓 ── */
async function emergencyCloseAllAction() {
  if (!confirm('⚠️ 确认紧急平仓所有仓位？此操作不可撤销！')) return;
  try {
    const result = await api.emergencyCloseAll();
    showToast(`已平仓 ${result.closed_count || 0} 个仓位`, 'success');
    refreshTradingData();
  } catch (err) {
    showToast('紧急平仓失败: ' + err.message, 'error');
  }
}

/* ── 撤单 ── */
async function cancelOrderAction(orderId) {
  if (!confirm('确认撤销此订单？')) return;
  try {
    await api.cancelOrder(orderId);
    showToast('撤单成功', 'success');
    refreshTradingData();
  } catch (err) {
    showToast('撤单失败: ' + err.message, 'error');
  }
}
