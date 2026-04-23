/**
 * 策略中心页面逻辑
 */
let selectedTemplateId = null;

async function loadStrategyPage() {
  const container = document.getElementById('strategy-content');
  container.innerHTML = '<div class="skeleton" style="height:120px;margin-bottom:16px;"></div><div class="skeleton" style="height:80px;"></div>';

  try {
    const [templates, instances] = await Promise.all([
      api.getStrategyTemplates().catch(() => []),
      api.getStrategyInstances().catch(() => []),
    ]);

    renderTemplateList(templates);
    renderInstanceList(instances);
  } catch (err) {
    container.innerHTML = `<div class="card" style="text-align:center;padding:40px;"><div style="font-size:36px;margin-bottom:12px;">📊</div><div style="color:#64748b;">${err.message}</div></div>`;
  }
}

function renderTemplateList(templates) {
  const el = document.getElementById('template-list');
  if (!templates || templates.length === 0) {
    el.innerHTML = '<div class="card" style="text-align:center;padding:24px;color:#64748b;">暂无策略模板</div>';
    return;
  }

  el.innerHTML = templates.map(t => `
    <div class="card strategy-card" id="tmpl-${t.id}" onclick="selectTemplate('${t.id}')" style="margin-bottom:10px;">
      <div class="strategy-icon">${t.icon || '📊'}</div>
      <div style="flex:1;">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
          <span style="font-size:14px;font-weight:700;color:#f8fafc;">${t.name}</span>
          <span class="tag tag-cyan" style="font-size:10px;">模板</span>
        </div>
        <div style="font-size:12px;color:#64748b;">${t.description}</div>
      </div>
      <div style="font-size:18px;color:#374151;" id="check-${t.id}">○</div>
    </div>
  `).join('');
}

function renderInstanceList(instances) {
  const el = document.getElementById('instance-list');
  if (!instances || instances.length === 0) {
    el.innerHTML = '<div class="card" style="text-align:center;padding:24px;color:#64748b;">暂无运行中的策略实例</div>';
    return;
  }

  el.innerHTML = instances.map(inst => `
    <div class="card" style="margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;">
        <div>
          <div style="display:flex;align-items:center;gap:8px;margin-bottom:4px;">
            <span style="font-size:14px;font-weight:700;color:#f8fafc;">${inst.name}</span>
            <span class="tag ${inst.status === 'running' ? 'tag-green' : inst.status === 'paused' ? 'tag-yellow' : 'tag-red'}">${inst.status === 'running' ? '运行中' : inst.status === 'paused' ? '已暂停' : '已停止'}</span>
          </div>
          <div style="font-size:12px;color:#64748b;">${inst.templateName} · ${inst.totalTrades} 笔交易</div>
        </div>
        <div style="text-align:right;">
          <div style="font-size:14px;font-weight:700;color:${inst.totalPnl >= 0 ? '#22c55e' : '#ef4444'};">${inst.totalPnl >= 0 ? '+' : ''}$${inst.totalPnl.toFixed(2)}</div>
          <div style="font-size:11px;color:#64748b;">${inst.winRate.toFixed(1)}% 胜率</div>
        </div>
      </div>
      <div style="display:flex;gap:8px;margin-top:12px;">
        ${inst.status !== 'running'
          ? `<button class="btn-secondary" style="font-size:11px;padding:6px 14px;" onclick="toggleStrategy('${inst.id}', 'start')">▶ 启动</button>`
          : `<button class="btn-secondary" style="font-size:11px;padding:6px 14px;" onclick="toggleStrategy('${inst.id}', 'stop')">⏹ 停止</button>`
        }
        <button class="btn-secondary" style="font-size:11px;padding:6px 14px;color:#ef4444;border-color:#7f1d1d;" onclick="deleteStrategyInst('${inst.id}')">🗑 删除</button>
      </div>
    </div>
  `).join('');
}

async function selectTemplate(id) {
  selectedTemplateId = id;
  document.querySelectorAll('.strategy-card').forEach(c => {
    c.classList.remove('selected');
    const checkEl = c.querySelector('[id^="check-"]');
    if (checkEl) { checkEl.textContent = '○'; checkEl.style.color = '#374151'; }
  });
  const card = document.getElementById('tmpl-' + id);
  if (card) card.classList.add('selected');
  const check = document.getElementById('check-' + id);
  if (check) { check.textContent = '✓'; check.style.color = '#22d3ee'; }

  // 显示创建表单
  document.getElementById('create-section').style.display = 'block';

  // 获取模板参数并渲染
  try {
    const templates = await api.getStrategyTemplates();
    const tmpl = templates.find(t => t.id === id);
    if (tmpl && tmpl.params) renderParamSliders(tmpl.params);
  } catch {}
}

function renderParamSliders(params) {
  const el = document.getElementById('param-sliders');
  if (!params || params.length === 0) {
    el.innerHTML = '<div style="font-size:12px;color:#64748b;">此策略无需配置参数</div>';
    return;
  }

  el.innerHTML = params.map(p => `
    <div style="margin-bottom:16px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
        <label style="font-size:13px;font-weight:600;color:#e2e8f0;">${p.name}</label>
        <span style="font-size:13px;font-weight:700;color:#22d3ee;" id="val-${p.key}">${p.default}</span>
      </div>
      <input type="range" class="slider-track" id="sl-${p.key}" min="${p.min || 0}" max="${p.max || 100}" value="${p.default}" step="${p.step || 1}"
        oninput="document.getElementById('val-${p.key}').textContent=this.value">
    </div>
  `).join('');
}

async function createStrategyInstance() {
  if (!selectedTemplateId) { showToast('⚠️ 请先选择策略模板'); return; }

  const name = document.getElementById('new-strategy-name').value.trim();
  if (!name) { showToast('⚠️ 请输入策略名称'); return; }

  const exchange = document.getElementById('new-strategy-exchange').value;
  const symbol = document.getElementById('new-strategy-symbol').value.trim() || 'BTCUSDT';

  // 收集参数
  const params = {};
  document.querySelectorAll('#param-sliders input[type="range"]').forEach(sl => {
    const key = sl.id.replace('sl-', '');
    params[key] = parseFloat(sl.value);
  });

  try {
    await api.createStrategyInstance({
      name,
      templateId: selectedTemplateId,
      exchange,
      symbol,
      params,
    });
    showToast('✅ 策略创建成功！');
    loadStrategyPage();
  } catch (err) {
    showToast('❌ 创建失败: ' + err.message);
  }
}

async function toggleStrategy(instanceId, action) {
  try {
    if (action === 'start') await api.startStrategy(instanceId);
    else await api.stopStrategy(instanceId);
    showToast(`✅ 策略已${action === 'start' ? '启动' : '停止'}`);
    loadStrategyPage();
  } catch (err) {
    showToast('❌ 操作失败: ' + err.message);
  }
}

async function deleteStrategyInst(instanceId) {
  if (!confirm('确认删除此策略？此操作不可撤销。')) return;
  try {
    await api.deleteStrategy(instanceId);
    showToast('✅ 策略已删除');
    loadStrategyPage();
  } catch (err) {
    showToast('❌ 删除失败: ' + err.message);
  }
}
