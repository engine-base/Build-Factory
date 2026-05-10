# ADR-009: 各案件への強制レイヤー自動展開 (project-bootstrap-enforcement)

- **Status**: Accepted
- **Date**: 2026-05-10
- **Deciders**: 高本まさと

## Context

Build-Factory 自体の開発で、以下の **機械的強制レイヤー** を整備した:

- `CLAUDE.md` (新セッション自動読み込み)
- `docs/HANDOVER.md` (全成果物統合インデックス)
- `docs/decisions/` ADR (技術判断記録)
- `docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md` (7 ステップ SOP)
- `scripts/lint-mock.sh` (絵文字 / AGPL / ARCHIVE / メタ検証)
- `scripts/validate-tickets.py` (EARS AC / mock_link / spec_link 検証)
- `.claude/settings.json` (PostToolUse hook + permissions deny)
- tickets.json への EARS AC + mock_link + spec_link メタ完備

これにより「読まれて意識される」レベルから「機械的に強制される」レベルに引き上がった。

**しかし**、Build-Factory が回す **各案件 (受託 EC #4 / 内製 SaaS #2 / etc.)** では、この強制レイヤーが自動で展開されない。
案件ごとに同じ品質を担保するには、**新案件作成時にこのレイヤーを自動配置**する必要がある。

### 何が起きるか (放置した場合)
- 案件 A は CLAUDE.md なし → Claude Code が方向性を見失う
- 案件 B は EARS AC なし → 実装範囲が曖昧、テスト網羅不能
- 案件 C は Lucide 規約なし → 絵文字が混入してデザイン破綻
- 案件 D は AGPL 検出なし → 知らないうちに license 違反のままリリース
- 全案件で同じ品質を期待できない → Build-Factory の価値毀損

### 要件
- **新案件作成 (workspace 新規作成) 時に、強制レイヤー一式を自動配置**
- **既存案件にも遡及適用 (migrate)**
- **テンプレート更新時に全案件に通知 + diff 提示**

## Decision

### 1. テンプレートディレクトリを Build-Factory リポジトリ内に保持

```
templates/project-bootstrap/
├── CLAUDE.md.j2                       # Jinja2 テンプレート
├── docs/
│   ├── HANDOVER.md.j2
│   ├── decisions/
│   │   └── README.md
│   └── task-decomposition/
│       └── IMPLEMENTATION_PROTOCOL.md
├── scripts/
│   ├── lint-mock.sh                   # 共通ロジック (汎用版)
│   └── validate-tickets.py            # 共通ロジック (汎用版)
└── .claude/
    └── settings.json
```

### 2. 新案件作成フローに組み込む

```
[案件作成 UI] → POST /api/workspaces
   ↓
WorkspaceService.create():
   1. workspaces レコード作成
   2. GitHub repo 作成 (engine-base/proj-{slug})
   3. テンプレート展開:
       - templates/project-bootstrap/* を repo に配置
       - {{プレースホルダ}} を案件メタで置換
         · {{project_name}}, {{client_name}}, {{deadline}},
         · {{phase}}, {{tech_stack}}, {{ai_employees}}
   4. 初回 commit ("chore: bootstrap project from template v{X}")
   5. main ブランチ push
   6. CLAUDE.md の自動読み込みが効く状態に
   ↓
[Phase 1 ヒアリング開始]
```

### 3. 既存案件への遡及適用 (migrate)

```bash
# CLI コマンド
build-factory project migrate --workspace=ws_8f3a2c

# 動作:
# 1. 既存 repo を fetch
# 2. テンプレート最新版と diff
# 3. 不足ファイルのみ追加 (既存ファイルは上書きしない、conflict なら手動マージ)
# 4. PR 作成 ("chore: migrate to project-template v{X}")
```

### 4. テンプレート更新時の伝播

```
templates/project-bootstrap/ を更新
   ↓
[CI] 全案件に対し migrate dry-run 実行
   ↓
影響範囲を集計 (変更されるファイル数 / 案件数)
   ↓
masato 承認
   ↓
[CI] 全案件に PR 自動作成 (各案件の owner にレビュー依頼)
```

### 5. 強制レイヤーの構成要素 (案件ごと)

| ファイル | 役割 | 自動展開 |
|---|---|---|
| `CLAUDE.md` | プロジェクト固有の引き継ぎ書 (テンプレ + メタ埋め込み) | ✅ |
| `docs/HANDOVER.md` | 案件の成果物インデックス | ✅ |
| `docs/decisions/` | 案件固有の ADR (空ディレクトリ + README) | ✅ |
| `docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md` | 共通 SOP (Build-Factory 版を継承) | ✅ |
| `scripts/lint-mock.sh` | 共通 lint (絵文字 / AGPL / メタ検証) | ✅ |
| `scripts/validate-tickets.py` | tickets.json メタ検証 | ✅ |
| `.claude/settings.json` | Hook + permissions deny | ✅ |
| `tickets.json` | 案件のタスクリスト (Phase 1 ヒアリング後に AI が埋める) | ✅ (空テンプレ) |
| `mocks/` | 案件のモック (Phase 4 で AI が生成) | ✅ (空ディレクトリ) |

## Consequences

### 得られるもの
- ✅ 全案件で同じ品質基準 (EARS AC / Lucide / 70% カバレッジ等)
- ✅ Claude Code が新案件 repo に入った瞬間にコンテキスト把握
- ✅ 機械的に違反を弾く (絵文字 / AGPL / メタ不足)
- ✅ Build-Factory のテンプレ更新が全案件に伝播 → 改善が複利で効く
- ✅ 案件ごとの独立性 (各案件 repo の `decisions/` は案件固有)

### 諦めるもの
- ❌ テンプレ更新コスト: 全案件への伝播時に conflict が出る → migrate コマンド + dry-run で軽減
- ❌ 新案件作成が遅くなる (テンプレ展開で 5-10 秒): UX 上は許容範囲、案件作成は頻度低い
- ❌ テンプレが「縛り」になり過ぎる懸念 → 案件側の `decisions/ADR-XXX-deviation.md` で逸脱を正当化可能

### 検討した代替案
- **A. 各案件で手動コピペ** = 漏れが起きる、不採用
- **B. Git submodule で共有** = 案件側で更新コントロールが面倒、不採用
- **C. (今回採用) Jinja2 テンプレート + 自動展開 + migrate コマンド**

### 関連
- 影響を受ける機能: F-003 workspace_management の新案件作成フロー
- 影響を受けるタスク: T-BTSTRAP-01 〜 T-BTSTRAP-06 (6 件、新規追加)
- 要件: M-31 project_bootstrap_enforcement (新規)
