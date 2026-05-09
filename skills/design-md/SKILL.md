---
name: design-md
description: Google Labs design.md仕様準拠のデザインシステムスキル。ブランド情報をもとにYAMLフロントマター+Markdownボディの完全なDESIGN.mdを生成し、カラーパレット・タイポグラフィ・コンポーネントを視覚化するHTMLプレビューファイルを同時出力する。「デザインシステムを作りたい」「DESIGN.mdを作りたい」「カラーパレットを設計したい」「ブランドのデザイントークンを作りたい」「タイポグラフィを設計したい」「UIコンポーネントのスタイルを決めたい」「デザイン基盤を作りたい」という場面で起動する。出力は ~/Documents/会社運営DB/records/06_ブランディング/design-system/ に保存する。
tab: ブランディング
builtin: true
---
---

## 🧠 全スキル共通：思考品質基準（必ず守ること）

---

### 出力フォーマット厳守（最優先ルール）

**スキルモードで動作している場合、出力の冒頭に会話的な前置きを絶対に含めない。**

❌ **禁止：**「ありがとうございます」などの会話的前置き  
✅ **正しい出力：** テンプレートの要素から直接開始する

---

# design-md スキル

## このスキルの役割

あなたは **デザインシステムアーキテクト** として動く。

Google Labs の [design.md 仕様](https://github.com/google-labs-code/design.md) に完全準拠した `DESIGN.md` ファイルを生成し、同時にカラーパレット・タイポグラフィ・コンポーネントを視覚化する **HTML プレビューファイル** を出力する。

**出力される2ファイル：**
1. `DESIGN-{name}.md` — machine-readable & human-readable デザイン仕様書
2. `DESIGN-{name}-preview.html` — 視覚化プレビュー（カラースウォッチ・タイポグラフィ・コンポーネント）

---

## ⛔ 絶対ルール

1. **YAML フロントマターは google-labs-code/design.md スキーマに完全準拠する**
2. **カラーは必ず WCAG AA コントラスト比（4.5:1 以上）を確認する**
3. **すべてのコンポーネントは `{path.to.token}` 参照構文を使う**
4. **HTMLプレビューは外部依存なしの単一ファイルで生成する（Google Fonts CDN のみ許可）**
5. **カラースウォッチは Primary/Secondary/Tertiary/Neutral の4列グリッドで視覚化する**
6. **タイポグラフィは実際のフォントで "Aa" サンプルを表示する**
7. **完了時に必ず両ファイルを保存する**

---

## design.md スキーマ仕様

### 必須 YAML トークン

```yaml
---
name: {デザインシステム名}
colors:
  # Primary（主色）
  primary: "#hex"
  on-primary: "#hex"
  primary-container: "#hex"
  on-primary-container: "#hex"
  # Secondary（副色）
  secondary: "#hex"
  on-secondary: "#hex"
  secondary-container: "#hex"
  on-secondary-container: "#hex"
  # Tertiary（アクセント色）
  tertiary: "#hex"
  on-tertiary: "#hex"
  tertiary-container: "#hex"
  on-tertiary-container: "#hex"
  # Surface（背景・サーフェス）
  surface: "#hex"
  on-surface: "#hex"
  surface-variant: "#hex"
  on-surface-variant: "#hex"
  # Error
  error: "#hex"
  on-error: "#hex"
  # Neutral
  neutral: "#hex"
  on-neutral: "#hex"
typography:
  headline-display:
    fontFamily: "Font Name"
    fontSize: 72px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: "Font Name"
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.01em
  headline-md:
    fontFamily: "Font Name"
    fontSize: 36px
    fontWeight: 600
    lineHeight: 1.25
  body-lg:
    fontFamily: "Body Font"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: 0.01em
  body-md:
    fontFamily: "Body Font"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "Body Font"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  label-lg:
    fontFamily: "Label Font"
    fontSize: 14px
    fontWeight: 600
    letterSpacing: 0.04em
  label-md:
    fontFamily: "Label Font"
    fontSize: 12px
    fontWeight: 500
    letterSpacing: 0.05em
  label-sm:
    fontFamily: "Label Font"
    fontSize: 11px
    fontWeight: 500
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
  md: 8px
  lg: 16px
  xl: 24px
  full: 9999px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  button-secondary:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  button-outlined:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    border: "1.5px solid {colors.primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  button-inverted:
    backgroundColor: "{colors.on-primary}"
    textColor: "{colors.primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
---
```

### Markdown ボディの8セクション（必須順序）

1. **Overview** — デザイン哲学・ビジュアルディレクション
2. **Colors** — カラーパレットと使用方法
3. **Typography** — フォントシステムと階層
4. **Layout** — スペーシングとグリッド
5. **Elevation & Depth** — シャドウとレイヤリング
6. **Shapes** — ボーダーラジウスとジオメトリ
7. **Components** — コンポーネント定義
8. **Do's and Don'ts** — ガイドラインとベストプラクティス

---

## STEP 構成

---

### ▶ STEP 1：デザイン情報のヒアリング

```
## 🎨 DESIGN.md 生成：情報入力

### プロジェクト基本情報
- プロジェクト名・ブランド名：
- 一言でのビジュアルディレクション：
  （例：「都市的ミニマリズム × 温かみのある職人気質」「クリーンな医療×信頼感」）

### カラーパレット

**Primary（主色・ブランドの顔）**
- 色名・イメージ：（例：ディープフォレストグリーン、ネイビーブルー）
- 指定の HEX があれば：

**Secondary（副色・Primary を引き立てる）**
- 色名・イメージ：

**Tertiary（アクセント色・視線誘導・CTA）**
- 色名・イメージ：

**Neutral（背景・テキスト系）**
- 明るい背景色のイメージ：（例：クリーム白、純白、ライトグレー）

### タイポグラフィ

**ヘッドライン用フォント（インパクト重視）：**
（例：Playfair Display、Newsreader、Space Grotesk、Raleway）

**ボディ用フォント（可読性重視）：**
（例：Noto Serif、Inter、Source Sans 3、Lato）

**ラベル用フォント（UI要素・ボタン用）：**
（上記と同じでも可）

### スタイル傾向
- 角丸：角ばり（0-4px）/ 標準（8px）/ 丸め（16px以上）/ 完全丸（pill型）
- 全体の雰囲気：ラグジュアリー / ナチュラル / テック / ポップ / ミニマル / その他
```

**⛔ STEP 1を出力したら止まる。情報入力後「生成して」とお知らせください。**

---

### ▶ STEP 2：DESIGN.md + HTML プレビューの生成

受け取った情報をもとに、以下の手順で生成する。

#### Step 2-1：カラートークンの導出

ユーザーが指定した主色から、Material Design 3のカラーシステムに準じた派生色を導出する：

```
Primary（入力値）→ 暗め50%で primary-container
On-Primary = コントラスト比4.5:1以上になる白または黒
On-Primary-Container = primary の明るい版でコントラスト確保
Surface = Neutral の最も明るい値
On-Surface = Surface に対してコントラスト比7:1以上
```

#### Step 2-2：DESIGN.md の生成

以下のフォーマットで完全な DESIGN.md を生成する：

```markdown
---
name: {プロジェクト名}
colors:
  primary: "{hex}"
  on-primary: "{hex}"
  primary-container: "{hex}"
  on-primary-container: "{hex}"
  secondary: "{hex}"
  on-secondary: "{hex}"
  secondary-container: "{hex}"
  on-secondary-container: "{hex}"
  tertiary: "{hex}"
  on-tertiary: "{hex}"
  tertiary-container: "{hex}"
  on-tertiary-container: "{hex}"
  surface: "{hex}"
  on-surface: "{hex}"
  surface-variant: "{hex}"
  on-surface-variant: "{hex}"
  error: "#ba1a1a"
  on-error: "#ffffff"
  neutral: "{hex}"
  on-neutral: "{hex}"
typography:
  headline-display:
    fontFamily: "{ヘッドラインフォント}"
    fontSize: 72px
    fontWeight: 700
    lineHeight: 1.1
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: "{ヘッドラインフォント}"
    fontSize: 48px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.01em
  headline-md:
    fontFamily: "{ヘッドラインフォント}"
    fontSize: 36px
    fontWeight: 600
    lineHeight: 1.25
  body-lg:
    fontFamily: "{ボディフォント}"
    fontSize: 18px
    fontWeight: 400
    lineHeight: 1.7
    letterSpacing: 0.01em
  body-md:
    fontFamily: "{ボディフォント}"
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.6
  body-sm:
    fontFamily: "{ボディフォント}"
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  label-lg:
    fontFamily: "{ラベルフォント}"
    fontSize: 14px
    fontWeight: 600
    letterSpacing: 0.04em
  label-md:
    fontFamily: "{ラベルフォント}"
    fontSize: 12px
    fontWeight: 500
    letterSpacing: 0.05em
  label-sm:
    fontFamily: "{ラベルフォント}"
    fontSize: 11px
    fontWeight: 500
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
  md: 8px
  lg: 16px
  xl: 24px
  full: 9999px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  button-secondary:
    backgroundColor: "{colors.secondary-container}"
    textColor: "{colors.on-secondary-container}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  button-outlined:
    backgroundColor: "transparent"
    textColor: "{colors.primary}"
    border: "1.5px solid {colors.primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  button-inverted:
    backgroundColor: "{colors.on-primary}"
    textColor: "{colors.primary}"
    typography: "{typography.label-lg}"
    rounded: "{rounded.md}"
    padding: "12px 24px"
  card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.lg}"
    padding: "{spacing.lg}"
  input:
    backgroundColor: "{colors.surface-variant}"
    textColor: "{colors.on-surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.md}"
---

# {プロジェクト名} Design System

## Overview

{デザイン哲学・ビジュアルディレクションを3〜5文で記述}

このデザインシステムは {ビジュアルディレクション} を体現する。
{Primary色の選択理由}、{タイポグラフィの選択理由}。

**Design Principles:**
1. {原則1}
2. {原則2}
3. {原則3}

## Colors

カラーシステムは Material Design 3 に準じた役割ベースの命名規則を採用する。

### Primary
{Primary色の説明・使用場面}

### Secondary
{Secondary色の説明・使用場面}

### Tertiary
{Tertiary色の説明・使用場面}

### Surface & Neutral
{サーフェス系の説明}

**WCAG コントラスト確認:**
- primary / on-primary: {比率}:1 ✅ AA
- surface / on-surface: {比率}:1 ✅ AA

## Typography

{タイポグラフィの哲学・ペアリングの理由}

### Headline: {フォント名}
{ヘッドラインフォントの特徴・選択理由}

### Body: {フォント名}
{ボディフォントの特徴・選択理由}

### Scale
`headline-display` → `headline-lg` → `headline-md` → `body-lg` → `body-md` → `body-sm` → `label-lg` → `label-md` → `label-sm`

## Layout

8px ベースラインのスペーシングシステムを使用する。

### Spacing Scale
- `xs`: 4px — アイコン内マージン、インラインギャップ
- `sm`: 8px — コンパクトなスタック
- `md`: 16px — 標準コンポーネント内パディング
- `lg`: 24px — カードパディング、セクション内間隔
- `xl`: 48px — セクション間スペース
- `2xl`: 96px — ページセクション間

### Grid
- デスクトップ: 12カラム / 24px ガター / 80px マージン
- タブレット: 8カラム / 16px ガター
- モバイル: 4カラム / 16px ガター

## Elevation & Depth

{エレベーションの説明}

## Shapes

{角丸の哲学と使い分け}

- `none` (0px): テーブル、フルブリード画像
- `sm` (4px): タグ、バッジ
- `md` ({rounded.md}): ボタン、入力フィールド、チップ
- `lg` (16px): カード、モーダル
- `xl` (24px): シート、大型コンテナ
- `full` (9999px): ピル型ボタン、アバター

## Components

### Buttons
4種のボタンバリアントを定義する。

- **Primary**: 最重要アクション。1画面に1つが原則
- **Secondary**: 重要だが補助的なアクション
- **Outlined**: 代替アクション、破壊的操作の確認
- **Inverted**: Primary背景上での使用

### Cards
`surface` 背景に `on-surface` テキスト。`rounded.lg` で柔らかさを演出。

### Inputs
`surface-variant` 背景でフォームフィールドを背景から浮かせる。

## Do's and Don'ts

### ✅ Do's
- Primary色はCTAと最重要UIのみに使用する
- テキストコントラストは常にWCAG AA (4.5:1) 以上を維持する
- スペーシングは必ず `spacing` トークンを使用する
- コンポーネントはトークン参照 `{colors.primary}` を使い、直接hex値を書かない

### ❌ Don'ts
- Primary色を装飾目的で多用しない
- タイポグラフィスケールを飛ばして使わない（display→md のジャンプは禁止）
- カスタム色を追加する際はシステムと整合するコントラスト比を確認する
- `surface` 上に `surface-variant` を重ねてコントラストを下げない
```

#### Step 2-3：HTML プレビューファイルの生成

以下の完全な HTML ファイルを生成する。**すべてのカラー・フォント・コンポーネントの値は実際の設計値に置換すること。**

```html
<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{プロジェクト名} — Design System</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family={ヘッドラインフォントURL}&family={ボディフォントURL}&family={ラベルフォントURL}&display=swap" rel="stylesheet">
<style>
  :root {
    /* === COLOR TOKENS === */
    --color-primary: {primary};
    --color-on-primary: {on-primary};
    --color-primary-container: {primary-container};
    --color-on-primary-container: {on-primary-container};
    --color-secondary: {secondary};
    --color-on-secondary: {on-secondary};
    --color-secondary-container: {secondary-container};
    --color-on-secondary-container: {on-secondary-container};
    --color-tertiary: {tertiary};
    --color-on-tertiary: {on-tertiary};
    --color-tertiary-container: {tertiary-container};
    --color-on-tertiary-container: {on-tertiary-container};
    --color-surface: {surface};
    --color-on-surface: {on-surface};
    --color-surface-variant: {surface-variant};
    --color-on-surface-variant: {on-surface-variant};
    --color-neutral: {neutral};
    --color-on-neutral: {on-neutral};
    --color-error: #ba1a1a;
    --color-on-error: #ffffff;

    /* === TYPOGRAPHY === */
    --font-headline: '{ヘッドラインフォント名}', serif;
    --font-body: '{ボディフォント名}', sans-serif;
    --font-label: '{ラベルフォント名}', sans-serif;

    /* === SPACING === */
    --space-xs: 4px;
    --space-sm: 8px;
    --space-md: 16px;
    --space-lg: 24px;
    --space-xl: 48px;
    --space-2xl: 96px;

    /* === ROUNDED === */
    --rounded-none: 0px;
    --rounded-sm: 4px;
    --rounded-md: {rounded-md}px;
    --rounded-lg: 16px;
    --rounded-xl: 24px;
    --rounded-full: 9999px;
  }

  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--color-surface);
    color: var(--color-on-surface);
    font-family: var(--font-body);
    font-size: 16px;
    line-height: 1.6;
  }

  /* HEADER */
  .ds-header {
    background: var(--color-primary);
    color: var(--color-on-primary);
    padding: var(--space-xl) var(--space-2xl);
  }
  .ds-header h1 {
    font-family: var(--font-headline);
    font-size: 56px;
    font-weight: 700;
    line-height: 1.1;
    letter-spacing: -0.02em;
    margin-bottom: var(--space-sm);
  }
  .ds-header p {
    font-family: var(--font-body);
    font-size: 18px;
    opacity: 0.85;
  }
  .ds-badge {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    background: var(--color-on-primary);
    color: var(--color-primary);
    padding: 6px 12px;
    border-radius: var(--rounded-full);
    font-family: var(--font-label);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: var(--space-lg);
  }

  /* SECTIONS */
  .ds-section {
    padding: var(--space-xl) var(--space-2xl);
    border-bottom: 1px solid var(--color-surface-variant);
  }
  .ds-section-title {
    font-family: var(--font-label);
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.12em;
    text-transform: uppercase;
    color: var(--color-on-surface-variant);
    margin-bottom: var(--space-xl);
    display: flex;
    align-items: center;
    gap: var(--space-sm);
  }
  .ds-section-title::after {
    content: '';
    flex: 1;
    height: 1px;
    background: var(--color-surface-variant);
  }

  /* COLOR PALETTE */
  .color-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: var(--space-md);
  }
  .color-card {
    border-radius: var(--rounded-lg);
    overflow: hidden;
    border: 1px solid rgba(0,0,0,0.06);
  }
  .color-swatch-main {
    height: 120px;
    display: flex;
    align-items: flex-end;
    padding: var(--space-md);
  }
  .color-swatch-main span {
    font-family: var(--font-label);
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.04em;
    opacity: 0.85;
  }
  .color-swatch-row {
    display: flex;
  }
  .color-swatch-sm {
    flex: 1;
    height: 40px;
  }
  .color-card-meta {
    padding: var(--space-md);
    background: var(--color-surface);
  }
  .color-name {
    font-family: var(--font-label);
    font-size: 13px;
    font-weight: 600;
    color: var(--color-on-surface);
    margin-bottom: 4px;
  }
  .color-hex {
    font-family: monospace;
    font-size: 12px;
    color: var(--color-on-surface-variant);
  }

  /* TYPOGRAPHY */
  .type-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-lg);
  }
  .type-card {
    background: var(--color-surface-variant);
    border-radius: var(--rounded-lg);
    padding: var(--space-xl) var(--space-lg);
    min-height: 200px;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
  }
  .type-sample {
    color: var(--color-on-surface);
    line-height: 1.1;
    margin-bottom: var(--space-md);
  }
  .type-meta {
    font-family: var(--font-label);
    font-size: 11px;
    color: var(--color-on-surface-variant);
    letter-spacing: 0.04em;
  }
  .type-scale-name {
    font-family: var(--font-label);
    font-size: 11px;
    font-weight: 700;
    color: var(--color-on-surface-variant);
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: var(--space-sm);
  }

  /* COMPONENTS */
  .component-section {
    margin-bottom: var(--space-xl);
  }
  .component-label {
    font-family: var(--font-label);
    font-size: 11px;
    font-weight: 600;
    color: var(--color-on-surface-variant);
    letter-spacing: 0.06em;
    text-transform: uppercase;
    margin-bottom: var(--space-lg);
  }
  .button-row {
    display: flex;
    align-items: center;
    gap: var(--space-md);
    flex-wrap: wrap;
    margin-bottom: var(--space-xl);
  }

  /* BUTTONS */
  .btn {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 8px;
    padding: 12px 24px;
    border: none;
    cursor: pointer;
    font-family: var(--font-label);
    font-size: 14px;
    font-weight: 600;
    letter-spacing: 0.04em;
    transition: all 0.15s ease;
    border-radius: var(--rounded-md);
  }
  .btn-primary {
    background: var(--color-primary);
    color: var(--color-on-primary);
  }
  .btn-secondary {
    background: var(--color-secondary-container);
    color: var(--color-on-secondary-container);
  }
  .btn-outlined {
    background: transparent;
    color: var(--color-primary);
    border: 1.5px solid var(--color-primary);
  }
  .btn-inverted {
    background: var(--color-on-primary);
    color: var(--color-primary);
  }
  .btn-ghost {
    background: transparent;
    color: var(--color-primary);
  }

  /* CARD EXAMPLES */
  .cards-row {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: var(--space-md);
    margin-bottom: var(--space-xl);
  }
  .demo-card {
    background: var(--color-surface);
    border: 1px solid var(--color-surface-variant);
    border-radius: var(--rounded-lg);
    padding: var(--space-lg);
  }
  .demo-card-primary {
    background: var(--color-primary-container);
    color: var(--color-on-primary-container);
    border: none;
  }
  .demo-card-secondary {
    background: var(--color-secondary-container);
    color: var(--color-on-secondary-container);
    border: none;
  }
  .demo-card h3 {
    font-family: var(--font-headline);
    font-size: 20px;
    font-weight: 600;
    margin-bottom: var(--space-sm);
  }
  .demo-card p {
    font-size: 14px;
    opacity: 0.8;
    line-height: 1.5;
  }

  /* SPACING VISUAL */
  .spacing-row {
    display: flex;
    align-items: flex-end;
    gap: var(--space-xl);
    margin-bottom: var(--space-md);
  }
  .space-block {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-sm);
  }
  .space-visual {
    background: var(--color-primary);
    opacity: 0.7;
    border-radius: var(--rounded-sm);
    width: 40px;
  }
  .space-label {
    font-family: monospace;
    font-size: 11px;
    color: var(--color-on-surface-variant);
    text-align: center;
  }

  /* SHAPES */
  .shapes-row {
    display: flex;
    gap: var(--space-lg);
    flex-wrap: wrap;
    align-items: center;
    margin-bottom: var(--space-xl);
  }
  .shape-demo {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: var(--space-sm);
  }
  .shape-box {
    width: 72px;
    height: 72px;
    background: var(--color-primary-container);
    display: flex;
    align-items: center;
    justify-content: center;
    font-family: var(--font-label);
    font-size: 10px;
    color: var(--color-on-primary-container);
  }

  /* INPUT DEMO */
  .input-demo {
    display: flex;
    flex-direction: column;
    gap: var(--space-sm);
    max-width: 360px;
    margin-bottom: var(--space-xl);
  }
  .input-label {
    font-family: var(--font-label);
    font-size: 12px;
    font-weight: 600;
    color: var(--color-on-surface-variant);
    letter-spacing: 0.04em;
  }
  .input-field {
    background: var(--color-surface-variant);
    color: var(--color-on-surface);
    border: none;
    border-radius: var(--rounded-md);
    padding: var(--space-md);
    font-family: var(--font-body);
    font-size: 16px;
    width: 100%;
  }
  .input-field:focus {
    outline: 2px solid var(--color-primary);
    outline-offset: 0;
  }

  /* DESIGN.MD SOURCE */
  .source-block {
    background: var(--color-on-surface);
    color: var(--color-surface);
    border-radius: var(--rounded-lg);
    padding: var(--space-xl);
    font-family: monospace;
    font-size: 12px;
    line-height: 1.8;
    white-space: pre;
    overflow-x: auto;
    max-height: 480px;
    overflow-y: auto;
  }
  .source-comment { color: #8B9EB0; }
  .source-key { color: #7EC8A0; }
  .source-value { color: #F8C555; }
  .source-string { color: #CE9178; }

  /* WCAG BADGES */
  .wcag-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: var(--space-md);
    margin-bottom: var(--space-xl);
  }
  .wcag-card {
    border-radius: var(--rounded-md);
    padding: var(--space-lg);
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .wcag-info { font-family: var(--font-label); font-size: 12px; }
  .wcag-ratio { font-family: var(--font-headline); font-size: 24px; font-weight: 700; }
  .wcag-pass { color: #1a6b3c; background: #d4edda; }
  .wcag-fail { color: #721c24; background: #f8d7da; }

  /* FOOTER */
  .ds-footer {
    background: var(--color-primary-container);
    color: var(--color-on-primary-container);
    padding: var(--space-xl) var(--space-2xl);
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-family: var(--font-label);
    font-size: 12px;
    letter-spacing: 0.04em;
  }

  @media (max-width: 768px) {
    .color-grid, .type-grid, .cards-row { grid-template-columns: 1fr; }
    .ds-header { padding: var(--space-xl) var(--space-lg); }
    .ds-section { padding: var(--space-xl) var(--space-lg); }
    .ds-header h1 { font-size: 36px; }
    .ds-footer { flex-direction: column; gap: var(--space-md); }
  }
</style>
</head>
<body>

<!-- HEADER -->
<header class="ds-header">
  <div class="ds-badge">
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
    design.md · Google Labs Format
  </div>
  <h1>{プロジェクト名}</h1>
  <p>{ビジュアルディレクション}</p>
</header>

<!-- 1. COLOR PALETTE -->
<section class="ds-section">
  <div class="ds-section-title">Colors</div>

  <div class="color-grid">
    <!-- PRIMARY -->
    <div class="color-card">
      <div class="color-swatch-main" style="background:{primary};">
        <span style="color:{on-primary};">{primary}</span>
      </div>
      <div class="color-swatch-row">
        <div class="color-swatch-sm" style="background:{primary-container};"></div>
        <div class="color-swatch-sm" style="background:{on-primary};"></div>
        <div class="color-swatch-sm" style="background:{on-primary-container};"></div>
      </div>
      <div class="color-card-meta">
        <div class="color-name">Primary</div>
        <div class="color-hex">{primary}</div>
      </div>
    </div>

    <!-- SECONDARY -->
    <div class="color-card">
      <div class="color-swatch-main" style="background:{secondary};">
        <span style="color:{on-secondary};">{secondary}</span>
      </div>
      <div class="color-swatch-row">
        <div class="color-swatch-sm" style="background:{secondary-container};"></div>
        <div class="color-swatch-sm" style="background:{on-secondary};"></div>
        <div class="color-swatch-sm" style="background:{on-secondary-container};"></div>
      </div>
      <div class="color-card-meta">
        <div class="color-name">Secondary</div>
        <div class="color-hex">{secondary}</div>
      </div>
    </div>

    <!-- TERTIARY -->
    <div class="color-card">
      <div class="color-swatch-main" style="background:{tertiary};">
        <span style="color:{on-tertiary};">{tertiary}</span>
      </div>
      <div class="color-swatch-row">
        <div class="color-swatch-sm" style="background:{tertiary-container};"></div>
        <div class="color-swatch-sm" style="background:{on-tertiary};"></div>
        <div class="color-swatch-sm" style="background:{on-tertiary-container};"></div>
      </div>
      <div class="color-card-meta">
        <div class="color-name">Tertiary</div>
        <div class="color-hex">{tertiary}</div>
      </div>
    </div>

    <!-- NEUTRAL / SURFACE -->
    <div class="color-card">
      <div class="color-swatch-main" style="background:{neutral}; border: 1px solid {surface-variant};">
        <span style="color:{on-neutral};">{neutral}</span>
      </div>
      <div class="color-swatch-row">
        <div class="color-swatch-sm" style="background:{surface};"></div>
        <div class="color-swatch-sm" style="background:{surface-variant};"></div>
        <div class="color-swatch-sm" style="background:{on-surface};"></div>
      </div>
      <div class="color-card-meta">
        <div class="color-name">Neutral</div>
        <div class="color-hex">{neutral}</div>
      </div>
    </div>
  </div>

  <!-- WCAG -->
  <div style="margin-top: var(--space-xl);">
    <div class="ds-section-title" style="margin-bottom: var(--space-md);">WCAG Contrast</div>
    <div class="wcag-grid">
      <div class="wcag-card wcag-pass" style="background:{primary}; color:{on-primary};">
        <div class="wcag-info">Primary / On-Primary<br><span style="opacity:0.7">AA ✓ AAA ✓</span></div>
        <div class="wcag-ratio">{contrast-primary}:1</div>
      </div>
      <div class="wcag-card wcag-pass" style="background:{surface}; color:{on-surface}; border: 1px solid {surface-variant};">
        <div class="wcag-info">Surface / On-Surface<br><span style="opacity:0.7">AA ✓</span></div>
        <div class="wcag-ratio">{contrast-surface}:1</div>
      </div>
      <div class="wcag-card wcag-pass" style="background:{secondary-container}; color:{on-secondary-container};">
        <div class="wcag-info">Secondary Container<br><span style="opacity:0.7">AA ✓</span></div>
        <div class="wcag-ratio">{contrast-secondary}:1</div>
      </div>
    </div>
  </div>
</section>

<!-- 2. TYPOGRAPHY -->
<section class="ds-section">
  <div class="ds-section-title">Typography</div>

  <div class="type-grid">
    <div class="type-card">
      <div>
        <div class="type-scale-name">Headline Display</div>
        <div class="type-sample" style="font-family: var(--font-headline); font-size: 64px; font-weight: 700; letter-spacing: -0.02em;">Aa</div>
      </div>
      <div class="type-meta">{ヘッドラインフォント名} · 72px · 700<br>lineHeight: 1.1 · −0.02em</div>
    </div>

    <div class="type-card">
      <div>
        <div class="type-scale-name">Headline LG</div>
        <div class="type-sample" style="font-family: var(--font-headline); font-size: 48px; font-weight: 600; letter-spacing: -0.01em;">Aa</div>
      </div>
      <div class="type-meta">{ヘッドラインフォント名} · 48px · 600</div>
    </div>

    <div class="type-card">
      <div>
        <div class="type-scale-name">Body Main</div>
        <div class="type-sample" style="font-family: var(--font-body); font-size: 36px; font-weight: 400;">Aa</div>
        <div style="font-family: var(--font-body); font-size: 16px; line-height: 1.6; margin-top: 8px; opacity: 0.7;">The quick brown fox jumps over the lazy dog.</div>
      </div>
      <div class="type-meta">{ボディフォント名} · 18px · 400<br>lineHeight: 1.7</div>
    </div>

    <div class="type-card">
      <div>
        <div class="type-scale-name">Headline MD</div>
        <div class="type-sample" style="font-family: var(--font-headline); font-size: 36px; font-weight: 600;">Aa</div>
      </div>
      <div class="type-meta">{ヘッドラインフォント名} · 36px · 600</div>
    </div>

    <div class="type-card">
      <div>
        <div class="type-scale-name">Body SM</div>
        <div class="type-sample" style="font-family: var(--font-body); font-size: 28px; font-weight: 400;">Aa</div>
        <div style="font-family: var(--font-body); font-size: 14px; line-height: 1.5; margin-top: 8px; opacity: 0.7;">Secondary text, captions, supporting information.</div>
      </div>
      <div class="type-meta">{ボディフォント名} · 14px · 400</div>
    </div>

    <div class="type-card">
      <div>
        <div class="type-scale-name">Label</div>
        <div class="type-sample" style="font-family: var(--font-label); font-size: 28px; font-weight: 600; letter-spacing: 0.04em;">Aa</div>
        <div style="font-family: var(--font-label); font-size: 14px; font-weight: 600; letter-spacing: 0.04em; margin-top: 8px; opacity: 0.7; text-transform: uppercase;">BUTTON LABEL</div>
      </div>
      <div class="type-meta">{ラベルフォント名} · 14px · 600 · +0.04em</div>
    </div>
  </div>
</section>

<!-- 3. COMPONENTS -->
<section class="ds-section">
  <div class="ds-section-title">Components</div>

  <!-- Buttons -->
  <div class="component-section">
    <div class="component-label">Buttons</div>
    <div class="button-row">
      <button class="btn btn-primary">Primary</button>
      <button class="btn btn-secondary">Secondary</button>
      <button class="btn btn-outlined">Outlined</button>
      <button class="btn btn-inverted" style="box-shadow: 0 0 0 1px {primary};">Inverted</button>
      <button class="btn btn-ghost">Ghost</button>
    </div>

    <!-- Buttons on Primary bg -->
    <div style="background: var(--color-primary); padding: var(--space-lg); border-radius: var(--rounded-lg); margin-bottom: var(--space-lg);">
      <div style="font-family: var(--font-label); font-size: 11px; color: var(--color-on-primary); opacity: 0.7; letter-spacing: 0.06em; text-transform: uppercase; margin-bottom: var(--space-md);">On Primary Background</div>
      <div class="button-row">
        <button class="btn btn-inverted">Inverted</button>
        <button class="btn btn-outlined" style="color: var(--color-on-primary); border-color: var(--color-on-primary);">Outlined</button>
        <button class="btn btn-ghost" style="color: var(--color-on-primary);">Ghost</button>
      </div>
    </div>
  </div>

  <!-- Cards -->
  <div class="component-section">
    <div class="component-label">Cards</div>
    <div class="cards-row">
      <div class="demo-card">
        <h3>Surface Card</h3>
        <p>Default card using surface background with on-surface text.</p>
        <div style="margin-top: var(--space-md);">
          <button class="btn btn-primary" style="padding: 8px 16px; font-size: 12px;">Action</button>
        </div>
      </div>
      <div class="demo-card demo-card-primary">
        <h3>Primary Container</h3>
        <p>Emphasized card using primary-container color role.</p>
        <div style="margin-top: var(--space-md);">
          <button class="btn" style="background: var(--color-primary); color: var(--color-on-primary); padding: 8px 16px; font-size: 12px;">Action</button>
        </div>
      </div>
      <div class="demo-card demo-card-secondary">
        <h3>Secondary Container</h3>
        <p>Supporting card using secondary-container color role.</p>
        <div style="margin-top: var(--space-md);">
          <button class="btn btn-outlined" style="color: var(--color-secondary); border-color: var(--color-secondary); padding: 8px 16px; font-size: 12px;">Action</button>
        </div>
      </div>
    </div>
  </div>

  <!-- Input -->
  <div class="component-section">
    <div class="component-label">Form Input</div>
    <div class="input-demo">
      <label class="input-label">Field Label</label>
      <input class="input-field" type="text" placeholder="Placeholder text..." />
      <label class="input-label">Search</label>
      <input class="input-field" type="text" placeholder="Search..." />
    </div>
  </div>
</section>

<!-- 4. SPACING -->
<section class="ds-section">
  <div class="ds-section-title">Spacing Scale</div>
  <div class="spacing-row">
    <div class="space-block">
      <div class="space-visual" style="height: 4px;"></div>
      <div class="space-label">xs<br>4px</div>
    </div>
    <div class="space-block">
      <div class="space-visual" style="height: 8px;"></div>
      <div class="space-label">sm<br>8px</div>
    </div>
    <div class="space-block">
      <div class="space-visual" style="height: 16px;"></div>
      <div class="space-label">md<br>16px</div>
    </div>
    <div class="space-block">
      <div class="space-visual" style="height: 24px;"></div>
      <div class="space-label">lg<br>24px</div>
    </div>
    <div class="space-block">
      <div class="space-visual" style="height: 48px;"></div>
      <div class="space-label">xl<br>48px</div>
    </div>
    <div class="space-block">
      <div class="space-visual" style="height: 96px;"></div>
      <div class="space-label">2xl<br>96px</div>
    </div>
  </div>
</section>

<!-- 5. SHAPES -->
<section class="ds-section">
  <div class="ds-section-title">Shapes / Border Radius</div>
  <div class="shapes-row">
    <div class="shape-demo">
      <div class="shape-box" style="border-radius: 0px;">none</div>
      <span class="space-label">none · 0px</span>
    </div>
    <div class="shape-demo">
      <div class="shape-box" style="border-radius: 4px;">sm</div>
      <span class="space-label">sm · 4px</span>
    </div>
    <div class="shape-demo">
      <div class="shape-box" style="border-radius: var(--rounded-md);">md</div>
      <span class="space-label">md · {rounded-md}px</span>
    </div>
    <div class="shape-demo">
      <div class="shape-box" style="border-radius: 16px;">lg</div>
      <span class="space-label">lg · 16px</span>
    </div>
    <div class="shape-demo">
      <div class="shape-box" style="border-radius: 24px;">xl</div>
      <span class="space-label">xl · 24px</span>
    </div>
    <div class="shape-demo">
      <div class="shape-box" style="border-radius: 9999px;">full</div>
      <span class="space-label">full · pill</span>
    </div>
  </div>
</section>

<!-- 6. DESIGN.MD SOURCE -->
<section class="ds-section">
  <div class="ds-section-title">DESIGN.md Source</div>
  <div class="source-block">{DESIGN_MD_SOURCE}</div>
</section>

<!-- FOOTER -->
<footer class="ds-footer">
  <span>{プロジェクト名} Design System · design.md format by Google Labs</span>
  <span>Generated by design-md skill · {今日の日付}</span>
</footer>

</body>
</html>
```

**重要：上記HTMLテンプレートの `{...}` プレースホルダーは全て実際の値に置換してから出力すること。**

---

## 💾 出力ファイル保存（STEP 2完了時に必ず実行）

```bash
PROJ_SLUG=$(echo "{プロジェクト名}" | tr '[:upper:]' '[:lower:]' | sed 's/ /-/g')
SAVE_DIR="$HOME/Documents/会社運営DB/records/06_ブランディング/design-system"
mkdir -p "$SAVE_DIR"

# DESIGN.md の保存
cat > "$SAVE_DIR/DESIGN-${PROJ_SLUG}.md" << 'EOF'
{DESIGN.md全文}
EOF

# HTML プレビューの保存
cat > "$SAVE_DIR/DESIGN-${PROJ_SLUG}-preview.html" << 'EOF'
{HTML全文}
EOF

echo "✅ 保存完了"
echo "📄 DESIGN.md   → $SAVE_DIR/DESIGN-${PROJ_SLUG}.md"
echo "🌐 HTML Preview → $SAVE_DIR/DESIGN-${PROJ_SLUG}-preview.html"
echo ""
echo "プレビューを開く:"
echo "  open '$SAVE_DIR/DESIGN-${PROJ_SLUG}-preview.html'"
```

---

## 完了報告フォーマット

```
---
✅ DESIGN.md + HTML プレビュー生成完了

📄 DESIGN.md：
  ~/Documents/会社運営DB/records/06_ブランディング/design-system/DESIGN-{slug}.md

🌐 HTML プレビュー：
  ~/Documents/会社運営DB/records/06_ブランディング/design-system/DESIGN-{slug}-preview.html

  → ブラウザで開くには：
  open ~/Documents/会社運営DB/records/06_ブランディング/design-system/DESIGN-{slug}-preview.html

🎨 デザイントークン サマリー：
  Primary:    {primary} → on-primary: {on-primary}
  Secondary:  {secondary}
  Tertiary:   {tertiary}
  Surface:    {surface}
  Headline Font:  {ヘッドラインフォント}
  Body Font:      {ボディフォント}

⚠️  WCAG 確認：
  Primary/On-Primary:   {ratio}:1 {AA/AAA} {pass/fail}
  Surface/On-Surface:   {ratio}:1 {AA}     {pass/fail}

design.md lint を実行するには：
  npx @google-labs/design.md lint {DESIGN-slug.md path}
---
```
