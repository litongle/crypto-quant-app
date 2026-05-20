'use strict';

const settingsDrawerState = {
  activeTab: 'accounts',
  runnerStatus: null,
};

function openSettingsDrawer() {
  const drawer = document.getElementById('settings-drawer');
  if (!drawer) return;
  // 互斥：打开前先关其他抽屉，否则 UI 重叠（instance drawer 占右侧 + settings
  // 也占右侧）。ESC 处理已经按优先级关，open 时也守住同一规则
  if (typeof closeInstanceDrawer === 'function') closeInstanceDrawer();
  if (typeof closeInstanceLogsDrawer === 'function') closeInstanceLogsDrawer();
  drawer.hidden = false;
  document.body.classList.add('is-drawer-open');
  loadSettingsDrawerTab(settingsDrawerState.activeTab);
}

function closeSettingsDrawer() {
  const drawer = document.getElementById('settings-drawer');
  if (!drawer) return;
  drawer.hidden = true;
  document.body.classList.remove('is-drawer-open');
  // 释放所有 pane 渲染内容,防 DOM 累积。下次 open 时 loadSettingsDrawerTab
  // 会重新 render(本来就 fetch 最新设置,无副作用)。
  drawer.querySelectorAll('.cq-settings-pane').forEach((pane) => {
    pane.innerHTML = '';
  });
}

function switchSettingsTab(tab) {
  settingsDrawerState.activeTab = tab;
  document.querySelectorAll('.cq-drawer__tab[data-settings-tab]').forEach((button) => {
    button.classList.toggle('is-active', button.dataset.settingsTab === tab);
  });
  // 切 tab 不清空 pane innerHTML — 旧实现切走时清空，下次回来要重新 fetch
  // + 重 render，用户在 SMTP 输了一半切到 risk 再切回来，输入丢失（实测确认）。
  // 现在只 toggle hidden，pane DOM 节点+表单状态保留。要清空全部由
  // closeSettingsDrawer 完成（关 drawer 时清所有 panes，下次 open 拉新数据）。
  let needLoad = false;
  document.querySelectorAll('.cq-settings-pane').forEach((pane) => {
    const active = pane.dataset.settingsPane === tab;
    pane.hidden = !active;
    pane.classList.toggle('is-active', active);
    // active pane 第一次进入（空 innerHTML）才 load；之前进过保留状态
    if (active && pane.innerHTML.trim() === '') needLoad = true;
  });
  if (needLoad) loadSettingsDrawerTab(tab);
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
  if (tab === 'risk') {
    await renderRiskSettingsPane();
  }
}

// ── 通知通道（Telegram + 邮箱 SMTP）────────────────────────────

async function renderNotificationsPane() {
  const container = document.getElementById('settings-pane-notifications');
  if (!container) return;
  let tg, smtp;
  try {
    [tg, smtp] = await Promise.all([api.getNotificationsSettings(), api.getSmtpSettings()]);
  } catch (err) {
    container.innerHTML = `<p class="cq-settings-error">加载失败：${escapeHtml(err.message)}</p>`;
    return;
  }
  container.innerHTML = renderTelegramSection(tg) + renderSmtpSection(smtp);
  bindTelegramForm(container);
  bindSmtpForm(container);
}

function renderTelegramSection(data) {
  const tokenPh = data.telegram_bot_token_is_set ? '已设置（输入新值覆盖；输入 - 清空）' : '未设置';
  // 未配置 token 或 chat_id 时禁用「发送测试」按钮 + tooltip 说明,避免
  // 用户白点一次看到「token 未配置」error 再去填配置
  const tgReady = Boolean(data.telegram_bot_token_is_set) && Boolean(data.telegram_chat_id);
  const tgTestAttr = tgReady ? '' : 'disabled title="先填好 Bot Token + Chat ID 并保存后再测试"';
  return `
    <form class="cq-settings-form" data-form="telegram">
      <h3 class="cq-settings-section-title">Telegram</h3>
      <label>Telegram Bot Token
        <input type="password" name="telegram_bot_token" placeholder="${escapeHtml(tokenPh)}" autocomplete="off">
        <small>留空 = 不修改；输入 <code>-</code> = 清空；其他 = 覆盖</small>
      </label>
      <label>Telegram Chat ID
        <input type="text" name="telegram_chat_id" value="${escapeHtml(data.telegram_chat_id || '')}" autocomplete="off">
      </label>
      <div class="cq-settings-form__actions">
        <button type="submit" class="cq-btn cq-btn--primary">保存</button>
        <button type="button" class="cq-btn cq-btn--secondary" data-action="test-telegram" ${tgTestAttr}>发送测试通知</button>
      </div>
      <div class="cq-settings-form__status" data-status></div>
    </form>
  `;
}

function renderSmtpSection(data) {
  const passPh = data.smtp_password_is_set ? '已设置（输入新值覆盖；输入 - 清空）' : '未设置';
  // 未配置 SMTP host/username/password/收件人时禁用「发送测试邮件」
  const smtpReady = Boolean(data.smtp_host) && Boolean(data.smtp_username) && Boolean(data.smtp_password_is_set) && Boolean(data.smtp_to);
  const smtpTestAttr = smtpReady ? '' : 'disabled title="先填好 Host / 用户名 / 密码 / 收件人并保存后再测试"';
  return `
    <form class="cq-settings-form" data-form="smtp">
      <h3 class="cq-settings-section-title cq-settings-section-title--divider">邮箱 SMTP</h3>
      <div class="cq-settings-form__group">
        <div class="cq-settings-form__group-title">服务器</div>
        <label>SMTP Host
          <input name="smtp_host" value="${escapeHtml(data.smtp_host || '')}" placeholder="smtp.qq.com">
        </label>
        <label>端口
          <input name="smtp_port" type="number" value="${escapeHtml(String(data.smtp_port ?? 465))}" min="1" max="65535">
          <small>465 = SSL（推荐）；587 = STARTTLS</small>
        </label>
        <label class="cq-checkbox">
          <input name="smtp_use_tls" type="checkbox" ${data.smtp_use_tls ? 'checked' : ''}>
          使用 SSL/TLS（465 勾选 / 587 不勾选）
        </label>
      </div>

      <div class="cq-settings-form__group">
        <div class="cq-settings-form__group-title">认证</div>
        <label>用户名
          <input name="smtp_username" value="${escapeHtml(data.smtp_username || '')}" placeholder="me@qq.com">
        </label>
        <label>密码 / 授权码
          <input name="smtp_password" type="password" placeholder="${escapeHtml(passPh)}" autocomplete="off">
          <small>不是登录密码。留空 = 不修改；输入 <code>-</code> = 清空；其他 = 覆盖</small>
        </label>
      </div>

      <div class="cq-settings-form__group">
        <div class="cq-settings-form__group-title">收发</div>
        <label>发件人地址
          <input name="smtp_from" value="${escapeHtml(data.smtp_from || '')}" placeholder="留空则用用户名">
        </label>
        <label>收件人地址
          <input name="smtp_to" value="${escapeHtml(data.smtp_to || '')}" placeholder="me@example.com">
        </label>
      </div>

      <div class="cq-settings-form__actions">
        <button type="submit" class="cq-btn cq-btn--primary">保存</button>
        <button type="button" class="cq-btn cq-btn--secondary" data-action="test-email" ${smtpTestAttr}>发送测试邮件</button>
      </div>
      <div class="cq-settings-form__status" data-status></div>
    </form>
  `;
}

function bindTelegramForm(container) {
  const form = container.querySelector('form[data-form="telegram"]');
  const status = form.querySelector('[data-status]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    // 先跑浏览器 native 校验 — 否则用户输入超长/格式不合规也会直接打后端
    if (!form.reportValidity()) return;
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
  form.querySelector('[data-action="test-telegram"]').addEventListener('click', async (e) => {
    // 防连点：测试通知会真发到 Telegram,连点会刷屏
    const btn = e.currentTarget;
    btn.disabled = true;
    status.textContent = '发送中…';
    try {
      await api.testNotification('telegram');
      status.textContent = '✅ 测试通知已发送，请检查 Telegram';
    } catch (err) {
      status.textContent = `❌ ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  });
}

function bindSmtpForm(container) {
  const form = container.querySelector('form[data-form="smtp"]');
  const status = form.querySelector('[data-status]');

  // port 与 use_tls 联动：465 = SSL（勾选）；587 = STARTTLS（不勾）。
  // 用户改 port 时自动同步 checkbox，避免「改了 port 忘改 TLS 导致连不上」
  const portEl = form.querySelector('input[name="smtp_port"]');
  const tlsEl = form.querySelector('input[name="smtp_use_tls"]');
  if (portEl && tlsEl) {
    portEl.addEventListener('change', () => {
      const port = Number(portEl.value);
      if (port === 465) tlsEl.checked = true;
      else if (port === 587) tlsEl.checked = false;
      // 其他端口保留用户当前选择
    });
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!form.reportValidity()) return;
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
      await renderNotificationsPane();
    } catch (err) {
      status.textContent = `❌ 保存失败：${err.message}`;
    }
  });
  form.querySelector('[data-action="test-email"]').addEventListener('click', async (e) => {
    // 防连点：测试邮件会真发，连点会刷垃圾箱
    const btn = e.currentTarget;
    btn.disabled = true;
    status.textContent = '发送中…';
    try {
      await api.testNotification('email');
      status.textContent = '✅ 测试邮件已发送，请检查收件箱（含垃圾箱）';
    } catch (err) {
      status.textContent = `❌ ${err.message}`;
    } finally {
      btn.disabled = false;
    }
  });
}

// ── 风控参数 ──────────────────────────────────────────────────

async function renderRiskSettingsPane() {
  const container = document.getElementById('settings-pane-risk');
  if (!container) return;
  let data;
  try {
    data = await api.getRiskSettings();
  } catch (err) {
    container.innerHTML = `<p class="cq-settings-error">加载失败：${escapeHtml(err.message)}</p>`;
    return;
  }
  container.innerHTML = `
    <form class="cq-settings-form" data-form="risk">
      <label>连续异常阈值
        <input name="consecutive_errors" type="number" value="${data.consecutive_errors}" min="1" max="100">
        <small>策略循环连续抛错多少次后自停（防卡死）</small>
      </label>
      <label>连续下单失败阈值
        <input name="consecutive_order_failures" type="number" value="${data.consecutive_order_failures}" min="1" max="100">
        <small>同一实例下单连续失败多少次后自停</small>
      </label>
      <label>心跳倍数
        <input name="heartbeat_multiplier" type="number" value="${data.heartbeat_multiplier}" min="1" max="100">
        <small>心跳超时阈值 = poll_interval × 这个倍数，与「最小心跳秒数」取较大</small>
      </label>
      <label>最小心跳秒数
        <input name="heartbeat_min_seconds" type="number" value="${data.heartbeat_min_seconds}" min="10" max="3600">
        <small>心跳超时阈值的下限秒数</small>
      </label>
      <label>守护扫描间隔（秒）
        <input name="watchdog_interval_seconds" type="number" value="${data.watchdog_interval_seconds}" min="5" max="600">
        <small>守护扫描周期，越短发现卡死越快</small>
      </label>
      <div class="cq-settings-form__actions">
        <button type="submit" class="cq-btn cq-btn--primary">保存</button>
      </div>
      <div class="cq-settings-form__status" data-status></div>
    </form>
  `;
  bindRiskForm(container);
}

function bindRiskForm(container) {
  const form = container.querySelector('form');
  const status = container.querySelector('[data-status]');
  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    // 风控参数都是 number + min/max 限制；submit 前先跑 native 校验避免
    // 越界值打到后端再失败（之前用户填 99999 才看到「需 ≤ 3600」提示）
    if (!form.reportValidity()) return;
    const fd = new FormData(form);
    const body = {
      consecutive_errors: Number(fd.get('consecutive_errors')),
      consecutive_order_failures: Number(fd.get('consecutive_order_failures')),
      heartbeat_multiplier: Number(fd.get('heartbeat_multiplier')),
      heartbeat_min_seconds: Number(fd.get('heartbeat_min_seconds')),
      watchdog_interval_seconds: Number(fd.get('watchdog_interval_seconds')),
    };
    status.textContent = '保存中…';
    try {
      await api.putRiskSettings(body);
      status.textContent = '✅ 已保存（下次守护周期生效）';
    } catch (err) {
      status.textContent = `❌ 保存失败：${err.message}`;
    }
  });
}
