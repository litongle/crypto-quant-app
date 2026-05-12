# 设计系统 v4 升级 · Linear 风重构

> 状态：设计已对齐，待 writing-plans 阶段。
>
> 作者：litongle ＋ Claude（brainstorming 会话）
> 日期：2026-05-13
> 前置：当前为 Semi Design v3.1 token，存在卡片层次单薄、light 模式 header 失明、空状态简陋、表单 input 裸奔等问题。

## 目标

把整套前端从 Semi v3.1 升级到 **Linear / Vercel 风** 的 v4 设计系统：
- Dark first，light 作为辅助
- 保留现有 indigo 主色 `#4D7FFF` 不动，但重做色阶
- 卡片采用「比背景更暗 + 蓝 border + 微 glow」的 Linear 反层次
- 字号节奏更紧凑（body 14 → 13），数字对比更强（PnL 20 → 28）
- 动效收敛到 150 / 180 / 220ms 三档

## 非目标（显式 YAGNI）

- ❌ 不重写 dashboard / backtest / events 页面布局
- ❌ 不引入新字体或新 SVG 库（已有 Geist Sans + Lucide-style SVG 内联）
- ❌ 不动 K 线图（lightweight-charts 自带样式）
- ❌ 不新增页面或功能
- ❌ 不重做事件流过滤器/分页

## 第 1 节：色彩 Token（Dark First）

### 1.1 Surface 6 档（从 4 档扩展）

```css
:root {
  --cq-bg-l0:  #0A0A0C;       /* 页面底（最暗） */
  --cq-bg-l1:  #0F0F12;       /* header / sider（与 l0 几乎齐平） */
  --cq-bg-l2:  #141417;       /* 卡片（反向更暗于 l0） */
  --cq-bg-l3:  #1A1A1F;       /* hover 态 */
  --cq-bg-l4:  #1F1F25;       /* 选中态 */          /* ⭐ 新增 */
  --cq-bg-l5:  #26262E;       /* 输入框 inset 凹陷 */ /* ⭐ 新增 */
}
```

「卡片比背景更暗」是 Linear 招牌的反直觉手法，靠 border + glow 划分层级。

### 1.2 Border + Glow

```css
:root {
  --cq-border-default: rgba(255,255,255,0.06);
  --cq-border-hover:   rgba(77,127,255,0.32);   /* hover 时变蓝 */
  --cq-border-active:  rgba(77,127,255,0.48);
  --cq-border-subtle:  rgba(255,255,255,0.04);

  --cq-glow-xs: 0 0 0 1px rgba(77,127,255,0.16);
  --cq-glow-sm: 0 0 0 1px rgba(77,127,255,0.16), 0 0 12px rgba(77,127,255,0.06);
  --cq-glow-md: 0 0 0 1px rgba(77,127,255,0.24), 0 0 24px rgba(77,127,255,0.10);
}
```

### 1.3 Text

```css
:root {
  --cq-text-primary:    #EDEDED;
  --cq-text-secondary:  #C5C7CA;
  --cq-text-tertiary:   #8B8B93;
  --cq-text-disabled:   #5F6368;
}
```

### 1.4 Light 主题对应

Light 主题仅做最小化调校，保持视觉一致：

```css
[data-theme="light"] {
  --cq-bg-l0:  #F7F8FA;
  --cq-bg-l1:  #FFFFFF;
  --cq-bg-l2:  #FFFFFF;
  --cq-bg-l3:  #F0F1F4;
  --cq-bg-l4:  #EAECEF;
  --cq-bg-l5:  #F5F6F8;
  --cq-border-default: rgba(28,31,35,0.08);
  --cq-border-hover:   rgba(0,100,250,0.32);
  --cq-glow-xs: 0 0 0 1px rgba(0,100,250,0.12);
  --cq-glow-sm: 0 0 0 1px rgba(0,100,250,0.12), 0 0 12px rgba(0,100,250,0.04);
  --cq-glow-md: 0 0 0 1px rgba(0,100,250,0.20), 0 0 24px rgba(0,100,250,0.06);
}
```

注意 light 主题 header 玻璃态背景需要单独修复（见第 5.A4 节）。

## 第 2 节：字号 + 字重

| Token | 当前 | v4 | 用在 |
|---|---|---|---|
| `--cq-text-xs` | 12 | **11** | tag/计数 |
| `--cq-text-sm` | 13 | **12** | timestamp/辅助 |
| `--cq-text-base` | 14 | **13** | body/label/input |
| `--cq-text-md` | 14 | 14 | 卡片标题 |
| `--cq-text-lg` | 16 | **15** | section 标题 |
| `--cq-text-xl` | 18 | 18 | h3 |
| `--cq-text-2xl` | 20 | **22** | 页头 h1 |
| `--cq-text-3xl` | 24 | **28** | 大数字（PnL） |
| `--cq-text-4xl` | 30 | **36** | dashboard 主数据 |

**字重**：取消 700，统一用 400 / 500 / 600 三档。

**数字保留** `font-feature-settings: "tnum"` + `letter-spacing: -0.02em`。

## 第 3 节：卡片层次

```css
.cq-card {
  background: var(--cq-bg-l2);
  border: 1px solid var(--cq-border-default);
  border-radius: 10px;
  padding: 20px;
  transition: border-color 150ms var(--cq-ease-default),
              box-shadow 150ms var(--cq-ease-default),
              transform 180ms var(--cq-ease-out),
              background-color 180ms var(--cq-ease-default);
}

.cq-card--interactive { cursor: pointer; }
.cq-card--interactive:hover {
  border-color: var(--cq-border-hover);
  box-shadow: var(--cq-glow-sm);
  transform: translateY(-1px);
}

.cq-card--selected {
  background: var(--cq-bg-l4);
  border-color: var(--cq-border-active);
  box-shadow: var(--cq-glow-md);
}
```

保留 `translateY(-1px)` 的 Linear 招牌微浮起。

## 第 4 节：圆角 / 间距 / 动效

### 4.1 圆角

| Token | 当前 | v4 |
|---|---|---|
| `--cq-radius-sm` | 3 | **4** |
| `--cq-radius-md` | 6 | 6 |
| `--cq-radius-lg` | 8 | 8 |
| `--cq-radius-xl` | 12 | **10** |
| `--cq-radius-full` | 9999 | 9999 |

### 4.2 间距

保留 `4 / 8 / 12 / 16 / 20 / 24 / 32 / 40 / 48`，不动。

### 4.3 动效 timing

```css
:root {
  --cq-duration-fast:   150ms;
  --cq-duration-medium: 180ms;
  --cq-duration-slow:   220ms;
  --cq-ease-default: cubic-bezier(0.4, 0, 0.2, 1);
  --cq-ease-out:     cubic-bezier(0.16, 1, 0.3, 1);
}
```

**规则**：
- 颜色 / border / opacity 变化 → 150ms `ease-default`
- transform / modal 进入 → 180ms `ease-out`
- 抽屉滑入退出 → 220ms `ease-out`
- 删除 `--cq-duration-normal`；主题切换从 300ms 改为 180ms

## 第 5 节：组件改造清单

### A. Tokens 联动（基础设施）

| # | 组件 | 改动 | 文件 |
|---|---|---|---|
| A1 | `.cq-card` 系列 | 套新 token + hover/selected 态 | `app.css` |
| A2 | `.cq-input` | 背景改 `--cq-bg-l5`，hover/focus 用 glow-xs | `app.css` |
| A3 | `.cq-btn--primary` | hover 加 glow-sm | `app.css` |
| A4 | `.cq-header` light 模式 | 玻璃态背景从 `rgba(255,255,255,0.75)` 改为 `rgba(247,248,250,0.85)` + border-bottom | `app.css` |
| A5 | 主题切换 transition | `body` 300ms → 180ms | `app.css` |

### B. 图里能看见的痛点

| # | 组件 | 改动 |
|---|---|---|
| B1 | 策略仓库空状态 | `strategy.js renderStrategyLibrary` 在 length=0 分支增加 SVG 插图 + 「从模板新建」CTA |
| B2 | 模板 pill 卡片（6 个） | `strategy.js renderTemplateList` 改为 grid 2 列 / 桌面 3 列，每张卡含 icon + 名称 + 一句模板描述 + 收藏 chevron |
| B3 | 设置抽屉表单 | `settings-drawer.js renderSmtpPane / renderNotificationsPane / renderRiskSettingsPane` 套 `.cq-settings-form` 新样式（input 凹陷、字段分组） |
| B4 | SMTP SSL/TLS 复选框位置 | 在 HTML 模板中移到「端口」紧下方 |
| B5 | SMTP 密码 label | 改成 `密码 / 授权码`；「不是登录密码」放 small 提示 |
| B6 | 抽屉 header 与 tabs 分隔 | `app.css .cq-drawer__header` 加 `border-bottom: 1px solid var(--cq-border-subtle)` |
| B7 | 模拟盘 tab 空白 bug | 排查 `paper.js renderPaperPane` 与 `api.getPaperAccounts`；定位失败原因后做精确修复（详见排错章节） |

### C. 联动小调整

| # | 组件 | 改动 |
|---|---|---|
| C1 | `.cq-tag` 各色 | profit/loss/warning/info muted 变量保持，文字用 secondary |
| C2 | `.cq-toast` | 阴影 → glow-sm |
| C3 | `.cq-dialog` modal | 入场 transform 改 180ms `ease-out` |
| C4 | `.cq-toggle` switch | hover 加 glow-xs |

### D. 配套基础设施

| # | 改动 | 文件 |
|---|---|---|
| D1 | `<link>` CSS 版本号 bump | `index.html`：`app.css?v=2026-05-13b` |
| D2 | Service Worker `CACHE_NAME` 升级 | `sw.js`：`cq-sw-v9` |

## 第 6 节：模拟盘 tab 空白 bug 排错策略

**现象**：图 3 中 `点击模拟盘 tab` 后只剩骨架灰块，没有 header 和空状态卡片。

**已知**：
- `settings-drawer.js` 调用 `renderPaperPane('#settings-pane-paper')`，selector 正确
- `paper.js` 接收 selector OK，进入 try/catch
- 失败时走 toast + `paperState.accounts = []`，但**仍应渲染 header + 空状态**

**排查步骤**：
1. 打开抽屉点模拟盘 tab，开 DevTools Network 看 `GET /api/v1/accounts/paper` 实际返回
2. 看 Console 是否有 JS 异常（toast 可能因为没初始化而吞错）
3. 看 `paperState.accounts` 实际值

**最可能的 root cause**（两个候选）：
- **候选 1**：接口路径或鉴权问题，导致 `accounts` 是 `undefined` 而非 `[]`，`accounts.length` 报错中断渲染。修复：`const accounts = paperState.accounts || [];` 已经在 line 26 处理；但需确认 `paperState.accounts = await ...` 失败时是否真的赋成 `[]`
- **候选 2**：抽屉 body 容器高度不足导致内容被裁切（非真 bug）。修复：检查 `.cq-drawer__body` overflow / max-height

修复一定在 **paper.js / 抽屉 CSS / accounts API** 三者之一，不会扩散。

## 工作量预估

| 阶段 | 任务 | 预估时间 |
|---|---|---|
| Phase 1 | Token 文件重写 + light/dark 校准 | 1.5h |
| Phase 2 | `.cq-card`/`.cq-input`/`.cq-btn`/`.cq-header` 联动 | 2h |
| Phase 3 | 策略仓库空状态 + 模板卡片 B1/B2 | 1.5h |
| Phase 4 | 设置抽屉 B3/B4/B5/B6 | 1.5h |
| Phase 5 | bug 排查 + 修复 B7 | 0.5–1h（取决于 root cause） |
| Phase 6 | 联动小调整 C 系列 | 1h |
| Phase 7 | CSS 版本号 + SW bump + 手动验证 | 0.5h |
| **合计** | — | **≈ 8–10h** |

## 验证策略

每个 Phase 后：
1. 强刷浏览器（先在 DevTools Application 里 Unregister SW，再 Ctrl+Shift+R）
2. Dark / Light 模式各看一遍
3. 桌面 (1920) / 平板 (768) / 手机 (375) 三个断点验证
4. Phase 7 跑一遍 `docker compose run --rm backend pytest`（CSS 改动不应影响测试，但确认没误改 HTML 模板）

## 风险

- **R1**：Linear 「卡片更暗」反直觉，实际看到可能不喜欢。**对策**：第 1 节落地后立即在浏览器看效果，不满意马上调；CSS 改动可一行翻转。
- **R2**：字号缩小（body 14 → 13）老花眼用户可能嫌小。**对策**：用户单人确认，本人现场看效果决定。
- **R3**：B7 bug 真因不明，可能比预估久。**对策**：单独 Phase，不影响其他 Phase 推进。
- **R4**：light 模式的 indigo glow 在白底上可能太刺眼。**对策**：light 主题的 glow 强度已经下调到 dark 的 60%（见 1.4 节）。

## 实施顺序约束

Phase 1（token）必须先做 —— 后面所有 Phase 都依赖新 token。其余 Phase 2-7 互相独立，可任意顺序。建议：
```
Phase 1 → 用户验收 token 视觉 → Phase 2 → 用户验收 → ...
```

每个 Phase 一个 commit，便于回退。
