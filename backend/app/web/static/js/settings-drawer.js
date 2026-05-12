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
  if (tab === 'notifications') {
    await renderNotificationsPane();
    return;
  }
  if (tab === 'smtp') {
    await renderSmtpPane();
    return;
  }
  if (tab === 'risk') {
    // T10 接管：仍走旧 runnerStatus 数据源
    settingsDrawerState.runnerStatus =
      settingsDrawerState.runnerStatus || (await api.getRunnerStatus().catch(() => null));
    renderRiskSettingsPane();
  }
}

// ── 通知通道（Telegram）────────────────────────────────────────

async function renderNotificationsPane() {
  const container = document.getElementById('settings-pane-notifications');
  if (!container) return;
  let data;
  try {
    data = await api.getNotificationsSettings();
  } catch (err) {
    container.innerHTML = `<p class="cq-settings-error">加载失败：${escapeHtml(err.message)}</p>`;
    return;
  }
  const tokenPh = data.telegram_bot_token_is_set ? '已设置（输入新值覆盖；输入 - 清空）' : '未设置';
  container.innerHTML = `
    <form class="cq-settings-form" data-form="notifications">
      <label>Telegram Bot Token
        <input type="password" name="telegram_bot_token" placeholder="${escapeHtml(tokenPh)}" autocomplete="off">
        <small>留空 = 不修改；输入 <code>-</code> = 清空；其他 = 覆盖</small>
      </label>
      <label>Telegram Chat ID
        <input type="text" name="telegram_chat_id" value="${escapeHtml(data.telegram_chat_id || '')}" autocomplete="off">
      </label>
      <div class="cq-settings-form__actions">
        <button type="submit">保存</button>
        <button type="button" data-action="test-telegram">发送测试通知</button>
      </div>
      <div class="cq-settings-form__status" data-status></div>
    </form>
  `;
  bindNotificationsForm(container);
}

function bindNotificationsForm(container) {
  const form = container.querySelector('form');
  const status = container.querySelector('[data-status]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const token = fd.get('telegram_bot_token');
    const chatId = fd.get('telegram_chat_id');
    const body = {
      telegram_bot_token: token === '' ? null : token === '-' ? '' : token,
      telegram_chat_id: chatId === '' ? null : chatId,
    };
    status.textContent = '保存中…';
    try {
      await api.putNotificationsSettings(body);
      status.textContent = '✅ 已保存（即时生效）';
      await renderNotificationsPane();
    } catch (err) {
      status.textContent = `❌ 保存失败：${err.message}`;
    }
  });
  container.querySelector('[data-action="test-telegram"]').addEventListener('click', async () => {
    status.textContent = '发送中…';
    try {
      await api.testNotification('telegram');
      status.textContent = '✅ 测试通知已发送，请检查 Telegram';
    } catch (err) {
      status.textContent = `❌ ${err.message}`;
    }
  });
}

// ── 邮箱 SMTP ────────────────────────────────────────────────

async function renderSmtpPane() {
  const container = document.getElementById('settings-pane-smtp');
  if (!container) return;
  let data;
  try {
    data = await api.getSmtpSettings();
  } catch (err) {
    container.innerHTML = `<p class="cq-settings-error">加载失败：${escapeHtml(err.message)}</p>`;
    return;
  }
  const passPh = data.smtp_password_is_set ? '已设置（输入新值覆盖；输入 - 清空）' : '未设置';
  container.innerHTML = `
    <form class="cq-settings-form" data-form="smtp">
      <label>SMTP Host
        <input name="smtp_host" value="${escapeHtml(data.smtp_host || '')}" placeholder="smtp.qq.com">
      </label>
      <label>端口
        <input name="smtp_port" type="number" value="${escapeHtml(String(data.smtp_port ?? 465))}" min="1" max="65535">
        <small>465 = SSL（推荐）；587 = STARTTLS</small>
      </label>
      <label>用户名
        <input name="smtp_username" value="${escapeHtml(data.smtp_username || '')}" placeholder="me@qq.com">
      </label>
      <label>密码（授权码，<b>不是登录密码</b>）
        <input name="smtp_password" type="password" placeholder="${escapeHtml(passPh)}" autocomplete="off">
        <small>留空 = 不修改；输入 <code>-</code> = 清空；其他 = 覆盖</small>
      </label>
      <label>发件人 From
        <input name="smtp_from" value="${escapeHtml(data.smtp_from || '')}" placeholder="留空则用用户名">
      </label>
      <label>收件人 To
        <input name="smtp_to" value="${escapeHtml(data.smtp_to || '')}" placeholder="me@example.com">
      </label>
      <label class="cq-checkbox">
        <input name="smtp_use_tls" type="checkbox" ${data.smtp_use_tls ? 'checked' : ''}>
        使用 SSL/TLS（465 勾选 / 587 不勾选）
      </label>
      <div class="cq-settings-form__actions">
        <button type="submit">保存</button>
        <button type="button" data-action="test-email">发送测试邮件</button>
      </div>
      <div class="cq-settings-form__status" data-status></div>
    </form>
  `;
  bindSmtpForm(container);
}

function bindSmtpForm(container) {
  const form = container.querySelector('form');
  const status = container.querySelector('[data-status]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    const fd = new FormData(form);
    const pw = fd.get('smtp_password');
    const body = {
      smtp_host: fd.get('smtp_host') || '',
      smtp_port: Number(fd.get('smtp_port')) || 465,
      smtp_username: fd.get('smtp_username') || '',
      smtp_password: pw === '' ? null : pw === '-' ? '' : pw,
      smtp_from: fd.get('smtp_from') || '',
      smtp_to: fd.get('smtp_to') || '',
      smtp_use_tls: form.querySelector('[name=smtp_use_tls]').checked,
    };
    status.textContent = '保存中…';
    try {
      await api.putSmtpSettings(body);
      status.textContent = '✅ 已保存（即时生效）';
      await renderSmtpPane();
    } catch (err) {
      status.textContent = `❌ 保存失败：${err.message}`;
    }
  });
  container.querySelector('[data-action="test-email"]').addEventListener('click', async () => {
    status.textContent = '发送中…';
    try {
      await api.testNotification('email');
      status.textContent = '✅ 测试邮件已发送，请检查收件箱（含垃圾箱）';
    } catch (err) {
      status.textContent = `❌ ${err.message}`;
    }
  });
}

// ── 风控参数（T10 会替换为表单）────────────────────────────────

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
