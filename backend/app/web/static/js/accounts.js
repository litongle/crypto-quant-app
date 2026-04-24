/**
 * 交易所账户管理页面逻辑
 */
let accounts = [];
let showAddForm = false;

async function loadAccountsPage() {
  const container = document.getElementById('accounts-content');
  container.innerHTML = '<div class="skeleton" style="height:120px;margin-bottom:16px;"></div><div class="skeleton" style="height:80px;"></div>';

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
      <div class="card" style="text-align:center;padding:60px 24px;">
        <div style="font-size:48px;margin-bottom:16px;">🔐</div>
        <div style="font-size:15px;font-weight:600;margin-bottom:8px;">还没有添加交易所账户</div>
        <div style="font-size:13px;color:#64748b;margin-bottom:24px;">添加 Binance / OKX / HTX 账户以开始交易</div>
        <button class="btn-primary" onclick="toggleAddForm()">+ 添加交易所账户</button>
      </div>
    `;
    return;
  }

  // 账户列表
  let html = `<div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
    <div style="font-size:14px;font-weight:700;">已添加的交易所账户 (${accounts.length})</div>
    <button class="btn-secondary" style="padding:6px 14px;font-size:12px;" onclick="toggleAddForm()">${showAddForm ? '取消' : '+ 添加账户'}</button>
  </div>`;

  // 添加表单
  if (showAddForm) {
    html += `
    <div class="card" style="margin-bottom:20px;">
      <div style="font-size:13px;font-weight:700;margin-bottom:16px;">添加新账户</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;">
        <div>
          <div style="font-size:11px;color:#64748b;margin-bottom:4px;">交易所</div>
          <select class="input-field" id="acc-exchange">
            <option value="binance">Binance</option>
            <option value="okx">OKX</option>
            <option value="huobi">HTX (火币)</option>
          </select>
        </div>
        <div>
          <div style="font-size:11px;color:#64748b;margin-bottom:4px;">账户别名</div>
          <input type="text" class="input-field" id="acc-name" placeholder="我的BN账户">
        </div>
      </div>
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">API Key</div>
        <input type="text" class="input-field" id="acc-apikey" placeholder="输入 API Key">
      </div>
      <div style="margin-bottom:12px;">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Secret Key</div>
        <input type="password" class="input-field" id="acc-secretkey" placeholder="输入 Secret Key">
      </div>
      <div style="margin-bottom:12px;" id="passphrase-field">
        <div style="font-size:11px;color:#64748b;margin-bottom:4px;">Passphrase <span style="color:#475569;">(OKX 必须，其他可不填)</span></div>
        <input type="password" class="input-field" id="acc-passphrase" placeholder="输入 Passphrase">
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px;">
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
          <input type="checkbox" id="acc-testnet" style="width:16px;height:16px;">
          <span style="font-size:12px;color:#94a3b8;">测试网 (Testnet)</span>
        </label>
        <label style="display:flex;align-items:center;gap:8px;cursor:pointer;">
          <input type="checkbox" id="acc-demo" style="width:16px;height:16px;">
          <span style="font-size:12px;color:#94a3b8;">模拟盘 (Demo)</span>
        </label>
      </div>
      <div style="background:#0f172a;border:1px solid #1e293b;border-radius:8px;padding:12px;margin-bottom:16px;">
        <div style="font-size:11px;color:#f59e0b;font-weight:600;margin-bottom:4px;">⚠️ 安全提示</div>
        <div style="font-size:11px;color:#64748b;">API Key 和 Secret Key 会使用 AES-256 加密存储。我们不会以明文形式存储或传输您的密钥。</div>
      </div>
      <button class="btn-primary" style="width:100%;" onclick="submitAddAccount()">确认添加</button>
    </div>`;
  }

  // 账户卡片列表
  if (accounts.length > 0) {
    html += '<div style="display:flex;flex-direction:column;gap:12px;">';
    for (const acc of accounts) {
      const exchangeLabels = { binance: 'Binance', okx: 'OKX', huobi: 'HTX' };
      const exchangeColors = { binance: '#f0b90b', okx: '#ffffff', huobi: '#4573e3' };
      const color = exchangeColors[acc.exchange] || '#22d3ee';
      const label = exchangeLabels[acc.exchange] || acc.exchange;
      const badges = [];
      if (acc.is_testnet) badges.push('<span style="background:#1e293b;color:#94a3b8;padding:2px 8px;border-radius:4px;font-size:10px;">测试网</span>');
      if (acc.is_demo) badges.push('<span style="background:#1e293b;color:#f59e0b;padding:2px 8px;border-radius:4px;font-size:10px;">模拟盘</span>');

      html += `
      <div class="card account-card-inner" style="display:flex;align-items:center;justify-content:space-between;padding:16px 20px;">
        <div style="display:flex;align-items:center;gap:16px;">
          <div style="width:44px;height:44px;border-radius:50%;background:#1e293b;display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;color:${color};flex-shrink:0;">${label[0]}</div>
          <div>
            <div style="font-weight:600;font-size:14px;margin-bottom:4px;">${acc.account_name || label}</div>
            <div style="font-size:12px;color:#64748b;">${label} · ${acc.exchange}</div>
            <div style="margin-top:6px;">${badges.join(' ')}</div>
          </div>
        </div>
        <div class="account-card-actions" style="display:flex;align-items:center;gap:12px;">
          <div style="text-align:right;">
            <div style="font-size:11px;color:#64748b;margin-bottom:2px;">余额</div>
            <div style="font-weight:700;font-size:14px;color:#22d3ee;">${Number(acc.balance || 0).toFixed(4)} <span style="color:#64748b;font-size:11px;">USDT</span></div>
          </div>
          <button class="btn-danger" style="padding:6px 12px;font-size:12px;white-space:nowrap;" onclick="deleteAccount(${acc.id})">删除</button>
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
    showToast('⚠️ 请填写必填字段');
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
    showToast('✅ 账户添加成功');
    showAddForm = false;
    accounts = await api.getExchangeAccounts();
    renderAccounts();
  } catch (err) {
    showToast('❌ ' + (err.message || '添加失败'));
  }
}

async function deleteAccount(id) {
  if (!confirm('确定要删除这个交易所账户吗？')) return;
  try {
    await api.deleteExchangeAccount(id);
    showToast('✅ 账户已删除');
    accounts = await api.getExchangeAccounts();
    renderAccounts();
  } catch (err) {
    showToast('❌ ' + (err.message || '删除失败'));
  }
}
