const settingsDrawerState = {
  activeTab: 'accounts',
  runnerStatus: null,
};

function openSettingsDrawer() {
  const drawer = document.getElementById('settings-drawer');
  if (!drawer) return;
  drawer.hidden = false;
  document.body.classList.add('is-drawer-open');
  loadSettingsDrawerTab(settingsDrawerState.activeTab);
}

function closeSettingsDrawer() {
  const drawer = document.getElementById('settings-drawer');
  if (!drawer) return;
  drawer.hidden = true;
  document.body.classList.remove('is-drawer-open');
}

function switchSettingsTab(tab) {
  settingsDrawerState.activeTab = tab;
  document.querySelectorAll('.cq-drawer__tab[data-settings-tab]').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.settingsTab === tab);
  });
  document.querySelectorAll('.cq-settings-pane').forEach((pane) => {
    const active = pane.dataset.settingsPane === tab;
    pane.hidden = !active;
    pane.classList.toggle('is-active', active);
  });
  loadSettingsDrawerTab(tab);
}

async function loadSettingsDrawerTab(tab) {
  if (tab === 'accounts') {
    await renderAccountsPane('#settings-pane-accounts');
    return;
  }
  if (tab === 'paper') {
    await renderPaperPane('#settings-pane-paper');
    return;
  }
  if (tab === 'security') {
    await renderSecurityPane('#settings-pane-security');
    return;
  }

  settingsDrawerState.runnerStatus = settingsDrawerState.runnerStatus || await api.getRunnerStatus().catch(() => null);
  if (tab === 'notifications') {
    renderNotificationsPane();
  } else if (tab === 'risk') {
    renderRiskSettingsPane();
  }
}

function renderNotificationsPane() {
  const container = document.getElementById('settings-pane-notifications');
  if (!container) return;
  const notifications = settingsDrawerState.runnerStatus?.settings?.notifications || {};
  container.innerHTML = `
    <div class="cq-settings-readonly">
      <div class="cq-settings-readonly__item"><span>Telegram Bot Token</span><strong>${notifications.telegram_bot_token_configured ? '已配置' : '未配置'}</strong></div>
      <div class="cq-settings-readonly__item"><span>Telegram Chat ID</span><strong>${notifications.telegram_chat_id_configured ? '已配置' : '未配置'}</strong></div>
      <p>请编辑 <code>backend/.env</code> 后重启服务使修改生效。</p>
    </div>
  `;
}

function renderRiskSettingsPane() {
  const container = document.getElementById('settings-pane-risk');
  if (!container) return;
  const risk = settingsDrawerState.runnerStatus?.settings?.auto_pause || {};
  container.innerHTML = `
    <div class="cq-settings-readonly">
      <div class="cq-settings-readonly__item"><span>连续异常阈值</span><strong>${escapeHtml(risk.consecutive_errors ?? '--')}</strong></div>
      <div class="cq-settings-readonly__item"><span>连续下单失败阈值</span><strong>${escapeHtml(risk.consecutive_order_failures ?? '--')}</strong></div>
      <div class="cq-settings-readonly__item"><span>心跳倍数阈值</span><strong>${escapeHtml(risk.heartbeat_multiplier ?? '--')}</strong></div>
      <div class="cq-settings-readonly__item"><span>最小心跳秒数</span><strong>${escapeHtml(risk.heartbeat_min_seconds ?? '--')}</strong></div>
      <div class="cq-settings-readonly__item"><span>Watchdog 间隔</span><strong>${escapeHtml(risk.watchdog_interval_seconds ?? '--')}</strong></div>
      <p>当前版本仅展示配置值。修改请编辑 <code>backend/.env</code> 并重启。</p>
    </div>
  `;
}
