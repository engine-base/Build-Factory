# Build-Factory — CLAUDE.md (セッション引き継ぎ書)

> **このファイルは Claude Code が新セッション起動時に自動で読み込む。**
> 実装・モック追加・仕様変更を始める前に必ずここを確認すること。
> このリポジトリは **Build-Factory** 専用。`~/Documents/company-dashboard` (AI 社員システム) とは別物なので混同しないこと。

---

## 1. プロジェクト概要 (1 段落)

**Build-Factory** は、株式会社 ENGINE BASE (代表: 高本まさと) が開発する **SaaS 型「開発工場 OS」**。
ヒアリング → 要件定義 → アーキ設計 → 機能分解 → タスク分解 → 実装 → テスト → 進捗管理 → 納品 までを **1 つの Web アプリ**で完結させ、**1 人で 10 案件を並列運用**する。実行者は人ではなく **AI 社員 (BMAD 10 ペルソナ)**。
顧客像: 受託会社 / 中小企業の社内開発チーム / フリーランス。Phase 1 は ENGINE BASE 内製で dogfood、Phase 2 で外部 SaaS 公開。

---

## 2. 現在のフェーズ進捗 (2026-05-10)

| # | フェーズ | 状態 | 成果物 |
|---|---|---|---|
| 1 | ヒアリング | ✅ 完了 | `docs/hearing/2026-05-09_re-hearing/` (v2.1) |
| 2 | 要件定義 | ✅ 完了 | `docs/requirements/2026-05-09_v1/` (Must 34 項目) |
| 3 | アーキ設計 | ✅ 完了 | `docs/architecture/2026-05-09_v1/` (7 層 / 43 entities) |
| 4 | 機能分解 | ✅ 完了 | `docs/functional-breakdown/2026-05-09_v1/` (43 screens / 30 features / 6 roles) |
| 5 | 技術選定 | ✅ 完了 | `docs/tech-stack/2026-05-09_v1/` (OSS license verified) |
| 6 | 機能依存分解 | ✅ 完了 | `docs/feature-decomposition/2026-05-09_v1/` (Sprint 0-7) |
| 7 | タスク分解 | ✅ 完了 | `docs/task-decomposition/2026-05-09_v1/` (113 tasks) |
| 8 | 画面モック | ✅ 完了 | `docs/mocks/2026-05-09_v1/` (43/43 HTML) |
| 9 | **実装** | ⏳ **次フェーズ** | - |
| 10 | レビュー / 納品 | 未着手 | - |

**「最初に読むファイル」** → [`docs/HANDOVER.md`](docs/HANDOVER.md) (全フェーズ成果物の統合インデックス)
**「実装着手手順」** → [`docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md`](docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md) (タスクごとの 7 ステップ SOP・必須遵守)

---

## 3. 主要な技術選定 (確定)

### Frontend
- **Next.js 15** (App Router) + **shadcn/ui** + **Tailwind CSS 4**
- **Lucide Icons** (アイコン唯一の選択肢、絵文字禁止) — `docs/mocks/2026-05-09_v1/design-tokens.md` §8
- **Recharts** (チャート) / **React Flow** (DAG / Swarm) / **Zustand** (state) / **TanStack Query** (data)
- **GrapesJS core (BSD-3)** = HTML エディタ (Phase 1.5、Studio SDK は不採用)

### Backend
- **FastAPI** モジュラーモノリス (13+ ドメインモジュール) + Python 3.13 + **uv** + **ruff** + **pyright**
- **SQLAlchemy 2.0 async** + Pydantic
- **bootstrap 済み** : 40 routers + 50 services + 8 Supabase migrations → REUSE/REFACTOR で活用 (新規最小化)

### DB / Auth
- **Supabase Postgres** + **RLS** + **pgvector** + **pg_trgm** + **pgsodium**
- **pg_cron** + **pg_partman** (Phase 2)
- **Supabase Auth** (GoTrue) + 2FA (TOTP) + OAuth (Anthropic / Slack / GitHub)

### AI Stack (5 層)
1. **LangGraph** = オーケストレータ (handoff / guardrails / sessions)
2. **LiteLLM** = プロバイダ抽象化 (Anthropic / OpenAI / 他)
3. **claude-agent-sdk** = subprocess 経由で Claude Code を呼ぶ
4. **Anthropic Agent Teams** = Claude Code 内の Plan / Gen / Eval
5. **openai/codex (Apache 2.0)** = 参照のみ (依存しない)
   - OpenAI Agents SDK / openai-python は LiteLLM 経由のみで、直接依存しない

### Memory (3 tier — Claude API 流 compaction)
- **Short**: `chat_threads` / `chat_messages` (生ログ)
- **Mid**: `chat_messages` 圧縮 + `audit_logs` + 9-section 構造化サマリー (95% コンテキスト時に自動)
- **Long**: **Mem0** (ベクトル) + **Obsidian** (Markdown) + **Constitution** (松本の判断基準)
- **3-tier compaction** : tool result trim + prompt cache (`cache_control: ephemeral` 5 min) + 95% で structured summary

### AI 社員 (BMAD 10 ペルソナ + 拡張)
- **secretary** (松本の複製、別リポ `~/.claude/skills/secretary/`)
- **mary** (BA) / **preston** (PM) / **winston** (Architect) / **sally** (PO) / **devon** (Dev) / **quinn** (QA) / **reviewer**
- **brand** / **mockup** / **curator (logan)** = Phase 1
- Phase 1.5 leaders: **sam / dani / quinn-lead / logan**
- Phase 2: **COO / CFO / CMO / Sales / CS** (まだ作らない)

### Hosting (Phase 1 = ¥0/月)
- **Vercel Hobby** (Frontend) — 自動 HTTPS / プレビュー環境
- **Oracle Cloud Free Tier** (Backend、4 vCPU + 24GB RAM 永久無料)
- **Supabase Free** (DB / Auth / Storage)
- **Sentry / Better Stack / GitHub Actions** = Free tier
- **Cloudflare Tunnel** = Backend を Vercel から呼ぶ
- 月額: ¥125 (ドメインのみ)

### Sandbox (OS レベル)
- macOS: **Seatbelt** / Linux: **Landlock + seccomp** (Codex CLI 流)
- Bash 実行は sandbox 経由のみ

### EARS notation (受け入れ条件の必須形式)
全 acceptance_criteria は次の 5 形式のいずれか:
1. **UBIQUITOUS** : The system **shall** ...
2. **EVENT-DRIVEN** : When [event], the system **shall** ...
3. **STATE-DRIVEN** : While [state], the system **shall** ...
4. **OPTIONAL** : Where [feature is enabled], the system **shall** ...
5. **UNWANTED** : If [unwanted condition], the system **shall not** ...

---

## 4. タスク全体像

- **総タスク数**: 113 件 (104 features + 8 integration tests + 1 audit)
- **ラベル分布**: REUSE 14 / REFACTOR 50 / NEW 49 / ARCHIVE 9
- **クリティカルパス** (順番に着手):
  ```
  T-019-01 → T-S0-13 → T-001-01 → T-001-02 → T-001-04 → T-001-06
   → T-S0-08 → T-S0-09 → T-021-03 → T-020-02 → T-003-02 → T-M28-01
  ```
- 詳細: `docs/task-decomposition/2026-05-09_v1/tickets.html` (Kanban カード形式)
- 113 件全件に対し **REFACTOR タスクは v2.1 適合チェック (9 項目)** を必ず実施

---

## 5. 絶対ルール (お作法)

### 5.1 アイコン (絶対遵守)
- **Lucide Icons のみ使用** (`design-tokens.md` §8)
- **絵文字は禁止** (🔍 📄 ▶︎ 等)
- 例: `<i data-lucide="play" class="w-3.5 h-3.5"></i>`
- CDN: `<script src="https://unpkg.com/lucide@latest"></script>` + `lucide.createIcons()`

### 5.2 デザイン
- 主色: **ENGINE BASE green** = `#1a6648` (Tailwind 上は `eb-500`)
- フォント: **Noto Sans JP** + **JetBrains Mono** (mono クラス)
- shadcn/ui コンポーネントを最優先 (独自 UI は最小化)

### 5.3 コード品質
- **EARS 形式 AC** = 全 task の `acceptance_criteria` で必須
- **TypeScript strict** + **pyright strict**
- **テストカバレッジ ≥ 70%** (Phase 1 ゲート)
- **既存実装 (bootstrap) は REUSE/REFACTOR ラベルで活用** (新規追加は本当に必要な場合のみ)

### 5.4 セキュリティ / レッドライン (即セッション kill)
- **本番 DB に `DROP` / `TRUNCATE` / `DELETE *`** = 即セッション kill
- **`.env` / 鍵ファイル のコミット** = git pre-commit + GitHub secret scanning
- **`--no-verify` / `--force push` (公開後)** = 明示承認時のみ
- **AGPL ライセンス依存追加** = 自動レビューキュー → 不採用が原則 (SaaS 提供のため)

### 5.5 Kanban / タスク管理
- **S-027 Kanban は機能別アコーディオン構造** (Hermes 流フラット 6 列 ❌)
- 各機能内で 4 列: **Todo / In Progress / Review / Done**
- 進行中の機能のみデフォルト展開、完了済みは折りたたみ

### 5.6 モック (43 画面、`docs/mocks/2026-05-09_v1/`)
- 全モックに `<meta name="screen-id|feature-id|task-ids|entities|phase">` を埋め込み済み
- 実装時は **対応モック + 仕様書 + ER 図 + タスクカード** をクロス参照
- **モック修正は S-023 経由** (GUI/AI/HTML 編集 → 新バージョン保存)

---

## 6. 直近セッションで決まったこと (2026-05-09 〜 2026-05-10)

| 日時 | 内容 |
|---|---|
| 05-09 | プロジェクト全 8 フェーズの再ヒアリング → 確定 |
| 05-09 | 113 タスクに圧縮 (152 → 113、REUSE 活用) |
| 05-09 | 43 画面モック A+D ハイブリッド戦略で完成 |
| 05-10 | **S-027 Kanban を機能別アコーディオンに再設計** (フラット 6 列廃止) |
| 05-10 | **S-023 に GUI / AI / HTML 編集モード追加** (M-5b) |
| 05-10 | **絵文字 175 件 → Lucide Icons に一括置換** |
| 05-10 | **CLAUDE.md / HANDOVER.md / ADR 整備** (このファイル含む) |
| 05-10 | **実装プロトコル + lint script + Hook 整備** (機械的強制レイヤー) |
| 05-10 | **M-31 / ADR-009 / templates/project-bootstrap/ 追加**: Build-Factory が回す各案件にも強制レイヤーを自動展開する仕組み (T-BTSTRAP-01〜06、6 タスク) |

ADR は `docs/decisions/` に 9 件残っている (主要技術判断の根拠)。
**強制レイヤー**: `scripts/lint-mock.sh` + `scripts/validate-tickets.py` + `.claude/settings.json` (PostToolUse hook + permissions deny)

---

## 7. 次にやること (実装フェーズ着手手順)

新セッションが最初にやるべき手順:

```bash
# 1. このファイル + 統合インデックスを読む
cat CLAUDE.md
cat docs/HANDOVER.md

# 2. ブラウザで全 43 画面のモックを視覚確認 (任意)
open docs/mocks/2026-05-09_v1/index.html

# 3. 113 タスクを確認
open docs/task-decomposition/2026-05-09_v1/tickets.html

# 4. クリティカルパス先頭から実装開始
# T-019-01 (platform-base ARCHIVE: onlook 削除) を最初に
# → T-S0-13 (Sprint 0 scaffold) → T-001-01 (FastAPI モジュラーモノリス基盤)
```

実装は claude-runner (LangGraph + claude-agent-sdk) 経由で並列起動 (Swarm) する設計だが、**Phase 1 着手時点ではまだ Swarm 機能が無い** ので、最初の Sprint 0 タスクは **手動で Claude Code から実行** する。

---

## 8. ディレクトリ構造

```
~/Documents/Build-Factory/             ← このリポジトリ
├── CLAUDE.md                          ← このファイル (新セッション自動読み込み)
├── README.md                          ← Bootstrap 環境セットアップ手順
├── backend/                           ← FastAPI (40 routers + 50 services 既存)
├── frontend/                          ← Next.js 15 (scaffold 済み)
├── data/                              ← Supabase migrations (8 件)
├── mocks/                             ← (旧) 元設計時のモック (参照のみ)
├── onlook/ penpot/                    ← (削除予定: T-019-01 ARCHIVE)
├── templates/                         ← 各案件に展開する強制レイヤーテンプレ (M-31)
│   ├── project-bootstrap/             ← 新案件作成時に自動配置されるスケルトン
│   └── CHANGELOG.md                   ← テンプレ更新履歴 (更新時に全案件へ伝播)
├── scripts/
│   ├── lint-mock.sh                   ← 絵文字 / AGPL / メタ検証
│   └── validate-tickets.py            ← tickets.json EARS AC 検証
└── docs/                              ← 全フェーズ成果物
    ├── HANDOVER.md                    ← 統合インデックス
    ├── decisions/                     ← ADR (技術判断記録)
    ├── hearing/2026-05-09_re-hearing/
    ├── requirements/2026-05-09_v1/
    ├── architecture/2026-05-09_v1/
    ├── functional-breakdown/2026-05-09_v1/
    ├── tech-stack/2026-05-09_v1/
    ├── feature-decomposition/2026-05-09_v1/
    ├── task-decomposition/2026-05-09_v1/
    └── mocks/2026-05-09_v1/           ← 43 HTML mocks + index.html
```

---

## 9. 環境

- **GitHub repo**: `engine-base/Build-Factory`
- **作業ブランチ**: `claude/project-overview-planning-McQUW` (現在)
- **main**: 未マージ (実装着手前にマージ予定)
- **DB**: Supabase (まだ未接続) → Phase 1 着手時に作成
- **Hosting**: Vercel + Oracle Cloud (Phase 1 着手時にセットアップ)

---

## 10. 別セッションで起動した時の確認コマンド

```bash
# このファイルが Build-Factory 用か確認
grep -c "Build-Factory" CLAUDE.md       # 5+ なら OK
grep -c "company-dashboard\|PM2" CLAUDE.md  # 0 なら OK (混入してない)

# フェーズ完了状況を可視化
ls docs/                                 # 8 つの phase ディレクトリ + HANDOVER.md
ls docs/mocks/2026-05-09_v1/             # 43 HTML

# git 履歴で直近セッションの追加を確認
git log --oneline -10

# 実装着手前の必須チェック (機械的強制)
bash scripts/lint-mock.sh                # 絵文字 / AGPL / ARCHIVE 残留 / tickets.json メタ検証
python3 scripts/validate-tickets.py      # クリティカルパス 12 件のメタ完備確認
```

### 自動 Hook (`.claude/settings.json`)
- **SessionStart**: 「CLAUDE.md と HANDOVER.md を読め」と stderr に出力
- **PostToolUse (Edit/Write)**: 編集ファイルに絵文字混入したら警告
- **PostToolUse (Bash)**: `git commit/push` 前に lint 推奨、`--no-verify` / `--force` は警告
- **Permissions**: `git push --force` / `--no-verify` 系は **deny** で機械的に拒否

---

## 11. 質問・判断保留時の動き

- **重大変更 (DB schema / 主要パッケージ追加 / 5 層 AI スタック変更 / Phase 1 ゲート緩和)** = 必ず masato (高本まさと) に確認
- **軽微変更 (UI 修正 / 文言 / バグ修正 / テスト追加)** = 自走 OK、git commit で報告
- **不明点** = 仮置き禁止、`AskUserQuestion` で確認

---

**最終更新: 2026-05-10**
**責任者: 高本まさと (masato@engine-base.com) / 株式会社 ENGINE BASE**
