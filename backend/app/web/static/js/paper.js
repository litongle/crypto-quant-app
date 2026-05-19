'use strict';

const paperState = {
  accounts: [],
};
let paperMountSelector = '#paper-content';

async function renderPaperPane(targetSelector = '#paper-content') {
  paperMountSelector = targetSelector;
  const container = document.querySelector(targetSelector);
  if (!container) return;
  container.innerHTML = '<div class="cq-skeleton" style="height:160px;"></div>';

  try {
    paperState.accounts = await api.getPaperAccounts();
  } catch (err) {
    paperState.accounts = [];
    showToast(err.message || '加载模拟盘账户失败', 'error');
  }

  renderPaperPage();
}

function renderPaperPage() {
  const container = document.querySelector(paperMountSelector);
  if (!container) return;

  const accounts = paperState.accounts || [];
  const header = `
    <div class="cq-card" style="margin-bottom:var(--cq-space-5);">
      <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:var(--cq-space-4);flex-wrap:wrap;">
        <div>
          <div style="font-size:var(--cq-text-lg);font-weight:600;color:var(--cq-text-primary);margin-bottom:var(--cq-space-1);">模拟盘账户管理</div>
          <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);line-height:1.6;">后端会为每个模拟盘账户分配虚拟资金和重置能力，适合联调策略和演练下单链路。</div>
        </div>
        <button class="cq-btn cq-btn--primary" onclick="createPaperAccount(this)" id="paper-create-btn">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          新建模拟盘账户
        </button>
      </div>
    </div>`;

  if (accounts.length === 0) {
    container.innerHTML = `${header}
      <div class="cq-card cq-empty-state">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="var(--cq-text-disabled)" stroke-width="1.5"><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/></svg>
        <h3>还没有模拟盘账户</h3>
        <p>创建后可用虚拟资金演练策略与交易流程。</p>
      </div>`;
    return;
  }

  container.innerHTML = `${header}
    <div style="display:flex;flex-direction:column;gap:var(--cq-space-3);">
      ${accounts.map((account) => `
        <div class="cq-card">
          <div style="display:flex;align-items:flex-start;justify-content:space-between;gap:var(--cq-space-4);flex-wrap:wrap;">
            <div>
              <div style="display:flex;align-items:center;gap:var(--cq-space-2);margin-bottom:var(--cq-space-2);">
                <span style="font-size:var(--cq-text-lg);font-weight:600;color:var(--cq-text-primary);">${escapeHtml(account.name || '模拟盘账户')}</span>
                <span class="cq-tag cq-tag--warn">模拟</span>
                ${account.isActive ? '<span class="cq-tag cq-tag--profit">启用中</span>' : '<span class="cq-tag cq-tag--neutral">已停用</span>'}
              </div>
              <div style="font-size:var(--cq-text-sm);color:var(--cq-text-tertiary);line-height:1.7;">
                账户 ID：<span class="cq-num">${account.id}</span><br>
                账户类型：<span class="cq-num">${escapeHtml(account.exchange === 'paper' || !account.exchange ? '模拟' : account.exchange)}</span>
              </div>
            </div>
            <div style="display:flex;align-items:center;gap:var(--cq-space-2);flex-wrap:wrap;">
              <button class="cq-btn cq-btn--secondary cq-btn--sm" onclick="refreshPaperAccounts()">刷新</button>
              <button class="cq-btn cq-btn--danger cq-btn--sm" data-account-id="${account.id}" data-account-name="${escapeHtml(account.name || '模拟盘账户')}" onclick="resetPaperAccountFromBtn(this)">重置账户</button>
            </div>
          </div>
        </div>`).join('')}
    </div>`;
}

async function createPaperAccount(btn) {
  // 防连点：快速双击会发多个请求，按钮 disabled 直到完成
  const targetBtn = btn || document.getElementById('paper-create-btn');
  if (targetBtn) targetBtn.disabled = true;
  try {
    await api.createPaperAccount();
    showToast('模拟盘账户已创建', 'success');
    await refreshPaperAccounts();
  } catch (err) {
    showToast(err.message || '创建模拟盘账户失败', 'error');
  } finally {
    // refreshPaperAccounts 会全量重建 DOM，btn 通常已被替换；这里给个兜底
    if (targetBtn && document.contains(targetBtn)) targetBtn.disabled = false;
  }
}

async function refreshPaperAccounts() {
  try {
    paperState.accounts = await api.getPaperAccounts();
    renderPaperPage();
  } catch (err) {
    showToast(err.message || '刷新模拟盘账户失败', 'error');
  }
}

function resetPaperAccountFromBtn(btn) {
  // 走 data-* 而非 inline 字符串参数：onclick 是 HTML attribute，浏览器会对其再解码一次，
  // 直接把 escapeHtml 后的 ' (&#39;) 还原成 '，撑破 JS 字符串字面量
  return resetPaperAccount(Number(btn.dataset.accountId), btn.dataset.accountName || '');
}

async function resetPaperAccount(accountId, accountName) {
  const confirmed = await confirmDangerous(
    `重置模拟盘：${accountName}`,
    '<p style="color:var(--cq-text-secondary);line-height:1.7;">重置会清空这个模拟盘账户的当前虚拟仓位与余额，并恢复到系统默认初始资金。</p>',
    { keyword: 'RESET', confirmLabel: '确认重置' }
  );
  if (!confirmed) return;

  try {
    await api.resetPaperAccount(accountId);
    showToast('模拟盘账户已重置', 'success');
    await refreshPaperAccounts();
  } catch (err) {
    showToast(err.message || '重置模拟盘账户失败', 'error');
  }
}
