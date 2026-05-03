# 策略中心重构实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:subagent-driven-development（推荐）或 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将当前策略中心重构为“运行台 / 策略仓库 / 工作台”的一致产品结构，并让前后端状态流与文案语义保持一致。

**架构：** 后端先补齐策略生命周期字段与视图模型，把“运行中”“仓库态”“工作台草案态”拆清；前端再将当前单页模板区和实例列表改为三段式布局，并将运行中策略编辑改为“复制为草案到工作台”。整个重构优先保留现有 API 能力，在必要处追加轻量字段和新接口，避免一次性推翻现有回测、绩效、运行器逻辑。

**技术栈：** FastAPI、SQLAlchemy、原生 JS、静态 HTML/CSS、pytest、Node 语法校验

---

## 文件结构

### 后端

- 修改：`backend/app/models/strategy.py`
  - 为策略实例补充“最近启动时间”“最近停止时间”“来源策略ID / 草案来源”这类状态追踪字段，支撑运行时长和“编辑副本”语义
- 修改：`backend/app/api/v1/strategies.py`
  - 调整策略中心读模型输出；新增运行台/策略仓库/工作台所需的分组字段或轻量接口
- 修改：`backend/app/services/strategy_service.py`
  - 明确“保存到仓库”“启动进入运行台”“停止回仓库”“从运行中复制草案到工作台”的服务语义
- 修改：`backend/app/repositories/strategy_repo.py`
  - 提供按状态分组、按最近启动时间排序、复制实例等仓储方法
- 测试：`backend/tests/test_strategy_center_flow.py`
  - 新增策略中心状态流测试

### 前端

- 修改：`backend/app/web/static/index.html`
  - 重排策略中心结构，拆成运行台、策略仓库、工作台三区
- 修改：`backend/app/web/static/js/api.js`
  - 增加运行台、策略仓库过滤和“复制为草案”接口封装
- 修改：`backend/app/web/static/js/strategy.js`
  - 重写页面加载、三区渲染、工作台编辑态、运行中编辑复制草案逻辑
- 修改：`backend/app/web/static/css/app.css`
  - 新增运行台摘要卡、仓库表格、工作台分栏样式
- 测试：`backend/app/web/static/js/strategy.js` 通过 Node 语法校验

### 文档

- 已存在：`docs/superpowers/specs/2026-05-03-strategy-center-design.md`
  - 实现时必须对照该规格逐项完成

---

### 任务 1：补齐策略生命周期字段与仓储能力

**文件：**
- 修改：`backend/app/models/strategy.py`
- 修改：`backend/app/repositories/strategy_repo.py`
- 测试：`backend/tests/test_strategy_center_flow.py`

- [ ] **步骤 1：编写失败的后端状态流测试**

```python
def test_stopped_strategy_returns_to_library_state():
    instance = make_strategy_instance(status="running")
    service.stop_instance(instance.id, user_id=instance.user_id)
    refreshed = repo.get_by_id(instance.id)
    assert refreshed.status == "stopped"
    assert refreshed.last_started_at is not None
    assert refreshed.last_stopped_at is not None


def test_clone_running_strategy_creates_draft_copy():
    running = make_strategy_instance(status="running", name="BTC 趋势跟踪")
    draft = service.clone_to_draft(running.id, user_id=running.user_id)
    assert draft.id != running.id
    assert draft.status == "draft"
    assert draft.source_instance_id == running.id
    assert draft.name.endswith("副本")
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest backend/tests/test_strategy_center_flow.py -v`
预期：FAIL，报错缺少 `last_started_at`、`last_stopped_at` 或 `clone_to_draft`

- [ ] **步骤 3：在模型中添加生命周期字段**

```python
last_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
last_stopped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
source_instance_id: Mapped[int | None] = mapped_column(ForeignKey("strategy_instances.id"), default=None)
workspace_state: Mapped[str] = mapped_column(
    Enum("draft", "library", "running", name="strategy_workspace_state"),
    default="library",
)
```

- [ ] **步骤 4：在仓储层增加复制与排序能力**

```python
async def clone_instance_to_draft(self, instance: StrategyInstance) -> StrategyInstance:
    draft = StrategyInstance(
        user_id=instance.user_id,
        template_id=instance.template_id,
        name=f"{instance.name} 副本",
        symbol=instance.symbol,
        exchange=instance.exchange,
        direction=instance.direction,
        params=copy.deepcopy(instance.params or {}),
        risk_params=copy.deepcopy(instance.risk_params or {}),
        account_id=instance.account_id,
        status="draft",
        workspace_state="draft",
        source_instance_id=instance.id,
    )
    self.session.add(draft)
    await self.session.flush()
    return draft
```

- [ ] **步骤 5：运行测试验证通过**

运行：`pytest backend/tests/test_strategy_center_flow.py -v`
预期：PASS

- [ ] **步骤 6：Commit**

```bash
git add backend/app/models/strategy.py backend/app/repositories/strategy_repo.py backend/tests/test_strategy_center_flow.py
git commit -m "feat: add strategy lifecycle fields"
```

### 任务 2：重构策略服务语义为运行台 / 仓库 / 工作台

**文件：**
- 修改：`backend/app/services/strategy_service.py`
- 修改：`backend/app/api/v1/strategies.py`
- 测试：`backend/tests/test_strategy_center_flow.py`

- [ ] **步骤 1：编写失败的接口级测试**

```python
def test_create_strategy_from_workbench_enters_library(client, auth_headers):
    payload = {
        "name": "RSI 分层试验 A",
        "templateId": "rule_custom",
        "exchange": "binance",
        "symbol": "BTCUSDT",
        "params": {"rules": {"buy": [], "sell": []}},
    }
    resp = client.post("/api/v1/strategies/instances", json=payload, headers=auth_headers)
    body = resp.json()["data"]
    assert body["status"] == "draft"
    assert body["workspaceState"] == "library"


def test_running_edit_creates_workbench_draft(client, auth_headers, running_instance):
    resp = client.post(f"/api/v1/strategies/instances/{running_instance.id}/clone-draft", headers=auth_headers)
    body = resp.json()["data"]
    assert body["status"] == "draft"
    assert body["workspaceState"] == "draft"
```

- [ ] **步骤 2：运行测试验证失败**

运行：`pytest backend/tests/test_strategy_center_flow.py -v`
预期：FAIL，`workspaceState` 或 `/clone-draft` 路由不存在

- [ ] **步骤 3：将创建、启动、停止语义改成规格定义**

```python
instance = StrategyInstance(
    user_id=user.id,
    template_id=template.id,
    name=name,
    symbol=symbol.upper(),
    exchange=exchange.lower(),
    direction=direction,
    params=params,
    risk_params=risk_params,
    account_id=account_id,
    status="draft",
    workspace_state="library",
)
```

```python
instance = await self.instance_repo.update(
    instance_id,
    status="running",
    workspace_state="running",
    last_started_at=datetime.now(UTC),
    last_stopped_at=None,
)
```

```python
return await self.instance_repo.update(
    instance_id,
    status="stopped",
    workspace_state="library",
    last_stopped_at=datetime.now(UTC),
)
```

- [ ] **步骤 4：新增“编辑副本到工作台”服务与接口**

```python
@router.post("/instances/{instance_id}/clone-draft")
async def clone_strategy_to_draft(...):
    draft = await service.clone_to_draft(inst_id, current_user.id)
    await session.commit()
    return APIResponse(data=_format_instance(draft))
```

- [ ] **步骤 5：扩展实例读模型**

```python
return {
    "id": inst.id,
    "name": inst.name,
    "templateId": template_code,
    "templateName": template_name,
    "status": inst.status,
    "workspaceState": inst.workspace_state,
    "sourceInstanceId": inst.source_instance_id,
    "lastStartedAt": inst.last_started_at.isoformat().replace("+00:00", "Z") if inst.last_started_at else None,
    "lastStoppedAt": inst.last_stopped_at.isoformat().replace("+00:00", "Z") if inst.last_stopped_at else None,
    ...
}
```

- [ ] **步骤 6：运行测试验证通过**

运行：`pytest backend/tests/test_strategy_center_flow.py -v`
预期：PASS

- [ ] **步骤 7：Commit**

```bash
git add backend/app/services/strategy_service.py backend/app/api/v1/strategies.py backend/tests/test_strategy_center_flow.py
git commit -m "feat: align strategy center lifecycle semantics"
```

### 任务 3：拆分前端数据模型与 API 调用

**文件：**
- 修改：`backend/app/web/static/js/api.js`
- 修改：`backend/app/web/static/js/strategy.js`
- 测试：`backend/app/web/static/js/strategy.js`

- [ ] **步骤 1：为前端写出分组函数的最小伪测试注释**

```javascript
// groupStrategyInstances([
//   { id: 1, status: 'running', workspaceState: 'running' },
//   { id: 2, status: 'draft', workspaceState: 'library' },
//   { id: 3, status: 'draft', workspaceState: 'draft' },
// ])
// =>
// {
//   running: [{ id: 1 }],
//   library: [{ id: 2 }],
//   drafts: [{ id: 3 }],
// }
```

- [ ] **步骤 2：在 API 客户端补齐新接口**

```javascript
async getStrategyInstances(status = 'all') {
  const json = await this.get(`/strategies/instances?status=${status}`);
  return json.data || json;
}

async cloneStrategyToDraft(instanceId) {
  const json = await this.post(`/strategies/instances/${instanceId}/clone-draft`);
  return json.data || json;
}
```

- [ ] **步骤 3：在 `strategy.js` 中抽出分组函数**

```javascript
function groupStrategyInstances(instances = []) {
  return {
    running: instances.filter(inst => inst.workspaceState === 'running' && inst.status === 'running'),
    library: instances.filter(inst => inst.workspaceState === 'library'),
    drafts: instances.filter(inst => inst.workspaceState === 'draft'),
  };
}
```

- [ ] **步骤 4：运行 JS 语法校验**

运行：

```bash
@'
const fs = require('fs');
new Function(fs.readFileSync('backend/app/web/static/js/api.js', 'utf8'));
new Function(fs.readFileSync('backend/app/web/static/js/strategy.js', 'utf8'));
console.log('strategy js syntax ok');
'@ | node -
```

预期：输出 `strategy js syntax ok`

- [ ] **步骤 5：Commit**

```bash
git add backend/app/web/static/js/api.js backend/app/web/static/js/strategy.js
git commit -m "refactor: split strategy center client state"
```

### 任务 4：重排策略中心页面为三段式布局

**文件：**
- 修改：`backend/app/web/static/index.html`
- 修改：`backend/app/web/static/css/app.css`
- 修改：`backend/app/web/static/js/strategy.js`
- 测试：`backend/app/web/static/js/strategy.js`

- [ ] **步骤 1：在 `index.html` 中替换旧结构容器**

```html
<div id="strategy-running-desk" class="cq-strategy-running-desk"></div>

<div class="cq-section-title" style="margin-top:var(--cq-space-6);">
  <h3>策略仓库</h3>
</div>
<div id="strategy-library-list"></div>

<div class="cq-section-title" style="margin-top:var(--cq-space-6);">
  <h3>工作台</h3>
</div>
<div id="strategy-workbench"></div>
```

- [ ] **步骤 2：在 CSS 中定义三区布局样式**

```css
.cq-strategy-running-desk {
  display: grid;
  gap: var(--cq-space-4);
  margin-bottom: var(--cq-space-6);
}

.cq-strategy-running-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--cq-space-3);
}

.cq-strategy-library-table {
  border: 1px solid var(--cq-border-default);
  border-radius: var(--cq-radius-lg);
  overflow: hidden;
}

.cq-strategy-workbench {
  display: grid;
  grid-template-columns: minmax(0, 1.15fr) minmax(320px, 0.85fr);
  gap: var(--cq-space-5);
}
```

- [ ] **步骤 3：将 `strategy.js` 渲染拆成三区**

```javascript
function renderStrategyCenter(instances) {
  const groups = groupStrategyInstances(instances);
  renderRunningDesk(groups.running);
  renderStrategyLibrary(groups.library);
  renderWorkbench(groups.drafts);
}
```

- [ ] **步骤 4：将 `loadStrategyPage()` 改成调用新总渲染**

```javascript
window._strategyInstances = instances;
window._cachedTemplates = templates;
renderRunningDeskSummary(instances);
renderTemplatePills(templates, instances);
renderStrategyCenter(instances);
```

- [ ] **步骤 5：运行 JS 语法校验**

运行：

```bash
@'
const fs = require('fs');
new Function(fs.readFileSync('backend/app/web/static/js/strategy.js', 'utf8'));
console.log('strategy layout js ok');
'@ | node -
```

预期：输出 `strategy layout js ok`

- [ ] **步骤 6：Commit**

```bash
git add backend/app/web/static/index.html backend/app/web/static/css/app.css backend/app/web/static/js/strategy.js
git commit -m "feat: rebuild strategy center layout"
```

### 任务 5：把工作台动作改成“保存入仓库 / 启动入运行台 / 运行中编辑复制草案”

**文件：**
- 修改：`backend/app/web/static/js/strategy.js`
- 测试：`backend/tests/test_strategy_center_flow.py`
- 测试：`backend/app/web/static/js/strategy.js`

- [ ] **步骤 1：把工作台主按钮拆成两个明确动作**

```html
<button class="cq-btn cq-btn--secondary" onclick="saveWorkbenchStrategy()" id="save-strategy-btn">保存为策略</button>
<button class="cq-btn cq-btn--primary" onclick="launchWorkbenchStrategy()" id="launch-strategy-btn">启动策略</button>
```

- [ ] **步骤 2：将旧 `createStrategyInstance()` 拆成保存和启动两个流程**

```javascript
async function saveWorkbenchStrategy() {
  const payload = await buildWorkbenchPayload();
  const result = await api.createStrategyInstance(payload);
  showToast('策略已保存到策略仓库', 'success');
  deselectTemplate();
  await loadStrategyPage();
  return result;
}

async function launchWorkbenchStrategy() {
  const result = await saveWorkbenchStrategy();
  await api.startStrategy(result.id);
  showToast('策略已启动并进入运行台', 'success');
  await loadStrategyPage();
}
```

- [ ] **步骤 3：把运行台编辑按钮改为复制草案**

```javascript
async function editRunningStrategy(instanceId) {
  const draft = await api.cloneStrategyToDraft(instanceId);
  await loadStrategyPage();
  await openWorkbenchDraft(draft.id);
}
```

- [ ] **步骤 4：补充后端流转测试**

```python
def test_starting_saved_strategy_moves_it_to_running(client, auth_headers, saved_strategy):
    resp = client.post(f"/api/v1/strategies/instances/{saved_strategy.id}/start", headers=auth_headers)
    body = resp.json()["data"]
    assert body["status"] == "running"


def test_clone_running_strategy_does_not_mutate_original(client, auth_headers, running_instance):
    resp = client.post(f"/api/v1/strategies/instances/{running_instance.id}/clone-draft", headers=auth_headers)
    assert resp.status_code == 200
    original = client.get(f"/api/v1/strategies/instances/{running_instance.id}", headers=auth_headers).json()["data"]
    assert original["status"] == "running"
    assert original["workspaceState"] == "running"
```

- [ ] **步骤 5：运行全链路验证**

运行：

```bash
pytest backend/tests/test_strategy_center_flow.py -v
@'
const fs = require('fs');
new Function(fs.readFileSync('backend/app/web/static/js/strategy.js', 'utf8'));
console.log('strategy actions ok');
'@ | node -
```

预期：
- pytest 全绿
- 输出 `strategy actions ok`

- [ ] **步骤 6：Commit**

```bash
git add backend/app/web/static/js/strategy.js backend/tests/test_strategy_center_flow.py
git commit -m "feat: align strategy center actions with product flow"
```

### 任务 6：人工验证页面语义与规格一致

**文件：**
- 修改：无
- 测试：`docs/superpowers/specs/2026-05-03-strategy-center-design.md`

- [ ] **步骤 1：启动本地服务**

运行：`uvicorn app.main:app --host 127.0.0.1 --port 8000`
预期：服务启动成功，可访问 `/web/#strategy`

- [ ] **步骤 2：验证运行台只显示运行中策略**

操作：
1. 准备至少 1 个 `running` 策略
2. 准备至少 1 个 `stopped` 或 `draft` 策略
3. 打开 `http://127.0.0.1:8000/web/#strategy`

预期：
- 顶部运行台只出现 `running` 策略
- 未运行策略不出现在运行台

- [ ] **步骤 3：验证“保存为策略”进入仓库**

操作：
1. 在工作台中创建一个新规则策略
2. 点击“保存为策略”

预期：
- 新策略不进入运行台
- 新策略出现在策略仓库
- 工作台草案被清空或回到空白态

- [ ] **步骤 4：验证“启动策略”进入运行台**

操作：
1. 从工作台点击“启动策略”
2. 或在策略仓库点击“启动”

预期：
- 策略进入运行台
- 不再停留在策略仓库可见区

- [ ] **步骤 5：验证“停止后回仓库”**

操作：
1. 在运行台停止一个策略

预期：
- 该策略从运行台消失
- 该策略重新出现在策略仓库

- [ ] **步骤 6：验证“编辑运行中策略”是复制草案**

操作：
1. 在运行台点击“编辑”

预期：
- 原运行中策略继续保持运行
- 工作台打开一个副本草案
- 不直接修改原运行实例

- [ ] **步骤 7：Commit**

```bash
git add .
git commit -m "test: verify strategy center product flow"
```
