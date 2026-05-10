# Build-Factory 画面モック v1.0（2026-05-09）

このフォルダは **F-005b 画面モック自動生成** + **M-5b パイプライン**の人間出力版を保管します。

## 進め方（A + D ハイブリッド）

```
Step 1: 共通基盤（design-tokens / flow-map / component-catalog / index）
   ↓
Step 2: 重要 10 画面を高品質モック（Phase 1 dogfood の中核体験）
   ↓
Step 3: 残り 33 画面をカテゴリ別に順次（mock-tracker.json で進捗管理）
```

## 閲覧方法

ブラウザで以下を開いてください：

```
file:///home/user/Build-Factory/docs/mocks/2026-05-09_v1/index.html
```

`index.html` から全 43 画面に navigate 可能。各モックには：
- 該当機能 ID（F-XXX）と仕様書へのリンク
- 関連タスク（T-XXX）
- 関連エンティティ
- サンプルデータ + interactive demo

## ファイル構成

```
docs/mocks/2026-05-09_v1/
├── README.md                ← このファイル
├── index.html               ← 全 43 画面のナビゲーション
├── design-tokens.md         ← カラー / タイポ / コンポーネント
├── flow-map.html            ← 画面遷移マップ（SVG）
├── component-catalog.html   ← 再利用部品カタログ
├── mock-tracker.json        ← 43 画面の進捗管理
├── auth/                    ← S-001〜005 (5 画面)
├── account/                 ← S-006〜011 (6 画面)
├── workspace/               ← S-012〜015 (4 画面)
├── moat/                    ← S-016〜019 (4 画面)
├── spec/                    ← S-020〜026 (7 画面)
├── task/                    ← S-027〜032 (6 画面)
├── review/                  ← S-033〜035 (3 画面)
├── ai/                      ← S-036〜038 (3 画面)
├── ops/                     ← S-039〜041 (3 画面)
└── client/                  ← S-042〜043 (2 画面)
```

## 実装時の参照パターン

distributed-dev で各タスクを Claude Code に渡す際、以下をセット：

```yaml
implementation_references:
  spec_html: docs/requirements/2026-05-09_v1/requirements-v1.html
  spec_md: docs/requirements/2026-05-09_v1/requirements-v1.md
  feature_breakdown: docs/functional-breakdown/2026-05-09_v1/screens.json
  task_card: docs/task-decomposition/2026-05-09_v1/tickets.json
  mock_html: docs/mocks/2026-05-09_v1/{category}/S-XXX-{name}.html  ← 重要！
  architecture: docs/architecture/2026-05-09_v1/architecture-v1.md
  er_diagram: docs/architecture/2026-05-09_v1/er-diagram-v1.html
```

各モック HTML 内にも以下のメタを埋込み：

```html
<meta name="bf-feature-id" content="F-XXX">
<meta name="bf-screen-id" content="S-XXX">
<meta name="bf-spec-link" content="../../requirements/2026-05-09_v1/requirements-v1.html#FXXX">
<meta name="bf-task-ids" content="T-XXX-01,T-XXX-02">
```

## 改訂履歴
- **v1.0**（2026-05-09）：A+D ハイブリッド進行・43 画面 / 10 critical 優先
