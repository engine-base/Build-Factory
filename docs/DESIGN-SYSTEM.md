# Build-Factory デザインシステム
**Calm Industrial — 業務 SaaS の信頼感 × 開発ツールのキレ × 日本語の余白**

このドキュメントは BF Workspace IA モック (2026-05) で確立したデザイン言語を、再利用可能な形で記録するものです。今後の高本まさとプロダクトのデフォルトスタイルとして使えます。

---

## 1. デザイン哲学（5 原則）

### 原則 1: **Tonal Hierarchy（階調による情報整理）**
影や色の数で目立たせるのではなく、**白〜薄グレーの 5 階層 + テキスト 4 階層**で情報の重みを表現する。

- 背景: `#FFFFFF` → `#F8FAFC` → `#F5F7FA` → `#F1F5F9`
- テキスト: `#0F172A` → `#334155` → `#64748B` → `#94A3B8`

→ 見るだけで「メイン情報 / 補足 / メタ / 装飾」が分かる。SmartHR / Linear / Notion 共通の流儀。

### 原則 2: **Border Over Shadow（影より境界線）**
影は最小限。`box-shadow` は使わず、`1px solid #E4E8EE` の境界線で領域を区切る。

- 影なし = 視覚ノイズなし = 業務 SaaS の信頼感
- ホバー時のみ `border-color` を変える（影をふわっと出さない）

### 原則 3: **Compact but Breathable（密度高めだが息苦しくない）**
業務 SaaS は情報量が多い。余白を取りすぎると「中身がない」、詰めすぎると「読めない」。

- 行の高さは 1.5〜1.7
- 隣接要素間は 8px / 12px / 16px の倍数
- カードのパディングは 16〜20px

### 原則 4: **Semantic Tokens（意味のある名前）**
`--blue-500` ではなく `--primary`、`--gray-700` ではなく `--text-1`。  
意味で命名するとブランド色を変えても破綻しない。

### 原則 5: **No Emoji, Lucide Only（絵文字禁止・SVG アイコン統一）**
プロダクト UI に絵文字は使わない。すべて Lucide の SVG。  
理由: ブランドの一貫性 + 環境差での見え方を統制 + プロ感。  
AI 社員アバターは 1 文字（秘 / PM / 設 / デ / エ / 品 / 運）+ カラー識別。

---

## 2. デザイントークン

### カラー

```css
/* 背景階層 (明るい順) */
--bg-base:    #FFFFFF;  /* 最前面 (カード表面) */
--bg-elev:    #FFFFFF;  /* カード本体 */
--bg-soft:    #F8FAFC;  /* やわらかい区切り */
--bg-app:     #F5F7FA;  /* アプリ全体背景 */
--bg-input:   #F8FAFC;  /* フォーム入力 */

/* テキスト階層 (濃い順) */
--text-1:     #0F172A;  /* 見出し・最重要 */
--text-2:     #334155;  /* 本文 */
--text-3:     #64748B;  /* 補足・キャプション */
--text-4:     #94A3B8;  /* プレースホルダ・装飾 */

/* 境界線 */
--border:        #E4E8EE;  /* 標準 */
--border-strong: #CBD3DC;  /* hover・focus */
--divider:       #EEF1F5;  /* 内部の区切り (薄め) */

/* ブランド (BF ブルー) */
--primary:       #004CD9;
--primary-hover: #0040B8;
--primary-bg:    #E8EFFE;  /* 選択中の背景 */
--primary-soft:  #F2F6FF;  /* focus ring */

/* セマンティック (各 fg + bg のペアで) */
--success: #15803D;  --success-bg: #DCFCE7;
--warning: #B45309;  --warning-bg: #FEF3C7;
--danger:  #B91C1C;  --danger-bg:  #FEE2E2;
--info:    #0369A1;  --info-bg:    #E0F2FE;
--neutral: #475569;  --neutral-bg: #F1F5F9;
```

→ **fg/bg のペア運用**が要点。`color: var(--success)` だけだと弱いので、必ず `background: var(--success-bg)` とセットで badge / pill にすると、業務 SaaS らしい安心感の出る色運びになる。

### スペーシング (8px 基準)

```css
--space-1: 4px;    /* インライン極小 */
--space-2: 8px;    /* アイコン横の余白 */
--space-3: 12px;   /* 行間 */
--space-4: 16px;   /* 標準 */
--space-5: 20px;   /* セクション内 */
--space-6: 24px;   /* セクション間 */
--space-8: 32px;   /* 大ブロック */
--space-10: 40px;  /* ページ内側余白 */
--space-12: 48px;  /* ページ最外側 */
```

ルール: **整数倍規則**を守る。`13px` `15px` 等の中途半端な値を使わない。視覚が揃う。

### 角丸

```css
--radius-sm: 4px;   /* タグ・コードブロック */
--radius-md: 6px;   /* ボタン・入力欄 */
--radius-lg: 8px;   /* カード */
--radius-xl: 12px;  /* モーダル・大ブロック */
```

業務 SaaS は **控えめな角丸 (4-8px)** が信頼感に繋がる。`16px+` だとカジュアル寄り。

### タイポグラフィ

```css
font-family: 'Inter', 'Noto Sans JP', sans-serif;

/* 主要サイズ */
font-size: 11px   → メタ・タイムスタンプ
         12.5px  → サブ情報
         13px    → 標準本文
         14px    → 強調本文・小見出し
         15px    → 見出し
         18-22px → ページタイトル
         32px    → ヒーロー

/* ウェイト */
400  → 通常
500  → 軽い強調 (リンク・タブ)
600  → 強調 (見出し・ボタン)
700  → 最強調 (ページタイトル・KPI 数値)

/* レターSpacing */
通常:    0
見出し:  -0.01 〜 -0.02em (引き締め)
ラベル:  +0.04 〜 +0.08em (大文字・タグで広げる)

/* line-height */
本文:    1.5 〜 1.7
見出し:  1.1 〜 1.25
タイト: 1
```

→ 見出しは **マイナス letter-spacing** で引き締まる。これだけでぐっとプロ感が出る。

---

## 3. レイアウトパターン

### アプリシェル (3 ペイン)

```
┌──────────────────────────────────────┐
│ Header (56px)                        │
├──────────────┬───────────────────────┤
│ Sidebar      │ Main                  │
│ (264px)      │ (flex: 1)             │
│              │                       │
│ - 階層型     │ padding: 32px 40px    │
│ - 固定       │ overflow-y: auto      │
│ - 薄グレー bg │                       │
└──────────────┴───────────────────────┘
```

CSS:
```css
.app {
  display: grid;
  grid-template-columns: 264px 1fr;
  grid-template-rows: 56px 1fr;
  grid-template-areas: "header header" "sidebar main";
  height: 100vh;
}
```

### サイドバー (3 セクション構成)

```
[← 戻る]
[プロジェクトカード]    ← bg: white, border: 1px

━ プロジェクト管理 ━
ホーム / 進捗 / タスク / ...

━ 開発フロー ━            ← AI 大分類 (アコーディオン)
リーダー名 + アバター + 状態ドット
  └ サブ項目 (展開時)

━ 管理 ━
メンバー / 共有 / 設定
```

各セクションタイトルは:
```css
font-size: 10.5px;
font-weight: 700;
letter-spacing: 0.08em;
text-transform: uppercase;
color: var(--text-4);
```

### 2 ペイン (リスト + 詳細)

議事録 / メール風画面で使用:
```
┌─────────┬──────────────────┐
│ List    │ Detail           │
│ 360px   │ flex: 1          │
└─────────┴──────────────────┘
gap: 20px
```

### グリッド (3 カラム / 4 カラム)

```css
.grid-2 { display: grid; grid-template-columns: 1.4fr 1fr; gap: 20px; }
.grid-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 20px; }
.grid-4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 20px; }
```

`1.4fr 1fr` の **黄金比寄り** が、左メイン + 右サブの自然なバランス。

---

## 4. コンポーネントパターン

### カード（最頻出）

```html
<div class="card">
  <div class="card-header">
    <h2><Icon /> タイトル</h2>
    <span class="card-header-meta">補足</span>
  </div>
  <div class="card-body">...</div>
</div>
```

```css
.card {
  background: var(--bg-elev);
  border: 1px solid var(--border);
  border-radius: 8px;
  overflow: hidden;
}
.card-header {
  padding: 14px 20px;
  border-bottom: 1px solid var(--divider);  /* 薄い区切り */
  display: flex; justify-content: space-between; align-items: center;
}
.card-body { padding: 16px 20px; }
```

→ ヘッダーとボディの **境界線は --divider (薄)**、外周は **--border (標準)** で階層を作る。

### ボタン (3 階層)

```css
/* Primary: 主要アクション (1 画面 1 つ) */
.btn-primary { background: var(--primary); color: #fff; }

/* Secondary: 補助アクション */
.btn-secondary {
  background: white;
  color: var(--text-1);
  border: 1px solid var(--border);
}

/* Ghost: 第三選択肢・キャンセル */
.btn-ghost { background: transparent; color: var(--text-2); }
```

共通: `height: 34px; padding: 0 14px; border-radius: 6px; font-size: 13px; font-weight: 600;`

→ **3 段階を超えない**。Primary/Secondary/Ghost で 99% カバー。

### バッジ (Status / Pill)

```css
.badge {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 600;
}
.badge.success { background: var(--success-bg); color: var(--success); }
.badge.warn    { background: var(--warning-bg); color: var(--warning); }
.badge.danger  { background: var(--danger-bg); color: var(--danger); }
```

→ **fg + bg ペア + radius:999 (pill) + small padding** が業務 SaaS の鉄板。

### フォーム

```css
.form-input {
  height: 40px;
  padding: 0 12px;
  background: var(--bg-input);
  border: 1px solid var(--border);
  border-radius: 6px;
  font-size: 13px;
}
.form-input:focus {
  border-color: var(--primary);
  background: white;
  box-shadow: 0 0 0 3px var(--primary-soft);  /* focus ring */
}
.form-label {
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
  margin-bottom: 6px;
}
```

→ **focus ring を 3px の薄い primary-soft** で出すのが SmartHR / Linear 流。`outline` ではなく `box-shadow` で柔らかく。

### サイドバーアイテム (active 状態)

```css
.sidebar-item.active {
  background: var(--primary-bg);
  color: var(--primary);
  font-weight: 600;
}
.sidebar-item.active::before {
  content: '';
  position: absolute; left: -12px;
  top: 6px; bottom: 6px;
  width: 3px;
  background: var(--primary);
  border-radius: 0 2px 2px 0;
}
```

→ **左に 3px のアクセントバー** で「今ここ」を強く示す。Linear / Notion 共通。

### テーブル (横罫線のみ)

```css
.table th {
  background: var(--bg-soft);
  padding: 10px 20px;
  font-size: 11.5px;
  font-weight: 600;
  color: var(--text-3);
  text-transform: uppercase;
  letter-spacing: 0.04em;
  border-bottom: 1px solid var(--border);
}
.table td {
  padding: 12px 20px;
  border-bottom: 1px solid var(--divider);
  font-size: 13px;
}
.table tr:hover td { background: var(--bg-soft); }
```

→ **縦罫線なし、横罫線のみ**で読みやすさが格段に上がる。SmartHR の真髄。

### AI アバター

```css
.leader-avatar {
  width: 22px; height: 22px;
  border-radius: 4px;  /* 円ではなく角丸 (キャラ感を抑える) */
  display: flex; align-items: center; justify-content: center;
  color: #fff;
  font-weight: 700;
  font-size: 10px;
  letter-spacing: 0.02em;
}
.leader-secretary { background: #6366F1; }   /* Indigo */
.leader-pm        { background: #0EA5E9; }   /* Sky */
.leader-arch      { background: #2563EB; }   /* Blue */
.leader-design    { background: #DB2777; }   /* Pink */
.leader-eng       { background: #16A34A; }   /* Green */
.leader-qa        { background: #CA8A04; }   /* Amber */
.leader-ops       { background: #DC2626; }   /* Red */
```

→ **円ではなく角丸 (4px)** にすることで「キャラクター感」を抑え業務感を保つ。色は HSL 配色で互いに離れるよう選定。

---

## 5. 階層の作り方（Visual Hierarchy）

### ページ構造の階層

```
Page Title (22px, weight 700, -0.01em)
  └ Page Subtitle (13px, --text-3)
      └ DAG Progress / Action Bar
          └ Section Card (--bg-elev)
              ├ Card Header (14px, weight 700)
              ├ Card Body
              │   └ Row Item (13px, --text-1)
              │       └ Meta (11px, --text-3)
              └ Card Footer (border-top dashed)
```

→ サイズ・ウェイト・色 の 3 軸で 5〜6 段階の階層を作る。**1 画面に強調色 (Primary) は 3 箇所まで** がルール。

### 強調の優先順位

1. **位置** (左上 > 中央 > 右下) — 最も強い
2. **サイズ** (大 > 小)
3. **ウェイト** (700 > 600 > 500 > 400)
4. **色のコントラスト** (text-1 > text-2 > text-3)
5. **背景色** (Primary > Soft > White)
6. **アニメーション・装飾** — 最も弱い

→ 強調したい時はまず **位置とサイズ** で勝負する。色やアイコンに頼らない。

---

## 6. インタラクション

### Hover

```css
/* デフォルト */
transition: border-color 120ms, background 120ms;

/* カード・ボタン */
:hover { border-color: var(--border-strong); /* または primary */ }

/* 行 */
tr:hover td { background: var(--bg-soft); }
```

→ **120〜160ms の短いトランジション**が SmartHR / Linear 流。長すぎると鈍い。

### Focus

```css
:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-soft);
  outline: none;
}
```

### Active (押下感)

ボタンに `:active { transform: translateY(0.5px); }` を入れると気持ち良いが、**業務 SaaS ではあまり使わない** (誤操作の不安を減らすため)。

### Loading

```css
@keyframes spin { to { transform: rotate(360deg); } }
.icon-loading { animation: spin 800ms linear infinite; }
```

ストライプアニメ (進行中バー):
```css
.in-progress {
  background-image: linear-gradient(45deg,
    rgba(255,255,255,0.18) 25%, transparent 25%,
    transparent 50%, rgba(255,255,255,0.18) 50%,
    rgba(255,255,255,0.18) 75%, transparent 75%);
  background-size: 14px 14px;
  animation: stripe 1.2s linear infinite;
}
```

→ プログレスバー / DAG ノードに **subtle なストライプ** を入れると「動いている」感が出る。

---

## 7. アンチパターン (やってはいけないこと)

| ❌ NG | 理由 |
|---|---|
| 絵文字を UI に使う | 一貫性が崩れる・環境で見え方が違う |
| 半端なサイズ (13px・15px・21px 等) | 8px 倍数規則を壊す |
| 影で目立たせる (`box-shadow: 0 4px 16px`) | 業務 SaaS には騒がしい |
| Primary 色を装飾で多用 | 重要なものが目立たなくなる |
| 角丸 12px+ をボタンに使う | カジュアル寄りになる、業務感が抜ける |
| 縦罫線あるテーブル | 圧迫感、読みづらい |
| カラーパレットが多い (10+ 色) | ブランド統一感が崩れる |
| アイコンとテキストの gap が `var(--space-2)` 以下でない | アイコンが寄り添ってない |
| ホバー時に大きく動く (transform: scale 等) | 業務向けには過剰 |
| `font-weight: bold` (太字) | 700 を超える太さは見出し以外で使わない |
| カラーを `#XXX` のリテラルで書く | トークン崩壊、テーマ切替不可 |

---

## 8. このスタイルの源流（参考にした SaaS）

| 借りた要素 | 元 | 採用理由 |
|---|---|---|
| **余白の取り方 / 業務 SaaS 王道のレイアウト** | SmartHR | 日本 B2B SaaS の最高峰。クライアントに見せて安心感がある |
| **テーブル・フォーム・権限管理 UI の構造** | SmartHR | 業務系の鉄板パターン |
| **サイドバー (active バー / アコーディオン)** | Linear | 開発者向け SaaS の世界基準 |
| **コマンドパレット (Cmd+K)** | Linear | 操作の高速化 |
| **アニメーションの短さ・速度感** | Linear | プロ向けプロダクト感 |
| **AI 社員のキャラ感・親しみやすさ** | esa.io | 日本らしい温度 |
| **AI 提案カードの見せ方** | Magic Moment Playbook | AI ネイティブ感 |

ブレンド比率: **SmartHR 70% + Linear 15% + esa 10% + Magic Moment 5%**

---

## 9. 再利用するときのチェックリスト

新しいプロダクト / 画面を作る時、このスタイルが守れているか:

- [ ] 背景は `--bg-app` (薄グレー)、カードは `--bg-elev` (白)
- [ ] テキストは `--text-1` 〜 `--text-4` の 4 段階に収まっている
- [ ] 境界線は `1px solid --border`、影は使わない
- [ ] 角丸は 4 / 6 / 8 / 12px のいずれか
- [ ] 余白はすべて 8px 倍数
- [ ] フォントは Inter + Noto Sans JP
- [ ] アイコンは Lucide のみ、絵文字ゼロ
- [ ] ボタンは Primary / Secondary / Ghost の 3 階層
- [ ] Status は fg + bg のペアで pill 形式
- [ ] Active 状態は左 3px のアクセントバー + `--primary-bg` 背景
- [ ] Hover は 120ms の `border-color` 変化
- [ ] Focus は 3px の `--primary-soft` リング
- [ ] テーブルは縦罫線なし、横罫線のみ
- [ ] サイドバーは 264px、ヘッダーは 56px
- [ ] Primary 色は 1 画面 3 箇所以下
- [ ] AI アバターは 1 文字 + カラー識別 + 角丸 4px

---

## 10. ファイル構成 (BF モック)

```
frontend/public/mock/
├ _shared.css        ← デザイントークン + 共通コンポーネント
├ _partials.js       ← ヘッダー + サイドバーの共有 HTML
├ index.html         ← モック一覧メニュー
├ workspace-home.html
├ leader-pm.html     ← AI 大分類画面 (代表)
├ progress.html      ← DAG + ガント
├ tasks.html         ← Kanban
├ client-home.html   ← クライアント限定ビュー
├ new-project.html   ← 新規導入
├ members.html       ← メンバー + 権限マトリクス
├ minutes.html       ← 議事録 (2 ペイン)
├ alerts.html        ← 通知センター
├ schedule.html      ← マイルストーン + カレンダー
└ settings.html      ← 設定 (左 nav + 右コンテンツ)
```

すべて `_shared.css` を `<link rel="stylesheet" href="./_shared.css" />` で読み込み。

---

## 11. 実装移行時の指針

このモックを React/Next.js コードに落とし込む時:

1. **トークン**: `_shared.css` の CSS 変数を `globals.css` にコピー（既存 BF の `--eb-*` を置換 / 統合）
2. **コンポーネント分割**:
   - `<AppShell>` (ヘッダー + サイドバー + メイン)
   - `<Sidebar>` (3 セクション固定 + propsで active 制御)
   - `<Card>` `<CardHeader>` `<CardBody>` (slot 構造)
   - `<Button>` (variant: primary/secondary/ghost)
   - `<Badge>` (variant: success/warn/danger/info/recommend/parallel)
   - `<LeaderAvatar>` (1文字 + カラー)
   - `<DagProgress>` (13 セグメント横棒)
   - `<NextActionCard>` (推奨マーク + 3 ボタン)
3. **ライブラリ採用**:
   - **shadcn/ui** ベース → カスタマイズで上記トークンを適用
   - **BlockNote** → 議事録 / 要件定義 / 仕様書編集 (Notion 風体験)
   - **cmdk** → コマンドパレット (Cmd+K)
   - **@dnd-kit** → タスク Kanban のドラッグ
   - **React Flow** → 進捗管理画面の DAG ビジュアル
   - **Lucide** → 既に採用、継続
   - **TanStack Query / Table** → 既に採用、継続

---

このスタイルを「**Calm Industrial**」と命名し、高本まさとプロダクトのデフォルトスタイルとする。

最終更新: 2026-05-04
