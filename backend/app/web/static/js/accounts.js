/**
 * 交易所账户管理页面逻辑 v2 — 使用设计令牌
 */
let accounts = [];
let showAddForm = false;

/* ── 交易所品牌色和图标 ── */
const EXCHANGE_META = {
  binance: { label: 'Binance', color: 'var(--cq-color-binance)', letter: 'B', icon: 'B' },
  okx:     { label: 'OKX',     color: 'var(--cq-color-okx)',     letter: 'O', icon: 'O' },
  huobi:   { label: 'HTX',     color: 'var(--cq-color-htx)',     letter: 'H', icon: 'H' },
};

async function loadAccountsPage() {
  const container = document.getElementById('accounts-content');
  container.innerHTML = '<div class="cq-skeleton" style="height:120px;margin-bottom:var(--cq-space-4);"></div><div class="cq-skeleton" style="height:80px;"></div>';

  try {
    accounts = await api.getExchangeAccounts();
  } catch {
    accounts = [];
  }

  renderAccounts();
}

function renderAccounts() {
  const container = document.getElementById('accounts-content');

  // 空状态
  if (accounts.length === 0 && !showAddForm) {
    container.innerHTML = `
      <div class="cq-card cq-empty-state">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/></svg>
        <h3>还没有添加交易所账户</h3>
        <p>添加 Binance / OKX / HTX 账户以开始交易</p>
        <button class="cq-btn cq-btn--primary" onclick="toggleAddForm()">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          添加交易所账户
        </button>
      </div>`;
    return;
  }

  let html = `
    <div class="cq-section-title" style="margin-bottom:var(--cq-space-4);">
      <h3>已添加的交易所账户 (${accounts.length})</h3>
      <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="toggleAddForm()">
        ${showAddForm ? '取消' : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg> 添加账户'}
      </button>
    </div>`;

  // 添加表单
  if (showAddForm) {
    html += `
    <div class="cq-card" style="margin-bottom:var(--cq-space-5);">
      <div style="font-size:var(--cq-text-md);font-weight:600;margin-bottom:var(--cq-space-4);">添加新账户</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cq-space-3);margin-bottom:var(--cq-space-3);">
        <div>
          <label class="cq-label">交易所</label>
          <select class="cq-input" id="acc-exchange">
            <option value="binance">Binance</option>
            <option value="okx">OKX</option>
            <option value="huobi">HTX (火币)</option>
          </select>
        </div>
        <div>
          <label class="cq-label">账户别名</label>
          <input type="text" class="cq-input" id="acc-name" placeholder="我的BN账户">
        </div>
      </div>
      <div style="margin-bottom:var(--cq-space-3);">
        <label class="cq-label">API Key</label>
        <input type="text" class="cq-input" id="acc-apikey" placeholder="输入 API Key">
      </div>
      <div style="margin-bottom:var(--cq-space-3);">
        <label class="cq-label">Secret Key</label>
        <input type="password" class="cq-input" id="acc-secretkey" placeholder="输入 Secret Key">
      </div>
      <div style="margin-bottom:var(--cq-space-3);" id="passphrase-field">
        <label class="cq-label">Passphrase <span style="color:var(--cq-text-disabled);">(OKX 必须，其他可不填)</span></label>
        <input type="password" class="cq-input" id="acc-passphrase" placeholder="输入 Passphrase">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:var(--cq-space-3);margin-bottom:var(--cq-space-4);">
        <label style="display:flex;align-items:center;gap:var(--cq-space-2);cursor:pointer;">
          <input type="checkbox" id="acc-testnet" style="width:16px;height:16px;accent-color:var(--cq-color-primary);">
          <span style="font-size:var(--cq-text-sm);color:var(--cq-text-secondary);">测试网 (Testnet)</span>
        </label>
        <label style="display:flex;align-items:center;gap:var(--cq-space-2);cursor:pointer;">
          <input type="checkbox" id="acc-demo" style="width:16px;height:16px;accent-color:var(--cq-color-primary);">
          <span style="font-size:var(--cq-text-sm);color:var(--cq-text-secondary);">模拟盘 (Demo)</span>
        </label>
      </div>
      <div style="background:var(--cq-bg-l2);border:1px solid var(--cq-border-default);border-radius:var(--cq-radius-lg);padding:var(--cq-space-3);margin-bottom:var(--cq-space-4);display:flex;gap:var(--cq-space-2);align-items:flex-start;">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="var(--cq-color-warning)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;margin-top:2px;"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>
        <div>
          <div style="font-size:var(--cq-text-xs);font-weight:600;color:var(--cq-color-warning);margin-bottom:2px;">安全提示</div>
          <div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);">API Key 和 Secret Key 会使用 AES-256 加密存储。我们不会以明文形式存储或传输您的密钥。</div>
        </div>
      </div>
      <button class="cq-btn cq-btn--primary cq-btn--full" onclick="submitAddAccount()">确认添加</button>
    </div>`;
  }

  // 账户卡片列表
  if (accounts.length > 0) {
    html += '<div style="display:flex;flex-direction:column;gap:var(--cq-space-3);">';
    for (const acc of accounts) {
      const meta = EXCHANGE_META[acc.exchange] || { label: acc.exchange, color: 'var(--cq-color-primary)', letter: acc.exchange[0]?.toUpperCase() || '?' };
      const badges = [];
      if (acc.is_testnet) badges.push('<span class="cq-tag cq-tag--neutral">测试网</span>');
      if (acc.is_demo) badges.push('<span class="cq-tag cq-tag--warn">模拟盘</span>');

      html += `
      <div class="cq-card account-card-inner" style="display:flex;align-items:center;justify-content:space-between;padding:var(--cq-space-4) var(--cq-space-5);">
        <div style="display:flex;align-items:center;gap:var(--cq-space-4);">
          <div style="width:44px;height:44px;border-radius:var(--cq-radius-lg);background:var(--cq-bg-l2);display:flex;align-items:center;justify-content:center;font-size:18px;font-weight:700;color:${meta.color};flex-shrink:0;border:1px solid var(--cq-border-default);">${meta.letter}</div>
          <div style="min-width:0;">
            <div style="font-weight:600;font-size:var(--cq-text-md);margin-bottom:var(--cq-space-1);color:var(--cq-text-primary);">${acc.account_name || meta.label}</div>
            <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);">${meta.label} · ${acc.exchange}</div>
            ${badges.length ? '<div style="margin-top:var(--cq-space-1);display:flex;gap:var(--cq-space-1);">' + badges.join('') + '</div>' : ''}
          </div>
        </div>
        <div class="account-card-actions" style="display:flex;align-items:center;gap:var(--cq-space-3);">
          <div style="text-align:right;">
            <div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);margin-bottom:2px;">余额</div>
            <div class="cq-num" style="font-weight:600;font-size:var(--cq-text-md);color:var(--cq-color-primary-hover);">${Number(acc.balance || 0).toFixed(4)} <span style="color:var(--cq-text-tertiary);font-size:var(--cq-text-xs);">USDT</span></div>
          </div>
          <button class="cq-btn cq-btn--danger cq-btn--sm" onclick="deleteAccount(${acc.id})">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="3 6 5 6 21 6"/><path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/></svg>
            删除
          </button>
        </div>
      </div>`;
    }
    html += '</div>';
  }

  container.innerHTML = html;
}

function toggleAddForm() {
  showAddForm = !showAddForm;
  renderAccounts();
}

async function submitAddAccount() {
  const exchange = document.getElementById('acc-exchange').value;
  const account_name = document.getElementById('acc-name').value.trim();
  const api_key = document.getElementById('acc-apikey').value.trim();
  const secret_key = document.getElementById('acc-secretkey').value.trim();
  const passphrase = document.getElementById('acc-passphrase').value.trim();
  const is_testnet = document.getElementById('acc-testnet').checked;
  const is_demo = document.getElementById('acc-demo').checked;

  if (!account_name || !api_key || !secret_key) {
    showToast('请填写必填字段', 'warn');
    return;
  }

  // OKX 必须提供 Passphrase
  if (exchange === 'okx' && !passphrase) {
    showToast('OKX 必须填写 Passphrase（创建 API Key 时设置的口令）', 'warn');
    return;
  }

  try {
    await api.createExchangeAccount({
      exchange,
      account_name: account_name || undefined,
      api_key,
      secret_key,
      passphrase: passphrase || undefined,
      is_testnet,
      is_demo,
    });
    showToast('账户添加成功', 'success');
    showAddForm = false;
    accounts = await api.getExchangeAccounts();
    renderAccounts();
  } catch (err) {
    showToast(err.message || '添加失败', 'error');
  }
}

async function deleteAccount(id) {
  if (!confirm('确定要删除这个交易所账户吗？')) return;
  try {
    await api.deleteExchangeAccount(id);
    showToast('账户已删除', 'success');
    accounts = await api.getExchangeAccounts();
    renderAccounts();
  } catch (err) {
    showToast(err.message || '删除失败', 'error');
  }
}
