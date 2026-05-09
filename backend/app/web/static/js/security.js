const securityState = {
  status: null,
  setup: null,
  auditLogs: [],
  auditOffset: 0,
  auditLimit: 50,
  hasMore: false,
  filters: {
    action: '',
    resource: '',
  },
};
let securityMountSelector = '#security-content';

window._pending2faLogin = null;

function maskEmail(email) {
  const [name = '', domain = ''] = String(email || '').split('@');
  if (!name || !domain) return email || '--';
  if (name.length <= 2) return `${name[0]}*@${domain}`;
  return `${name.slice(0, 2)}***@${domain}`;
}

function showLogin2fa(email, password) {
  window._pending2faLogin = { email, password };
  document.getElementById('login-form').style.display = 'none';
  document.getElementById('register-form').style.display = 'none';
  document.getElementById('login-2fa-form').style.display = 'block';
  document.getElementById('login-2fa-email').textContent = maskEmail(email);
  document.getElementById('login-2fa-code').value = '';
  document.getElementById('login-2fa-code').focus();
}

function cancelLogin2fa(silent = false) {
  window._pending2faLogin = null;
  document.getElementById('login-2fa-form').style.display = 'none';
  document.getElementById('login-2fa-code').value = '';
  if (!silent) showLogin();
}

async function handleLogin2fa() {
  const pending = window._pending2faLogin;
  const code = document.getElementById('login-2fa-code').value.trim();
  if (!pending?.email || !pending?.password) {
    showToast('登录会话已失效，请重新输入账号密码', 'warn');
    cancelLogin2fa();
    return;
  }
  if (!/^\d{6}$/.test(code)) {
    showToast('请输入 6 位验证码', 'warn');
    return;
  }

  const btn = document.getElementById('login-2fa-btn');
  btn.disabled = true;
  btn.innerHTML = '<svg class="cq-spin" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12a9 9 0 1 1-6.22-8.56"/></svg> 验证中...';

  try {
    await api.login2fa(pending.email, pending.password, code);
    cancelLogin2fa(true);
    enterApp();
  } catch (err) {
    showToast(err.message || '2FA 登录失败', 'error');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l7 4v5c0 5-3.5 8.74-7 9-3.5-.26-7-4-7-9V7l7-4z"/><path d="M9 12l2 2 4-4"/></svg> 验证并登录';
  }
}

async function renderSecurityPane(targetSelector = '#security-content') {
  securityMountSelector = targetSelector;
  const container = document.querySelector(targetSelector);
  if (!container) return;
  container.innerHTML = '<div class="cq-skeleton" style="height:180px;margin-bottom:var(--cq-space-4);"></div><div class="cq-skeleton" style="height:220px;"></div>';

  await Promise.all([
    load2faStatus(true),
    loadAuditLogs({ reset: true, silent: true }),
  ]);

  renderSecurityPage();
}

async function load2faStatus(silent = false) {
  try {
    securityState.status = await api.get2faStatus();
  } catch (err) {
    securityState.status = null;
    if (!silent) showToast(err.message || '加载 2FA 状态失败', 'error');
  }
}

async function loadAuditLogs({ reset = false, silent = false } = {}) {
  try {
    if (reset) {
      securityState.auditOffset = 0;
      securityState.auditLogs = [];
    }
    const logs = await api.getAuditLogs({
      action: securityState.filters.action,
      resource: securityState.filters.resource,
      limit: securityState.auditLimit,
      offset: securityState.auditOffset,
    });
    securityState.auditLogs = reset ? logs : securityState.auditLogs.concat(logs);
    securityState.auditOffset += logs.length;
    securityState.hasMore = logs.length === securityState.auditLimit;
  } catch (err) {
    if (!silent) showToast(err.message || '加载审计日志失败', 'error');
  }
}

function renderSecurityPage() {
  const container = document.querySelector(securityMountSelector);
  if (!container) return;

  const status = securityState.status || { enabled: false, verified: false, has_2fa: false };
  const setup = securityState.setup;
  const twoFaBlock = setup
    ? `
      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:var(--cq-space-5);align-items:start;">
        <div class="cq-card cq-card--sm" style="text-align:center;">
          <div id="security-2fa-qr" style="display:flex;justify-content:center;min-height:180px;align-items:center;"></div>
          <div style="margin-top:var(--cq-space-3);font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);line-height:1.6;">使用身份验证器扫描二维码，或手动录入下面的密钥。</div>
        </div>
        <div class="cq-card cq-card--sm">
          <div style="font-size:var(--cq-text-md);font-weight:600;color:var(--cq-text-primary);margin-bottom:var(--cq-space-3);">完成绑定</div>
          <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);line-height:1.7;margin-bottom:var(--cq-space-3);">密钥：<span class="cq-num" style="word-break:break-all;color:var(--cq-text-primary);">${escapeHtml(setup.secret)}</span></div>
          <div style="margin-bottom:var(--cq-space-3);">
            <label class="cq-label">输入验证码启用 2FA</label>
            <input type="text" class="cq-input" id="security-2fa-verify-code" placeholder="输入 6 位验证码" maxlength="6" inputmode="numeric">
          </div>
          <div style="display:flex;gap:var(--cq-space-2);flex-wrap:wrap;">
            <button class="cq-btn cq-btn--primary" onclick="submit2faVerification()">验证并启用</button>
            <button class="cq-btn cq-btn--secondary" onclick="cancel2faSetup()">取消本次设置</button>
          </div>
        </div>
      </div>`
    : `
      <div class="cq-card cq-card--sm">
        <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:var(--cq-space-4);flex-wrap:wrap;">
          <div>
            <div style="display:flex;align-items:center;gap:var(--cq-space-2);margin-bottom:var(--cq-space-2);">
              <span style="font-size:var(--cq-text-lg);font-weight:600;color:var(--cq-text-primary);">双重验证状态</span>
              ${status.has_2fa ? '<span class="cq-tag cq-tag--profit">已启用</span>' : (status.enabled ? '<span class="cq-tag cq-tag--warn">待验证</span>' : '<span class="cq-tag cq-tag--neutral">未启用</span>')}
            </div>
            <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);line-height:1.7;">
              已生成密钥：${status.enabled ? '是' : '否'}<br>
              已完成验证：${status.verified ? '是' : '否'}
            </div>
          </div>
          <div style="display:flex;gap:var(--cq-space-2);flex-wrap:wrap;">
            ${status.has_2fa
              ? '<button class="cq-btn cq-btn--secondary" onclick="renderSecurityPage()">刷新状态</button>'
              : '<button class="cq-btn cq-btn--primary" onclick="start2faSetup()">开始设置 2FA</button>'}
          </div>
        </div>
        ${status.has_2fa ? `
          <div style="margin-top:var(--cq-space-4);padding-top:var(--cq-space-4);border-top:1px solid var(--cq-border-subtle);">
            <label class="cq-label">输入当前验证码以关闭 2FA</label>
            <div style="display:flex;gap:var(--cq-space-2);flex-wrap:wrap;">
              <input type="text" class="cq-input" id="security-2fa-disable-code" placeholder="输入 6 位验证码" maxlength="6" inputmode="numeric" style="max-width:220px;">
              <button class="cq-btn cq-btn--danger" onclick="submit2faDisable()">禁用 2FA</button>
            </div>
          </div>` : ''}
      </div>`;

  container.innerHTML = `
    <div style="display:flex;flex-direction:column;gap:var(--cq-space-5);">
      <section>
        <div class="cq-section-title" style="margin-bottom:var(--cq-space-3);">
          <h3>双重验证</h3>
        </div>
        ${twoFaBlock}
      </section>

      <section>
        <div class="cq-section-title" style="margin-bottom:var(--cq-space-3);">
          <h3>审计日志</h3>
        </div>
        <div class="cq-card">
          <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:var(--cq-space-3);margin-bottom:var(--cq-space-4);align-items:end;">
            <div>
              <label class="cq-label">操作类型</label>
              <input type="text" class="cq-input" id="audit-action-filter" placeholder="如 strategy_start" value="${escapeHtml(securityState.filters.action)}">
            </div>
            <div>
              <label class="cq-label">资源类型</label>
              <input type="text" class="cq-input" id="audit-resource-filter" placeholder="如 account / order" value="${escapeHtml(securityState.filters.resource)}">
            </div>
            <div style="font-size:var(--cq-text-xs);color:var(--cq-text-tertiary);line-height:1.7;padding-bottom:2px;">
              共加载 <span class="cq-num">${securityState.auditLogs.length}</span> 条记录
            </div>
            <div style="display:flex;justify-content:flex-end;">
              <button class="cq-btn cq-btn--secondary" onclick="applyAuditFilters()">查询</button>
            </div>
          </div>
          ${renderAuditTable()}
        </div>
      </section>
    </div>`;

  if (setup) {
    const qrEl = document.getElementById('security-2fa-qr');
    if (qrEl) {
      qrEl.innerHTML = '';
      new QRCode(qrEl, {
        text: setup.uri,
        width: 180,
        height: 180,
        colorDark: '#111827',
        colorLight: '#ffffff',
        correctLevel: QRCode.CorrectLevel.H,
      });
    }
  }
}

function renderAuditTable() {
  const logs = securityState.auditLogs || [];
  if (logs.length === 0) {
    return `
      <div class="cq-empty-state" style="padding:var(--cq-space-8) 0;">
        <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5"><path d="M9 12l2 2 4-4"/><path d="M12 3l7 4v5c0 5-3.5 8.74-7 9-3.5-.26-7-4-7-9V7l7-4z"/></svg>
        <h3>暂无审计记录</h3>
        <p>当前筛选条件下没有查到安全或操作日志。</p>
      </div>`;
  }

  return `
    <div class="cq-table-wrap">
      <table class="cq-table">
        <thead>
          <tr>
            <th>时间</th>
            <th>操作</th>
            <th>资源</th>
            <th>状态</th>
            <th>详情</th>
            <th>IP</th>
          </tr>
        </thead>
        <tbody>
          ${logs.map((log) => `
            <tr>
              <td>${escapeHtml(formatAuditTime(log.createdAt))}</td>
              <td><span class="cq-num">${escapeHtml(log.action || '--')}</span></td>
              <td>${escapeHtml(log.resource || '--')}${log.resourceId ? ` <span class="cq-num" style="color:var(--cq-text-tertiary);">#${log.resourceId}</span>` : ''}</td>
              <td>${renderAuditStatus(log.status)}</td>
              <td style="max-width:280px;white-space:normal;line-height:1.6;">${escapeHtml(log.detail || '--')}</td>
              <td class="cq-num">${escapeHtml(log.ipAddress || '--')}</td>
            </tr>`).join('')}
        </tbody>
      </table>
    </div>
    <div style="display:flex;justify-content:flex-end;margin-top:var(--cq-space-4);">
      ${securityState.hasMore ? '<button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="loadMoreAuditLogs()">加载更多</button>' : ''}
    </div>`;
}

function renderAuditStatus(status) {
  const normalized = String(status || 'success').toLowerCase();
  if (normalized === 'success') return '<span class="cq-tag cq-tag--profit">成功</span>';
  if (normalized === 'failure') return '<span class="cq-tag cq-tag--warn">失败</span>';
  return '<span class="cq-tag cq-tag--loss">异常</span>';
}

function formatAuditTime(value) {
  if (!value) return '--';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString('zh-CN', { hour12: false });
}

async function start2faSetup() {
  try {
    securityState.setup = await api.setup2fa();
    await load2faStatus(true);
    renderSecurityPage();
    showToast('请扫描二维码并输入验证码完成绑定', 'info');
  } catch (err) {
    showToast(err.message || '发起 2FA 设置失败', 'error');
  }
}

function cancel2faSetup() {
  securityState.setup = null;
  renderSecurityPage();
}

async function submit2faVerification() {
  const code = document.getElementById('security-2fa-verify-code')?.value.trim() || '';
  if (!/^\d{6}$/.test(code)) {
    showToast('请输入 6 位验证码', 'warn');
    return;
  }
  try {
    await api.verify2fa(code);
    securityState.setup = null;
    await load2faStatus(true);
    renderSecurityPage();
    showToast('2FA 已启用', 'success');
  } catch (err) {
    showToast(err.message || '验证 2FA 失败', 'error');
  }
}

async function submit2faDisable() {
  const code = document.getElementById('security-2fa-disable-code')?.value.trim() || '';
  if (!/^\d{6}$/.test(code)) {
    showToast('请输入 6 位验证码', 'warn');
    return;
  }
  try {
    await api.disable2fa(code);
    await load2faStatus(true);
    renderSecurityPage();
    showToast('2FA 已禁用', 'success');
  } catch (err) {
    showToast(err.message || '禁用 2FA 失败', 'error');
  }
}

async function applyAuditFilters() {
  securityState.filters.action = document.getElementById('audit-action-filter')?.value.trim() || '';
  securityState.filters.resource = document.getElementById('audit-resource-filter')?.value.trim() || '';
  await loadAuditLogs({ reset: true });
  renderSecurityPage();
}

async function loadMoreAuditLogs() {
  await loadAuditLogs();
  renderSecurityPage();
}
