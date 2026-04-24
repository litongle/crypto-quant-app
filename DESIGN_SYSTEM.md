# 币钱袋 (CryptoQuant) — 统一设计系统 v2.0

> 基于专业金融交易产品标准，构建跨平台一致的视觉语言

---

## 1. 设计哲学

**专业 · 克制 · 高密度信息**

- 金融产品不追求"炫酷"，追求**清晰和信任感**
- 信息密度优先：一屏尽量展示更多有意义的数据
- 克制使用渐变和装饰，让数据本身成为视觉焦点
- 暗色模式下，通过微妙的层级差异而非强烈色彩对比来区分区域

---

## 2. 色彩系统

### 2.1 品牌色

```
Primary:        #6366F1  (Indigo 500)  — 品牌主色，强调、CTA
Primary Hover:   #818CF8  (Indigo 400)  — 悬停态
Primary Muted:   rgba(99,102,241,0.12)   — 淡背景
Primary Subtle:  rgba(99,102,241,0.06)   — 极淡背景
```

> **为什么从Cyan切换到Indigo？**  
> Cyan (#22d3ee) 在暗色背景上过于刺眼，长时间盯盘易疲劳。  
> Indigo 兼具专业感和科技感，Bloomberg/TradingView 均采用偏蓝紫色系。

### 2.2 语义色

```
Profit/Success:  #10B981  (Emerald 500)
Loss/Danger:     #EF4444  (Red 500)
Warning:         #F59E0B  (Amber 500)
Info:            #3B82F6  (Blue 500)

Profit Muted:    rgba(16,185,129,0.12)
Loss Muted:      rgba(239,68,68,0.12)
```

### 2.3 暗色模式色阶

```
Background L0:   #0B0F1A  — 页面背景（最深）
Background L1:   #111827  — 卡片、侧栏
Background L2:   #1A2235  — 输入框、深层嵌套
Background L3:   #1F2937  — 悬浮层、边框

Border Default:  #1F2937
Border Hover:    #374151
Border Active:   #6366F1

Text Primary:    #F1F5F9  (Slate 100)
Text Secondary:  #94A3B8  (Slate 400)
Text Tertiary:   #64748B  (Slate 500)
Text Disabled:   #475569  (Slate 600)
```

### 2.4 交易所品牌色

```
Binance:   #F0B90B  (Gold)
OKX:       #FFFFFF  (White)
HTX/Huobi: #2A6EDB  (Blue)
```

---

## 3. 字体系统

### 3.1 字体栈

```css
--font-sans: 'Inter', 'PingFang SC', 'Noto Sans SC', system-ui, -apple-system, sans-serif;
--font-mono: 'JetBrains Mono', 'Fira Code', 'Cascadia Code', ui-monospace, monospace;
```

### 3.2 字号比例 (Major Second — 1.125)

| Token       | Size   | Weight | Line-height | Letter-spacing | Usage |
|-------------|--------|--------|-------------|----------------|-------|
| `text-xs`   | 11px   | 500    | 1.4         | 0.01em         | 标签、徽章 |
| `text-sm`   | 12px   | 400    | 1.5         | 0              | 辅助说明、表头 |
| `text-base` | 13px   | 400    | 1.5         | 0              | 正文、表格内容 |
| `text-md`   | 14px   | 500    | 1.5         | 0              | 导航、按钮、标签 |
| `text-lg`   | 16px   | 500    | 1.4         | -0.01em        | 区块标题 |
| `text-xl`   | 18px   | 600    | 1.3         | -0.01em        | 卡片标题 |
| `text-2xl`  | 22px   | 600    | 1.25        | -0.02em        | 页面标题 |
| `text-3xl`  | 28px   | 700    | 1.2         | -0.02em        | 大数值展示 |
| `text-num`  | var    | 600    | 1.2         | 0              | 金融数字(使用tnum) |

### 3.3 关键规则

- **金融数字** 必须使用 `font-feature-settings: "tnum"` 保证对齐
- **字重**：默认400，标题500-600，避免使用800（太重）
- **等宽字体** 用于：价格、数量、百分比、代码

---

## 4. 间距系统 (4px 基准)

```
--space-0:  0px
--space-1:  4px    — 图标与文字间距
--space-2:  8px    — 紧凑元素间距
--space-3:  12px   — 组件内部间距
--space-4:  16px   — 卡片内边距、表单项间距
--space-5:  20px   — 区块间距
--space-6:  24px   — 页面区块间距
--space-8:  32px   — 大区块间距
--space-10: 40px   — 区域分隔
--space-12: 48px   — 页面边距
--space-16: 64px   — 大空白
```

---

## 5. 圆角系统

```
--radius-sm:   4px   — 小元素（标签、Badge）
--radius-md:   6px   — 按钮、输入框
--radius-lg:   8px   — 卡片、对话框
--radius-xl:   12px  — 模态框、大面板
--radius-full: 9999px — 胶囊、头像
```

> **核心原则**：金融App圆角控制在4-8px，避免过度圆润带来的非专业感

---

## 6. 阴影系统

```css
--shadow-xs:  0 1px 2px rgba(0,0,0,0.3);
--shadow-sm:  0 1px 3px rgba(0,0,0,0.4), 0 1px 2px rgba(0,0,0,0.2);
--shadow-md:  0 4px 6px rgba(0,0,0,0.4), 0 2px 4px rgba(0,0,0,0.2);
--shadow-lg:  0 10px 15px rgba(0,0,0,0.4), 0 4px 6px rgba(0,0,0,0.2);
--shadow-xl:  0 20px 25px rgba(0,0,0,0.5), 0 8px 10px rgba(0,0,0,0.3);
```

---

## 7. 组件规范

### 7.1 按钮

```
Primary Button:
  bg: #6366F1
  text: white
  radius: 6px
  padding: 10px 20px (sm) / 12px 24px (md)
  font: 14px/500
  hover: bg #818CF8, translateY(-1px), shadow-md
  active: translateY(0), shadow-xs
  disabled: opacity 0.5

Secondary Button:
  bg: transparent
  border: 1px solid #374151
  text: #94A3B8
  hover: border #6366F1, text #818CF8, bg primary-muted

Danger Button:
  bg: rgba(239,68,68,0.12)
  text: #EF4444
  border: 1px solid rgba(239,68,68,0.2)
  hover: bg rgba(239,68,68,0.2)
```

**禁止**：渐变按钮（linear-gradient）。纯色 + 微交互才是专业金融产品的做法。

### 7.2 卡片

```
Card:
  bg: #111827
  border: 1px solid #1F2937
  radius: 8px
  padding: 16px (sm) / 20px (md) / 24px (lg)
  hover (interactive): border #374151, shadow-sm
  no gradient background
```

### 7.3 输入框

```
Input:
  bg: #1A2235
  border: 1px solid #1F2937
  radius: 6px
  padding: 10px 14px
  text: 13px/400, #F1F5F9
  placeholder: #475569
  focus: border #6366F1, ring rgba(99,102,241,0.2)
  error: border #EF4444, ring rgba(239,68,68,0.2)
```

### 7.4 标签/Badge

```
Tag:
  padding: 2px 8px
  radius: 4px
  font: 11px/500

  Profit: bg rgba(16,185,129,0.12), text #10B981
  Loss:   bg rgba(239,68,68,0.12),  text #EF4444
  Info:   bg rgba(99,102,241,0.12),  text #818CF8
  Warn:   bg rgba(245,158,11,0.12),  text #F59E0B
  Neutral: bg rgba(148,163,184,0.08), text #94A3B8
```

### 7.5 导航 (Web侧栏)

```
Sidebar:
  width: 240px
  bg: #0B0F1A
  border-right: 1px solid #1F2937
  
  Nav Item:
    padding: 10px 16px
    radius: 6px
    margin: 2px 12px
    text: 13px/500, #64748B
    
    Active:
      bg: rgba(99,102,241,0.08)
      text: #818CF8
      left-border: 2px solid #6366F1 (not border-left, use pseudo-element)
    
    Hover:
      bg: rgba(99,102,241,0.04)
      text: #94A3B8
```

### 7.6 图标规范

**必须使用SVG图标**，禁止Emoji。推荐图标库：
- **Lucide** (https://lucide.dev) — 开源、一致、轻量
- 备选：Phosphor Icons

关键图标映射：
| 当前Emoji | 替换SVG图标 |
|-----------|-------------|
| 💎 Logo   | 自定义Logo SVG |
| 🏠 首页   | `layout-dashboard` |
| 📊 策略   | `brain-circuit` |
| 📈 回测   | `line-chart` |
| 🔐 账户   | `shield-check` |
| ⚙️ 设置   | `settings-2` |
| 📈 买入   | `trending-up` |
| 📉 卖出   | `trending-down` |
| ⚡ 信号   | `zap` |
| 🎯 目标   | `target` |

---

## 8. 动效规范

```css
--duration-fast:    150ms    — hover、focus
--duration-normal:  200ms    — 导航切换、展开折叠
--duration-slow:    300ms    — 页面过渡、模态框

--ease-default:     cubic-bezier(0.4, 0, 0.2, 1)
--ease-in:          cubic-bezier(0.4, 0, 1, 1)
--ease-out:         cubic-bezier(0, 0, 0.2, 1)
--ease-bounce:      cubic-bezier(0.34, 1.56, 0.64, 1)
```

**核心动效**：
- 按钮hover: `translateY(-1px)` + shadow
- 卡片hover: border-color transition
- 导航切换: 左侧指示条滑动
- 数值变化: 数字翻动动画
- 加载态: 骨架屏 (Skeleton) 替代 Spinner

---

## 9. 响应式断点

```
Mobile:     < 768px   — 底部导航 + 全宽卡片
Tablet:     768-1024px — 侧栏折叠 + 自适应网格
Desktop:    1024-1440px — 固定侧栏 + 多列布局
Wide:       > 1440px   — 最大宽度1440px居中 + 增加间距
```

---

## 10. 信息架构

### 10.1 Web Console 导航

```
侧栏:
  🏠 控制台     /dashboard
  📊 策略中心   /strategy  
  📈 回测       /backtest
  ⚡ 信号       /signals (新增)
  🔐 账户       /accounts
  ────────
  👤 用户信息
  ⚙️ 设置
  退出
```

### 10.2 Mobile App 导航

```
底部Tab:
  控制台      /dashboard
  策略        /strategies
  信号        /signals (新增)
  我的        /settings
```

---

## 11. 可访问性 (WCAG AA)

- 文字对比度 ≥ 4.5:1 (正文) / 3:1 (大标题)
- 可点击区域最小 44x44px
- 所有图标有 `aria-label`
- 颜色不是唯一信息区分方式 (同时使用图标/文字)
- 键盘可完全导航 (focus-visible 样式)

---

## 12. 设计交付

### CSS变量前缀规范

```css
/* 使用 --cq- 前缀 (CryptoQuant缩写) */
:root {
  --cq-color-primary: #6366F1;
  --cq-radius-md: 6px;
  --cq-space-4: 16px;
  --cq-text-base: 13px;
  /* ... */
}
```

### 命名规范

- 组件: `.cq-card`, `.cq-btn`, `.cq-input`
- 变体: `.cq-btn--primary`, `.cq-btn--danger`
- 状态: `.cq-btn.is-disabled`, `.cq-card.is-selected`
- 工具: `.cq-text-profit`, `.cq-text-loss`

---

*v2.0 · 2025-04-25 · 统一Web + Mobile设计语言*
