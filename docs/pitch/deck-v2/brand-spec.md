# AML Open Framework · Pitch Deck V2 · Brand Spec

> 采集日期：2026-04-29
> 资产来源：现有 v1 deck (commit 275948c) + `tokens.css` + 真实 CLI 输出捕获
> 资产完整度：完整（codebase IS the brand — own product, no external assets needed）

## 🎯 核心资产（一等公民）

### Logo / Wordmark
- 形态：**`AML · OPEN FRAMEWORK`** typographic wordmark (JetBrains Mono, uppercase, 0.18em letterspacing)
- 配 8px cyan glowing dot (`var(--accent)` + `var(--accent-glow)`)
- 位置：top:64 left:96 of every slide (`tokens-v2.css` `.wordmark`)
- 浅底反色版：n/a（deck 全部深底）
- 禁用变形：不要拉伸，不要换字，不要改颜色组合

### 产品截图（dashboard / CLI / spec）— 数字产品的"主角"
- **Dashboard 真截图**：`docs/pitch/03-framework-overview.png` 等已在 repo 中的 PNG
- **真实 CLI 输出**：`docs/pitch/deck-v2/captures/today-{cco,mlro,analyst}.txt`（live-captured 2026-04-29）
- **Spec YAML 片段**：直接从 `examples/canadian_schedule_i_bank/aml.yaml` 抽
- 使用场景：**任何展示产品的 slide 必须用真截图/真输出，禁止 CSS 仿制 terminal 或 dashboard**

## 🎨 辅助资产

### 色板（继承 v1 + 加 1 个 chapter accent）
```css
--bg:           #0a0e1a    /* deep navy — page background */
--panel:        #0f172a    /* card / terminal background */
--panel-border: #1e293b    /* card border */
--ink:          #f1f5f9    /* primary text */
--ink-dim:      #94a3b8    /* secondary text */
--ink-faint:    #475569    /* meta / numbering */
--accent:       #67e8f9    /* cyan — primary brand color */
--accent-glow:  rgba(103,232,249,0.4)
--rag-green:    #86efac    /* semantic only — RAG bands */
--rag-amber:    #fde68a
--rag-red:      #fca5a5

/* NEW for V2 */
--chapter-warm: #f5e6c8    /* warm parchment — chapter-opener serif text */
--rule:         rgba(148,163,184,0.15)
```

**禁用色**：紫渐变（AI slop 的代表）；其他凭空发明的色一律不许出现。

### 字型（V2 新增 Source Serif 4）

```html
<!-- 新增 Source Serif 4 — 给 chapter opener / pull quote 用 -->
<link href="https://fonts.googleapis.com/css2?family=Source+Serif+4:opsz,wght@8..60,300;8..60,400;8..60,600;8..60,700&family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
```

| 用途 | 字体 | 何时用 |
|---|---|---|
| Display（chapter opener / hero quote） | **Source Serif 4** 600/700 | Act 开篇页、关键引语、"重"的瞬间 |
| Body / titles / 大段文字 | Inter 400-800 | 默认 — 标题、正文、card 内文 |
| Code / accent labels / numbers | JetBrains Mono 400-700 | 命令、eyebrow 标签、slide 编号、数据 |

**V1 全场 Inter 显得"轻"——V2 在 1/3 的 slide 引入衬线 display 增加监管级权威感**。但**不要全场塞**——衬线的力量来自稀缺。规则：每个 Act 最多 1 张用 Source Serif（chapter opener）。

### 签名细节（120% 做到的地方）

1. **CLI 输出的 terminal panel**：
   - `font-family: 'JetBrains Mono'`
   - 真实 ANSI 颜色映射（cyan eyebrow、ink-dim 注释、accent 命令）
   - terminal "chrome"：左上角三个 dot（红黄绿）+ "$ aml today --persona cco" 标题栏
   - 不要做成截图——做成可被屏幕阅读器读出的 `<pre>`，方便 PDF 导出后文字仍可搜
2. **CLI Bridge slide 的命令分组**：四列 by persona（CCO / MLRO / Analyst / Eng），每列 4 条命令，等高，cyan 编号
3. **Hero quote 的 hanging indent**：用 Source Serif 4 italic、64px、左侧 4px 高 cyan rule，留 96px 顶部呼吸

### 禁区（绝对不做）

- ❌ 紫渐变背景 / 紫色 accent
- ❌ Emoji 作 icon（除非用户内容里本来就有）
- ❌ 圆角卡片 + 左彩 border accent（v1 没用，v2 也不用）
- ❌ CSS 画 terminal / fake CLI prompt（**必须用真 capture**）
- ❌ CSS 画 dashboard / fake screenshot（用 repo 里已有 PNG）
- ❌ 占位 stats / 编造 quote
- ❌ 全场只用 Inter 当 display（v1 的弱点，v2 必修）
- ❌ 装饰性 icon 在每个标题旁边

### 气质关键词

`严谨` · `克制` · `监管级权威` · `工程纪律` · `不卖弄`

不要：`激动`、`未来感`、`赛博`、`紫粉`、`hype`

## 📐 Layout 系统（继承 v1，扩展 V2）

### 1920×1080 canvas 区域预算
- **0–144px**：top chrome（wordmark 左 + slide num 右 + 1px header rule）
- **200–420px**：title block（eyebrow + h1）
- **460–920px**：body（cards / panels / split panes / 真截图）
- **bottom 64px**：footer（tagline / repo URL / page meta）

### V2 新增 grammar：dual-pane

```
┌─────────────────────────────────────────────────────────────┐
│ wordmark              ─────────────              slide-num   │
├─────────────────────────────────────────────────────────────┤
│ EYEBROW                                                      │
│ Headline (Inter 64px, max 2 lines)                           │
├──────────────────────────────┬──────────────────────────────┤
│                              │                              │
│  Narrative pane              │  Code / capture pane         │
│  (Inter, ~36% width)         │  (JetBrains Mono, ~60%)      │
│  - Pain bullet               │  Real terminal capture       │
│  - Bridge sentence           │  with chrome                 │
│  - Outcome                   │                              │
│                              │                              │
└──────────────────────────────┴──────────────────────────────┘
                                                  github.com/...
```

Used by **every "X command unlocks Y leader artifact" slide**: S05 (CLI Bridge), S06 (Today), S07 (Add-Rule + Typology-Import), S08 (Propose-Change), S09 (Auditor-Pack), S13 (Init + BYOD), S14 (Notify-Digest).

### V2 新增 grammar：chapter opener（衬线 hero）

```
┌─────────────────────────────────────────────────────────────┐
│ wordmark              ─────────────              slide-num   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│   ACT III                                                    │
│                                                              │
│   The morning ritual.                                        │
│   ──────────────────                                         │
│                                                              │
│   Source Serif 4, 88px, light italic, hanging cyan rule      │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

Used at the start of each Act (Acts I-VI). 6 slides total. No body content — pure breathing room.

## 🎯 受众落点（双 track 但单 deck）

每张 slide 必须同时能被以下两类受众在 ≤8 秒内读懂：
- **CCO / MLRO**：左 pane 的 narrative + 标题
- **Eng / 2LoD**：右 pane 的 CLI 输出 + 命令 + spec

如果右 pane 看不懂、左 pane 看不到价值——这张 slide 失败了 50% 的受众。**reviewer 模式：每张 slide 自检"这张同时讲明白业务和技术了吗？"**
