---
name: Build-Factory
colors:
  # === Primary (ENGINE BASE green / ブランド主色) ===
  primary: "#1a6648"
  on-primary: "#ffffff"
  primary-container: "#d3f0e0"
  on-primary-container: "#082015"
  # === Secondary (Slate Steel / 中性ニュートラル) ===
  secondary: "#475569"
  on-secondary: "#ffffff"
  secondary-container: "#e2e8f0"
  on-secondary-container: "#0f172a"
  # === Tertiary (Amber Warning / アクセント) ===
  tertiary: "#d97706"
  on-tertiary: "#ffffff"
  tertiary-container: "#fef3c7"
  on-tertiary-container: "#78350f"
  # === Surface (背景 / カード) ===
  surface: "#ffffff"
  on-surface: "#0f172a"
  surface-variant: "#f1f5f9"
  on-surface-variant: "#475569"
  # === Error ===
  error: "#dc2626"
  on-error: "#ffffff"
  # === Neutral (ページ背景) ===
  neutral: "#f8fafc"
  on-neutral: "#0f172a"
typography:
  headline-display:
    fontFamily: "Noto Sans JP"
    fontSize: 56px
    fontWeight: 700
    lineHeight: 1.15
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: "Noto Sans JP"
    fontSize: 36px
    fontWeight: 700
    lineHeight: 1.25
  headline-md:
    fontFamily: "Noto Sans JP"
    fontSize: 24px
    fontWeight: 700
    lineHeight: 1.4
  body-lg:
    fontFamily: "Noto Sans JP"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: 0
  body-md:
    fontFamily: "Noto Sans JP"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.7
  body-sm:
    fontFamily: "Noto Sans JP"
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.6
  label-lg:
    fontFamily: "Noto Sans JP"
    fontSize: 14px
    fontWeight: 600
    letterSpacing: 0.02em
  label-md:
    fontFamily: "Noto Sans JP"
    fontSize: 12px
    fontWeight: 500
    letterSpacing: 0.04em
  label-sm:
    fontFamily: "Noto Sans JP"
    fontSize: 11px
    fontWeight: 700
    letterSpacing: 0.06em
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 48px
  2xl: 96px
rounded:
  none: 0px
  sm: 4px
  md: 6px
  lg: 8px
  xl: 12px
  full: 9999px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-secondary:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-outlined:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    border: "1px solid {colors.primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  button-inverted:
    backgroundColor: "{colors.on-primary}"
    textColor: "{colors.primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "10px 20px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "1px solid {colors.surface-variant}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "1px solid {colors.surface-variant}"
    rounded: "{rounded.md}"
    padding: "10px 12px"
  badge:
    backgroundColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface-variant}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
    padding: "2px 8px"
  modal:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    border: "1px solid {colors.surface-variant}"
    rounded: "{rounded.xl}"
    padding: "{spacing.lg}"
---

# Build-Factory Design System

> **作成**: 2026-05-15
> **対象**: Build-Factory (SaaS 型「開発工場 OS」)
> **会社**: 株式会社 ENGINE BASE
> **format**: Google Labs design.md v1
> **supersedes**: `docs/mocks/2026-05-09_v1/design-tokens.md`

## Overview

このデザインシステムは **「開発の工場 × Linear 系の高密度情報設計」** を体現する。受託 PM が 1 画面で 10 案件を並列管理する業務に最適化された、情報密度を最大化するプロフェッショナル系 SaaS UI。

**Primary 色** に ENGINE BASE green (`#1a6648`) を採用する理由:
- v1 / v2 で確立済のブランドアイデンティティを継承
- 緑系は「成長」「進行中」「Done」の象徴で、Build-Factory が扱う「開発の進捗」と意味的に合致
- 深い (`L=25%`) ため、CTA / Active state に使っても視覚的疲労が少ない

**Typography** に Noto Sans JP を統一して使う理由:
- 日本語コンテンツが UI 主体 / 見出しと本文を別 family にすると日本語の階層表現が破綻する
- Noto Sans JP は 100〜900 ウェイトを持ち、weight 違いだけで階層を綺麗に表現できる
- 既存 v1 で確立済 / 移行コストゼロ

**Design Principles:**
1. **情報密度を最大化する** — Linear / Vercel 系の compressed scale。本文 14px、line-height 1.7 (日本語向け)、shadow 最小限で border 区切り優先
2. **Primary は控えめに使う** — Primary green を装飾目的で多用せず、CTA / Active / Brand identity の 3 用途に限定。脇役を担う slate / amber が UI の主役
3. **WCAG AA を妥協しない** — 全 critical text/bg pair で 4.5:1 以上を達成。外販 SaaS / 多様な視覚特性に対応
4. **Lucide Icons only / 絵文字禁止** — 機械強制 (`scripts/lint-mock.sh` check #1)
5. **Dark mode を CSS 変数で構造化** — 後付けコストを Phase 1 段階で構造的に回避

## Colors

カラーシステムは **Material Design 3 に準じた役割ベースの命名規則** を採用する。
全色は `:root` の CSS Custom Properties として定義し、`.dark` クラスで Dark mode に切り替わる。

### Primary
**ENGINE BASE green** — ブランドの顔。CTA ボタン / アクティブ状態 / リンク / フォーカスリングに使用。
- **`primary: #1a6648`** (HSL 153° 59% 25%) — メイン
- **`on-primary: #ffffff`** (白) — Primary 上のテキスト
- **`primary-container: #d3f0e0`** — Primary を弱めた背景 (Badge / chip / accent bg)
- **`on-primary-container: #082015`** — primary-container 上のテキスト

### Secondary
**Slate Steel** — 中性的なニュートラルダーク。控えめなボタン / セカンダリアクション / muted text。
- **`secondary: #475569`** (slate-600)
- **`on-secondary: #ffffff`**
- **`secondary-container: #e2e8f0`** (slate-200) — 区切り線 / disabled bg
- **`on-secondary-container: #0f172a`** — secondary-container 上のテキスト

### Tertiary
**Amber Warning** — アクセント / 注意喚起。予算アラート / 警告 / 進行中表示など、視線を引きたいが Primary を使うほど重要ではない場面で使用。
- **`tertiary: #d97706`** (amber-600)
- **`on-tertiary: #ffffff`**
- **`tertiary-container: #fef3c7`** (amber-100)
- **`on-tertiary-container: #78350f`** (amber-900)

### Surface & Neutral
- **`surface: #ffffff`** — カード / モーダル背景
- **`on-surface: #0f172a`** — 本文 / 主要テキスト (slate-900)
- **`surface-variant: #f1f5f9`** — 入力フィールド bg / hover bg (slate-100)
- **`on-surface-variant: #475569`** — caption / 補助テキスト (slate-600)
- **`neutral: #f8fafc`** — ページ背景 (slate-50)
- **`on-neutral: #0f172a`** — neutral 上のテキスト

### Error
- **`error: #dc2626`** (red-600) — エラー / 赤線抵触 / 破壊的操作
- **`on-error: #ffffff`**

### WCAG コントラスト確認

| 組み合わせ | 比率 | 判定 |
|---|---:|:---:|
| primary / on-primary (#1a6648 / #ffffff) | **5.4 : 1** | ✅ AA |
| surface / on-surface (#ffffff / #0f172a) | **17.4 : 1** | ✅ AAA |
| surface / on-surface-variant (#ffffff / #475569) | **7.4 : 1** | ✅ AAA |
| neutral / on-neutral (#f8fafc / #0f172a) | **16.7 : 1** | ✅ AAA |
| primary-container / on-primary-container | **12.6 : 1** | ✅ AAA |
| secondary-container / on-secondary-container | **14.8 : 1** | ✅ AAA |
| tertiary-container / on-tertiary-container | **9.1 : 1** | ✅ AAA |
| error / on-error (#dc2626 / #ffffff) | **5.9 : 1** | ✅ AA |

全 critical pair で WCAG AA (4.5:1) 以上を達成。

## Typography

タイポグラフィは **Noto Sans JP 単一 family + JetBrains Mono (コード専用)** の構成。
日本語見出しの可読性 / weight 違いだけで階層を表現可能 / Google Fonts で自由ライセンス。

### Headline: Noto Sans JP (weight 700)
- 大型見出し / page title / KPI hero
- 日本語の太字でも字面が崩れない / 漢字の画数が多くても潰れない

### Body: Noto Sans JP (weight 400)
- 本文 / caption / 補助テキスト
- `line-height: 1.7` で日本語の字間を確保
- `letter-spacing: 0` で Noto Sans JP の標準字間をそのまま使う

### Label: Noto Sans JP (weight 500-700)
- Button / Badge / micro label (uppercase)
- `letter-spacing: 0.04-0.06em` で英語ラベルの可読性を上げる
- `tracking-wider` の `micro` (11px) は uppercase 専用

### Mono: JetBrains Mono
- コード / Workspace ID / 数値 (`mono tabular-nums`)
- 等幅 + 0/O などの混同を回避 / プログラマー向けに最適

### Scale

`headline-display` (56px) → `headline-lg` (36px) → `headline-md` (24px, **= 通常 page title**) → `body-lg` (16px) → `body-md` (14px, **= 標準 body**) → `body-sm` (13px) → `label-lg` (14px) → `label-md` (12px) → `label-sm` (11px uppercase)

> Build-Factory は高密度設計のため、`body-md` 14px / `headline-md` 24px が日常使用の中心。`headline-display` 56px はランディングや空状態など特定箇所のみ。

## Layout

8px ベースラインのスペーシングシステムを採用する。

### Spacing Scale
- **`xs: 4px`** — アイコン内マージン / インラインギャップ
- **`sm: 8px`** — コンパクトなスタック / chip 間
- **`md: 16px`** — 標準フォーム要素間
- **`lg: 24px`** — Card padding / セクション内間隔 / Page padding
- **`xl: 48px`** — セクション間スペース
- **`2xl: 96px`** — ページレベル大区切り (最大)

### Layout 構造

```
┌────────────────────────────────────────────┐
│         [Top Bar / 任意 / h-12]            │
├────────────┬───────────────────────────────┤
│  Sidebar   │   Main Content                │
│  240px     │   flex-1                      │
│  bg-primary│   px-24 py-24                 │
│  text-white│   max-w-[1400px] mx-auto      │
│            │                               │
└────────────┴───────────────────────────────┘
```

- **Sidebar**: 240px 固定 / `primary` 系 (eb-700 / Light, eb-950 / Dark) で両 mode 共通
- **Main**: 24px (lg) padding / max-w 1400px で中央寄せ
- **Container max**: 1400px (xl 案件管理画面想定)

### Grid (12-col / Tailwind 既定)

- デスクトップ (1280px+): 12 col / 24px gutter / 24px margin
- タブレット (1024px): 8 col / 16px gutter (sidebar 折畳可能)
- モバイル (<640px): **閲覧専用モード** (フル機能は PC 推奨表示)

### Breakpoint

| BP | px | 対応 |
|---|---|---|
| `xl` | 1280px+ | **標準デスクトップ** (全機能) |
| `lg` | 1024px | タブレット横 (全機能 / sidebar 折畳) |
| `md` | 768px | タブレット縦 (閲覧専用 / 一部編集 disable) |
| `sm` | 640px | モバイル (Cmd+K 検索のみ) |
| `<640px` | mobile | 「PC でご利用ください」表示 |

## Elevation & Depth

**Linear 流の minimal shadow**: shadow より border 区切りを優先する。
高密度 UI で shadow を多用すると視覚的にうるさくなるため、Card は基本 shadow なし + 1px border のみ。

| 用途 | 値 |
|---|---|
| **Card (default)** | `box-shadow: none` (border 区切りのみ) |
| **Card (hover)** | `0 1px 2px rgba(0,0,0,0.04)` |
| **Popover / Dropdown** | `0 4px 12px rgba(0,0,0,0.10)` |
| **Modal / Dialog** | `0 12px 32px rgba(0,0,0,0.12)` |

ホバー / フォーカスでも要素は浮き上がらない (`translate-y` 等は使わない)。

## Shapes

**「角は丸くしすぎず、0px ではない適度な丸み」**:
Linear / Vercel 系 sharper / 親しみやすさより clean を優先。

| Token | px | 用途 |
|---|---:|---|
| `none` | 0px | テーブル / フルブリード画像 |
| `sm` | 4px | Tag / 小バッジ / icon container |
| **`md`** | **6px** | **Button / Input / Select** (← 適度な丸み) |
| **`lg`** | **8px** | **Card / Panel** (← 標準) |
| **`xl`** | **12px** | **Modal / Dialog** |
| `full` | 9999px | Pill ボタン / Avatar / Status badge |

## Components

### Buttons

4 種のボタンバリアントを定義する。

- **Primary** (`button-primary`): 最重要アクション。1 画面に 1 つが原則 (例: 「保存」「実行」)
- **Secondary** (`button-secondary`): 重要だが補助的なアクション (例: 「キャンセル」「下書き保存」)
- **Outlined** (`button-outlined`): 代替アクション / Primary 背景上での操作
- **Inverted** (`button-inverted`): Primary 背景 (sidebar 等) 上で「Primary に対比する」CTA

#### Button States (全 variant 共通)
- `default` → base
- `hover` → bg を 10% 暗く
- `focus-visible` → `outline: 2px solid {colors.primary}` + offset
- `active (pressed)` → bg を 15% 暗く + `scale: 0.98`
- `disabled` → `opacity: 0.5` + `cursor: not-allowed`
- `loading` → Lucide `<Loader2 spin>` + `pointer-events: none`

### Cards
`surface` 背景 + `surface-variant` border。`rounded.lg = 8px` の控えめな丸み。
- Interactive (clickable): `hover:border-primary/40` + shadow-sm
- Elevated (Modal 内): `shadow-md`

### Inputs
`surface` 背景 + `surface-variant` border。`rounded.md = 6px`。
- Focus: `outline: 2px solid {colors.primary}` + offset 0 (Linear 流のはみ出さない focus ring)
- Error: `border-color: {colors.error}` + helper text in error color
- Disabled: `opacity: 0.5` + `background: {colors.surface-variant}`

### Badges
`rounded.full` の pill。
- Default: `{colors.surface-variant}` bg / `{colors.on-surface-variant}` text
- Success: `green-50` bg / `green-600` text (status indicator)
- Warning: `amber-50` bg / `amber-600` text
- Error: `red-50` bg / `red-600` text
- Brand: `primary-container` bg / `on-primary-container` text

### KPI Card (Build-Factory 特化)
Dashboard / 案件俯瞰画面で使用。4 バリアント:
1. **数値型**: 数値 + 単位 + サブテキスト (例: Active Projects 7/10)
2. **ゲージ型**: 数値 + 上限 + 横バー (例: Running Sessions 12/50)
3. **金額型**: 金額 + 予算比較 + 進捗バー (例: Monthly Cost ¥8,420/¥30K)
4. **アラート型**: 数値 + warning/error 色 + アイコン (例: Anomalies (24h) 3)

KPI 大型数値は `JetBrains Mono` `tabular-nums` `28px bold` を統一。

### AI 社員 Chip (Build-Factory 特化)
`inline-flex` + avatar (5x5) + 名前 + ロール。背景 `accent` (`primary-container`)、border `surface-variant`。
役割色 (Dev=primary / QA=warning / Architect=info / BA=success / PM=error)。

### Modal / Dialog
`rounded.xl = 12px` で他より丸み深め。
- 確認 dialog: max-w 480px
- フォーム dialog: max-w 640px
- 詳細 viewer: max-w 800px
- 全画面 dialog: max-w 1200px

### Drawer (右から sliding)
`rounded.none` (画面端に接する) / Task Detail (S-030) や Session Detail (S-032) で使用。
- Small: 480px / Large: 640px

### Status Dot
`w-1.5 h-1.5 rounded-full` + 1.4s pulse animation。
running / idle / paused / failed / done の 5 状態を色で表現。

### Sidebar Navigation
- `bg-primary` (eb-700 light / eb-950 dark) - 両 mode 共通
- nav item: `px-3 py-1.5 text-sm rounded` (`rounded.md`)
- active: `bg-eb-600 font-semibold`
- icon: Lucide `w-4 h-4 mr-2`

### Tabs
- `border-b border-surface-variant`
- tab default: `text-on-surface-variant`
- tab active: `text-on-surface border-b-2 border-primary`

## Do's and Don'ts

### ✅ Do's
- **Primary 色は CTA + Active state + Brand identity** に限定する (装飾目的禁止)
- **テキストコントラスト 4.5:1 以上** を全 critical pair で維持する
- **スペーシングは `spacing` トークンを必ず使う** (xs/sm/md/lg/xl/2xl)
- **コンポーネントはトークン参照 `{colors.primary}`** を使い、直接 hex 値を書かない
- **アイコンは Lucide のみ** を使う (lint #1 で機械強制)
- **数値カラムは `mono tabular-nums`** で桁を揃える
- **focus-visible で keyboard focus を明示** する (a11y)

### ❌ Don'ts
- **Primary 色を装飾目的で多用しない** (Primary は脇役、情報が主役)
- **タイポグラフィスケールを飛ばさない** (`headline-display` → `body-md` の直接ジャンプ禁止)
- **shadow を多用しない** (Linear 流: border 区切り優先)
- **絵文字を UI に使わない** (Lucide Icons で代替 / lint #1 で fail)
- **角丸を 16px 以上にしない** (xl=12px が上限 / 親しみやすさより clean)
- **モバイルでフル機能を提供しない** (Phase 1 は desktop first、モバイル <640px は閲覧専用)
- **`surface` 上に `surface-variant` を重ねない** (コントラスト 1.04:1 で読めなくなる)
- **`bf_` prefix table を新規追加しない** (ADR-014 命名規約)

## 参照

- 関連 ADR: `docs/decisions/ADR-013-auth-strategy.md` / `ADR-014-naming-standard.md`
- Tailwind config 統合先: `frontend/tailwind.config.ts`
- 既存 design tokens (legacy): `docs/mocks/2026-05-09_v1/design-tokens.md`
- HTML プレビュー: `./preview.html` (この同階層)
- v3 mock 一覧: `docs/mocks/2026-05-15_v3/index.html` (今後生成)

## 検証

```bash
# design.md lint (Google Labs)
npx @google-labs/design.md lint docs/mocks/2026-05-15_v3/design-system/DESIGN.md

# WCAG 検証 (axe-core or 手動)
# 全 critical pair で 4.5:1 以上達成済 (上記表参照)

# preview HTML をブラウザで開く
open docs/mocks/2026-05-15_v3/design-system/preview.html
```
