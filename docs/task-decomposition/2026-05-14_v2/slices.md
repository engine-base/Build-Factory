# tickets v2 — Slice / Wave / Parallel 構造による再分解 (2026-05-14)

> **既存 tickets.json (`../2026-05-09_v1/tickets.json`) を完全に保持しつつ、
> 各 task に `slice / wave / parallel_group / dogfood_value / unlocks / done_status` を
> 追加した **augmented 版**.**仕様 (M-1〜M-30 / ER / AC / mocks) はゼロ変更**.

> 目的: 「縦スライス × 並列波」で実装順序を明確化し、
> dogfood 駆動 + 並列実行可能性を見える化する.

---

## 全体サマリー

- **total**: 187 task
- **done**: 68 (36.4%)
- **pending**: 119
- **slice**: 8 (S1〜S8)

| Slice | Name | Done | Pending | % | Dogfood acceptance |
|---|---|---:|---:|---:|---|
| **S1** | 認証 + Workspace + テナント階層 | 8 | 26 | 24% | ログインして workspace に入れる / 招待 / 権限 / OAuth で外部 API キー登録 |
| **S2** | AI 社員 + Chat + Memory (3 tier) | 25 | 26 | 49% | workspace 内で AI 社員と会話できる + 短期/中期/長期 memory が回る |
| **S3** | ヒアリング → 要件定義 AI ペルソナ | 4 | 5 | 44% | Mary (BA) がヒアリング, Preston (PM) が要件定義書を出す |
| **S4** | アーキ設計 → 機能分解 → タスク分解 AI | 7 | 5 | 58% | Winston (Architect) → Sally (PO) → Devon (Dev) の連携で 1 案件分が組み立つ |
| **S5** | Kanban + DAG + Phase 管理 + 横断検索 | 9 | 11 | 45% | タスク化 → Kanban で進捗 → DAG で依存可視化 → Cmd+K で横断検索 |
| **S6** | MCP + Reviewer + Constitution 適用 | 8 | 13 | 38% | Quinn (QA/Reviewer) が動く + MCP server 経由で Claude Code に bf tools が見える + red-line 監視 |
| **S7** | Swarm 並列実行 + Worktree (= 靴屋に靴を履かせる) | 2 | 14 | 12% | 1 人の operator が Swarm UI で複数 task を並列実行できる |
| **S8** | GitHub + Slack + Obsidian + 観測 + 監査 + 配信 | 5 | 19 | 21% | PR 自動化 / Slack 通知 / Obsidian エクスポート / Langfuse / 監査ログ / 納品まで完走 |

## 推奨実装順 (Slice 単位)

各 Slice は **dogfood 完成単位** を表す。Slice 完了時に「動く価値」が一つ手に入る。

```
S1 (認証 + Workspace) [基盤]
  ↓
S2 (AI Chat + Memory) [中核]
  ↓ (S2 完了時点で chat-only dogfood が動く ← 最初の milestone)
S3 (ヒアリング AI) → S4 (要件→分解 AI)
  ↓
S5 (Kanban / DAG)
  ↓
S6 (MCP + Reviewer)
  ↓
S7 (Swarm 並列実行) ← 靴を履く!ここから残り task が並列消化
  ↓
S8 (Github / 観測 / 配信) [仕上げ]
```

---

## 各 Slice の詳細

### S1: 認証 + Workspace + テナント階層

**Dogfood 受入基準**: ログインして workspace に入れる / 招待 / 権限 / OAuth で外部 API キー登録

**進捗**: 8/34 done = 23.5%

**Wave 構造** (依存深さ):


#### Wave 1.1 — 3/11 done, 4 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-019-01 | REFACTOR | bootstrap archive 9 ファイル / dirs (onlook + penpot + design- |
| ⏳ | T-021-05 | NEW | self-strip block + owner 保護 (workspace_service.SelfStripEr |
| ⏳ | T-023-02 | REFACTOR | API キー管理 UI (ApiKeysTab + OAuthConnectionsCard + OAuthRow  |
| ⏳ | T-023-03 | REFACTOR | pgsodium 暗号化保管 (encrypted_store.py adapter + encrypted_sec |
| ⏳ | T-023-04 | NEW | OAuth 連携 (Slack/GitHub/Anthropic) (backend/routers/oauth.p |
| ⏳ | T-023-05 | NEW | クローン opt-in toggle + GDPR 削除権 (30 日 grace) (backend/servic |
| ✅ | T-S0-01 | NEW | docker-compose.yml 全サービス (postgres + redis + backend + lit |
| ⏳ | T-S0-02 | NEW | GitHub Actions ci.yml (pytest + coverage + pre-commit-chec |
| ⏳ | T-S0-03 | NEW | license-check.yml (AGPL 防御 + ADR-010 機械的ガード CI 実効化) |
| ✅ | T-S0-05 | REUSE | shadcn/ui setup + Tailwind config (verify existing setup / |
| ⏳ | T-S0-07 | REFACTOR | Supabase FE wrapper (singleton browser client + auth helpe |

#### Wave 1.2 — 1/4 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-019-02 | NEW | modify 対象 GitHub Issue 化 (scanner script + 運用文書 / side-eff |
| ⏳ | T-S0-04 | NEW | deploy-staging.yml (Vercel + Oracle Cloud / Phase 1 ¥0 hos |
| ⏳ | T-S0-06 | REUSE | 共通 UI components (Button/Input/Modal/Toast/Badge / shadcn  |
| ✅ | T-S0-13 | NEW | 既存実装インベントリ監査 (51 routers + 75 services + 13 migrations + 9 |

#### Wave 1.3 — 2/7 done, 6 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-001-01 | REFACTOR | Supabase project init + 環境変数 (env 必須化 / 4 vars / ハードコード鍵除去 |
| ✅ | T-002-01 | REFACTOR | スキル管理 UI (existing skills.py 拡張) |
| ⏳ | T-019-03 | REUSE | bootstrap 動作確認 (smoke test: main:app import / archive remo |
| ⏳ | T-021-04 | NEW | permission matrix UI grid (frontend/src/app/workspaces/[id |
| ⏳ | T-023-01 | REFACTOR | プロフィール編集 UI (frontend/src/app/settings/profile/page.tsx Pr |
| ⏳ | T-S0-13b | REFACTOR | UNDETERMINED 64 件 → 0 化 + Orphan 6 件 → 16 annotated (T-S0- |
| ⏳ | T-S0-13c | REFACTOR | tickets.json 全件 AC 整合検査 (title ↔ AC + テンプレ転用検出 / verbatim  |

#### Wave 1.4 — 0/3 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-001-01b | REFACTOR | FastAPI モジュラーモノリス 13 ドメイン bounded-context 整理 |
| ⏳ | T-001-02 | REFACTOR | 認証 6 テーブル DDL + RLS (supabase/migrations/20260510000000_au |
| ⏳ | T-002-02 | REFACTOR | archive スクリプト (existing skill_manager.py 拡張) |

#### Wave 1.5 — 1/2 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-004-01 | REFACTOR | account 作成 API + UI (POST /api/accounts / AccountCreate +  |
| ⏳ | T-021-01 | REFACTOR | 6 ロール enum + permission matrix JSON (account_owner→owner / |

#### Wave 1.6 — 0/3 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-004-02 | REFACTOR | workspace 作成 API+UI (existing workspaces.py 拡張) |
| ⏳ | T-004-05 | NEW | owner 移譲 UI (/workspaces/[id]/settings owner-transfer sect |
| ⏳ | T-021-02 | NEW | custom_permissions JSONB バリデータ (validate_custom_permission |

#### Wave 1.7 — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-004-03 | NEW | workspace_invitations 発行 API |

#### Wave 1.8 — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-004-04 | NEW | 招待受入 API + signup |

#### Wave 1.9 — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-004-06 | NEW | テナント階層統合テスト |

#### Wave 1.99 (Integration Test) — 1/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-IT-S0 | NEW | Sprint 0 統合テスト |

---

### S2: AI 社員 + Chat + Memory (3 tier)

**Dogfood 受入基準**: workspace 内で AI 社員と会話できる + 短期/中期/長期 memory が回る

**進捗**: 25/51 done = 49.0%

**Wave 構造** (依存深さ):


#### Wave 2.1 — 5/10 done, 7 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-001-03 | REFACTOR | AI 5 テーブル DDL (hierarchy + clone / 20260512200000_ai_hiera |
| ✅ | T-001-04 | NEW | Build-Factory プロジェクト 11 テーブル DDL + RLS (supabase/migration |
| ✅ | T-001-05 | NEW | 実装・連携・運用 17 テーブル + Template DDL (chat_threads / chat_messa |
| ⏳ | T-020-01 | NEW | LiteLLM docker-compose 追加 (ADR-010 Layer 2b サブ用途: cheap-ba |
| ⏳ | T-020-04 | REFACTOR | BYOK + Anthropic prompt cache (cache_control: ephemeral) |
| ✅ | T-024-04 | REFACTOR | workspaces.preferred_provider column 追加 migration (ADR-012 |
| ⏳ | T-026-02 | NEW | Constitution editor UI (content_md + version diff) |
| ✅ | T-M12-01 | REFACTOR | LiteLLM Router (サブ用途のみ — 画像/音声/安価バッチ/緊急代替) |
| ⏳ | T-M30-04 | REFACTOR | 長期 layer (existing long_term_memory + obsidian_sync 統合) |
| ✅ | T-S0-08 | REFACTOR | claude-agent-sdk runner 基盤 (subprocess + session resume /  |

#### Wave 2.2 — 11/18 done, 8 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-001-06 | REFACTOR | RLS 全 23 ユーザデータテーブル enforcement + custom_permissions 連動 (s |
| ⏳ | T-001-07 | REUSE | 拡張機能 4 種 (vector + pg_trgm + pgsodium + pg_cron) + GIN/BRI |
| ⏳ | T-001-08 | NEW | クローン opt-in trigger + service (bf_enforce_clone_opt_in / u |
| ✅ | T-001-09 | NEW | 循環依存防止 trigger 2 種 (recursive CTE / bf_prevent_task_dep_cy |
| ✅ | T-020-02 | REFACTOR | Memory 3 tier (claude-agent-sdk session + Memory API + Mem |
| ⏳ | T-022-01 | REUSE | ai_employees DDL 拡張確認 (5 table CREATE TABLE IF NOT EXISTS: |
| ✅ | T-026-01 | REUSE | constitutions DDL 確認 |
| ⏳ | T-AI-01 | NEW | Anthropic Memory API 統合 (memory_facts.write_fact + extract |
| ⏳ | T-AI-06 | NEW | Rate limit 自動 retry (anthropic_retry.with_retry + retryabl |
| ✅ | T-AI-MEM-01 | NEW | Anthropic Memory Tool client-side handler (memory_20250818 |
| ✅ | T-AI-MEM-02 | NEW | Anthropic Context Editing config (clear_tool_uses_20250919 |
| ✅ | T-M27-01 | ARCHIVE | (ARCHIVED) LangGraph base setup — superseded by T-M27-01b  |
| ✅ | T-M27-01b | NEW | claude-agent-sdk entry node (replaces T-M27-01 per ADR-010 |
| ✅ | T-M28-01 | REFACTOR | Context Builder skeleton (existing conversation_memory/rag |
| ✅ | T-M28-02 | REUSE | Tier 1 tool result trimming (SDK auto activation + audit w |
| ⏳ | T-M28-03 | REUSE | Tier 2 prompt cache friendly (cache_control: ephemeral 5mi |
| ⏳ | T-M30-01 | REFACTOR | ChatThread/ChatMessage CRUD (existing threads.py 拡張) |
| ✅ | T-M30-05 | NEW | Memory 統合 orchestrator (memory_pipeline; 3 層 short+mid+lon |

#### Wave 2.3 — 6/13 done, 10 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-001-10 | NEW | seed.sql + BF_ENV ガード (supabase/seed.sql idempotent / back |
| ✅ | T-003-02 | REFACTOR | AI 社員召喚 API + Workspace Dashboard (existing secretary_chat |
| ⏳ | T-020-03 | REFACTOR | provider adapter 3 個 (Anthropic/OpenAI/Gemini) |
| ⏳ | T-022-02 | NEW | 階層循環参照 trigger |
| ⏳ | T-022-03 | REFACTOR | AI 社員 CRUD API (existing employees.py/staff_service.py 拡張) |
| ✅ | T-026-03 | REFACTOR | Constitution context 注入 (M-28 連携) |
| ⏳ | T-AI-02 | NEW | Mem0 ベクトル検索 + Anthropic Memory API ブリッジ (mem0_bridge.mirro |
| ✅ | T-AI-08 | NEW | Anthropic 障害時 LiteLLM フォールバック (Claude → GPT-4o / Gemini) |
| ✅ | T-AI-MEM-04 | NEW | Provider-adapter Memory Tool (任意切替 + 障害時 fallback 両対応; Ant |
| ✅ | T-M27-02 | REFACTOR | Intent 分類 (existing intent_preprocessor/mode_detector/skil |
| ✅ | T-M28-04 | REFACTOR | Tier 3 9-section structured summary persistence (SDK auto- |
| ⏳ | T-M28-05 | REFACTOR | semantic retrieval (existing embedding_service 活用) |
| ⏳ | T-M30-02 | REUSE | 短期 layer (FIFO 直近 N=20; chat_thread_store REUSE wrapper) |

#### Wave 2.4 — 2/8 done, 5 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-001-11 | NEW | DB 統合テスト (RLS/権限/soft delete/拡張) |
| ⏳ | T-003-01 | REFACTOR | BMAD 12 → 10 メンバー persona prompt 整理 (md source-of-truth +  |
| ⏳ | T-003-03 | NEW | parent guideline 継承 |
| ⏳ | T-003-04 | NEW | スキル context 注入 (CLAUDE.md ルール準拠) |
| ⏳ | T-003-05 | REFACTOR | artifact 保存 + AC 検証連携 (existing artifact_service 活用) |
| ⏳ | T-022-04 | NEW | 組織図 UI (React Flow tree / AI 社員 hierarchy 可視化 / Lucide + e |
| ✅ | T-M27-03 | REUSE | Agent / Role Selector + handoff (SDK Task tool activation  |
| ✅ | T-M30-03 | REFACTOR | 中期 layer (mid_term_layer; chat_thread_store + conversation |

#### Wave 2.5 — 1/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-AI-MEM-03 | NEW | Subagent Memory store (handoff 引継ぎ知識保管; /memories/subagent |

#### Wave 2.99 (Integration Test) — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-IT-S2 | NEW | Sprint 2 統合テスト (M-27 chain x M-30 chain x 4 層 observabilit |

---

### S3: ヒアリング → 要件定義 AI ペルソナ

**Dogfood 受入基準**: Mary (BA) がヒアリング, Preston (PM) が要件定義書を出す

**進捗**: 4/9 done = 44.4%

**Wave 構造** (依存深さ):


#### Wave 3.1 — 2/5 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-005-01 | REFACTOR | hearing AI (Mary) 4STEP (existing hearing.py/hearing_servi |
| ✅ | T-005-04 | REFACTOR | 仕様書 HTML 生成 |
| ⏳ | T-005b-01 | REFACTOR | screens/components 統一 read view (existing design_frames/de |
| ⏳ | T-005b-02 | REFACTOR | ui-mockup スキル統合 (existing designer_ai REFACTOR: SKILL.md p |
| ⏳ | T-005b-03 | NEW | コンポーネントカタログ + 画面遷移マップ (mock HTML から bf-* meta 抽出 + 遷移 DAG  |

#### Wave 3.2 — 1/3 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-005-02 | REFACTOR | 対話 UI + slot 永続化 (existing slot_state/slot_extractor 活用) |
| ⏳ | T-005-03 | REFACTOR | requirements AI (Preston) 6STEP (existing requirements.py  |
| ✅ | T-005b-04 | NEW | 仕様 ↔ モック双方向リンク |

#### Wave 3.99 (Integration Test) — 1/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-IT-S3 | NEW | Sprint 3 統合テスト |

---

### S4: アーキ設計 → 機能分解 → タスク分解 AI

**Dogfood 受入基準**: Winston (Architect) → Sally (PO) → Devon (Dev) の連携で 1 案件分が組み立つ

**進捗**: 7/12 done = 58.3%

**Wave 構造** (依存深さ):


#### Wave 4.1 — 4/5 done, 3 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-006-01 | NEW | feature-decomposition AI (Devon) |
| ⏳ | T-006-03 | NEW | impact-analysis |
| ✅ | T-025-01 | NEW | EARS 5 形式テンプレ + JSON Schema バリデータ (機械的 AC 検証基盤) |
| ✅ | T-025-02 | NEW | EARS 形式分類 AI prompt + 書き直し suggest (rule-based + SDK backe |
| ✅ | T-BTSTRAP-01 | REUSE | テンプレート構造を確定 (templates/project-bootstrap/) |

#### Wave 4.2 — 2/3 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-006-02 | REFACTOR | task-decomposition AI + EARS AC (existing tasks.py REFACTO |
| ✅ | T-BTSTRAP-02 | REFACTOR | WorkspaceService.bootstrap() — 新案件作成時にテンプレを GitHub repo に展 |
| ✅ | T-BTSTRAP-03 | NEW | Jinja2 プレースホルダ置換エンジン |

#### Wave 4.3 — 1/3 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-006-04 | NEW | タスク分解 UI (TaskDecomposeForm.tsx / POST /api/task-decomposi |
| ✅ | T-BTSTRAP-04 | NEW | 既存案件への遡及適用 (build-factory project migrate) |
| ⏳ | T-BTSTRAP-06 | NEW | e2e テスト = workspace 作成 → 強制レイヤー検証 |

#### Wave 4.4 — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-BTSTRAP-05 | NEW | テンプレ更新時に全案件へ PR 自動作成 (CI 統合) |

---

### S5: Kanban + DAG + Phase 管理 + 横断検索

**Dogfood 受入基準**: タスク化 → Kanban で進捗 → DAG で依存可視化 → Cmd+K で横断検索

**進捗**: 9/20 done = 45.0%

**Wave 構造** (依存深さ):


#### Wave 5.1 — 6/10 done, 4 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-007-01 | REFACTOR | task_kanban accordion (existing TaskKanban.tsx REFACTOR /  |
| ⏳ | T-007-02 | NEW | task_list view (table + sort + 一括操作) |
| ✅ | T-008-01 | REFACTOR | phases CRUD (existing dashboard.py 一部活用) |
| ✅ | T-009-01 | REUSE | task_dependencies CRUD |
| ⏳ | T-009-02 | NEW | DAG 可視化 UI (React Flow @xyflow/react v12 / 6 status palett |
| ⏳ | T-009-03 | NEW | 影響範囲 AI ハイライト |
| ⏳ | T-024-01 | NEW | Cmd+K UI modal (cmdk + shadcn/ui Dialog / global Cmd+K | C |
| ✅ | T-024-02 | REFACTOR | unified search API (existing knowledge_search/embedding_se |
| ✅ | T-024-03 | REUSE | RLS 連動 |
| ✅ | T-AI-03 | NEW | chat_messages 全文検索 (chat_search.hybrid_search + parse_quer |

#### Wave 5.2 — 2/7 done, 4 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-007-03 | REUSE | task_dag_view (existing DependencyGraph.tsx REUSE wrapper  |
| ⏳ | T-007-04 | NEW | 仮想スクロール VirtualList (react-window FixedSizeList wrapper /  |
| ⏳ | T-008-02 | NEW | phase_management UI (フェーズ + ガント + ゲート編集) |
| ⏳ | T-008-03 | NEW | ゲート達成判定 + auto unlock |
| ⏳ | T-009-04 | NEW | DAG 仮想化 + 階層折りたたみ (pure helpers + DagHierarchyControls / D |
| ⏳ | T-009-05 | NEW | 依存追加/削除 drag&drop (pure validation + DependencyDnDPanel /  |
| ✅ | T-024-02b | REFACTOR | unified search silent-fail fix (kwarg drift + bf_db Import |

#### Wave 5.3 — 1/2 done, 2 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-007-03b | REFACTOR | task_dag_view edge_type/kind semantic drift fix (silent: a |
| ⏳ | T-008-04 | NEW | フェーズ削除タスク移動 UI |

#### Wave 5.99 (Integration Test) — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-IT-S4 | NEW | Sprint 4 統合テスト |

---

### S6: MCP + Reviewer + Constitution 適用

**Dogfood 受入基準**: Quinn (QA/Reviewer) が動く + MCP server 経由で Claude Code に bf tools が見える + red-line 監視

**進捗**: 8/21 done = 38.1%

**Wave 構造** (依存深さ):


#### Wave 6.1 — 6/13 done, 7 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-010a-01 | REFACTOR | MCP server (existing mcp_server.py + mcp_stdio_server.py 拡 |
| ⏳ | T-010a-04 | NEW | MCP token scope (workspace 単位) |
| ✅ | T-010b-01 | REFACTOR | claude-agent-sdk 統合 (existing task_executor + skill_runner |
| ⏳ | T-010b-02 | NEW | OAuth フロー (Claude Pro/Max トークン) |
| ⏳ | T-010b-03 | REFACTOR | 初期プロンプト構築 (M-28 経由) |
| ⏳ | T-010b-05 | NEW | sessions table 状態遷移管理 |
| ✅ | T-011-01 | REFACTOR | Reviewer AI persona + Plan/Gen/Eval (existing reviewer.py  |
| ⏳ | T-011-03 | REFACTOR | エスカレ通知 (Slack DM + UI バッジ) |
| ⏳ | T-012-01 | NEW | red_lines DDL + 5 主要 category seed |
| ⏳ | T-012-03 | NEW | OS-level sandbox red-line policy (Linux Landlock + seccomp |
| ✅ | T-AI-04 | NEW | Constitution 自動注入エンジン (全 AI 社員のシステムプロンプト) |
| ✅ | T-S0-09 | NEW | OS-level sandbox 基盤 (bwrap on Linux + --unshare-net zero-t |
| ✅ | T-S0-09b | REFACTOR | RLS context helper (auth_middleware → PostgreSQL session に |

#### Wave 6.2 — 2/6 done, 4 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ✅ | T-010a-02 | REFACTOR | bf_get_spec / bf_post_progress / bf_attach_artifact 実装 |
| ⏳ | T-010a-03 | NEW | bf_request_review / bf_get_review_feedback 実装 |
| ⏳ | T-010b-04 | REFACTOR | Play ボタン UI + session 起動 API (REFACTOR: existing POST /api |
| ⏳ | T-011-02 | NEW | 3 ターンカウンター + state 管理 (reviewer 改善 loop 上限 / 4 ターン目で escal |
| ⏳ | T-011-04 | NEW | 統合テスト指揮 AI (integration test conductor / DAG topological 実 |
| ✅ | T-012-02 | REFACTOR | pattern 検出 middleware (existing approval.py 拡張) |

#### Wave 6.3 — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-012-04 | REFACTOR | red_line_approval キュー UI (existing approval ページ拡張) |

#### Wave 6.99 (Integration Test) — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-IT-S5 | NEW | Sprint 5 統合テスト |

---

### S7: Swarm 並列実行 + Worktree (= 靴屋に靴を履かせる)

**Dogfood 受入基準**: 1 人の operator が Swarm UI で複数 task を並列実行できる

**進捗**: 2/16 done = 12.5%

**Wave 構造** (依存深さ):


#### Wave 7.1 — 1/8 done, 4 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-010c-01 | REFACTOR | asyncio.Semaphore + Queue (existing task_executor 拡張) |
| ⏳ | T-010c-02 | NEW | 親子昇格 (依存グラフ尊重) |
| ⏳ | T-010c-05 | NEW | crash detection (30 分応答なし/メモリ閾値超/予期せぬ exit) |
| ⏳ | T-010d-01 | NEW | FastAPI WebSocket endpoint (session subscribe) |
| ⏳ | T-010d-02 | NEW | swarm_grid UI (SwarmGrid.tsx / 4 size preset 4/9/16/64 / c |
| ⏳ | T-021-03 | NEW | Swarm 並列実行 (backend/services/swarm/orchestrator.start_swar |
| ✅ | T-AI-07 | NEW | Streaming UI (claude-agent-sdk → WebSocket bridge) |
| ⏳ | T-M29-01 | NEW | git worktree manager (作成/cleanup / Codex CLI 参考 / swarm 並列 |

#### Wave 7.2 — 1/7 done, 3 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-010c-03 | NEW | 完了次第キュー補充 (FIFO + priority) |
| ⏳ | T-010c-04 | NEW | circuit breaker (連続失敗 N で auto-block) |
| ⏳ | T-010c-06 | NEW | resume 機能 (4 択: from_checkpoint/再実行/cancel/手動修正 / round-tr |
| ⏳ | T-010d-03 | NEW | swarm_session_detail UI (個別全画面 + ライブログ / GET /api/agent/se |
| ⏳ | T-010d-04 | NEW | 自動 reconnect + 履歴 fetch (T-010d-01 WS subscribe REUSE / ex |
| ⏳ | T-M29-02 | NEW | worktree path → session マッピング (T-M29-01 REUSE / parse_work |
| ✅ | T-M29-03 | NEW | merge conflict 検出 + sequential merge ヘルパー (T-M29-01 worktr |

#### Wave 7.99 (Integration Test) — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-IT-S6 | NEW | Sprint 6 統合テスト (5 並列タスク完走) |

---

### S8: GitHub + Slack + Obsidian + 観測 + 監査 + 配信

**Dogfood 受入基準**: PR 自動化 / Slack 通知 / Obsidian エクスポート / Langfuse / 監査ログ / 納品まで完走

**進捗**: 5/24 done = 20.8%

**Wave 構造** (依存深さ):


#### Wave 8.1 — 4/17 done, 7 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-013-01 | NEW | GitHub OAuth + repo 紐付け UI |
| ⏳ | T-013-02 | NEW | Claude Code commit + push wrap (worktree 経由) |
| ✅ | T-013-04 | NEW | merge conflict 検出 + 人間エスカ (Phase 1; AI 解決試行は Phase 1.5 / T |
| ⏳ | T-014-01 | REUSE | Slack Bolt 統合 (existing slack_client + slack_block_kit 活用) |
| ⏳ | T-015-01 | REFACTOR | 共通テンプレ registry (existing artifact_export REFACTOR / forma |
| ✅ | T-015-03 | REFACTOR | Storage upload + 共有リンク + Markdown 併記 |
| ⏳ | T-016-01 | REFACTOR | obsidian_vaults 設定 UI (existing obsidian_sync 活用) |
| ⏳ | T-017-01 | NEW | Langfuse self-host docker-compose (v3 / langfuse-web + lan |
| ⏳ | T-017-02 | REFACTOR | Langfuse SDK 統合 (existing observability 拡張) |
| ⏳ | T-017-03 | NEW | cost dashboard (8 タブ・Recharts / GET /api/observability/cos |
| ⏳ | T-018-01 | NEW | audit_logs trigger (主要テーブルに変更検出) |
| ⏳ | T-018-02 | NEW | audit_log_viewer UI (検索 + before/after diff + CSV/JSON exp |
| ⏳ | T-018-03 | NEW | nightly-backup workflow (DB + Storage + 検証 / GitHub Action |
| ✅ | T-AI-05 | REFACTOR | Cost tracking (Anthropic Usage API + LiteLLM callback で 案件 |
| ✅ | T-S0-10 | NEW | Sentry 設定 (FE+BE / error reporting + perf tracing / gracef |
| ⏳ | T-S0-11 | NEW | structlog + pino (backend + frontend 中央集約 logger / 構造化ログ) |
| ⏳ | T-S0-12 | NEW | Better Stack uptime monitor (pull /health + push heartbeat |

#### Wave 8.2 — 1/5 done, 4 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-013-03 | NEW | PR 自動作成 + HTML diff 注釈レビュー資料添付 |
| ✅ | T-013-04b | NEW | merge conflict AI 自動解決試行 (Phase 1.5; LLM-driven strategy + |
| ⏳ | T-014-02 | REFACTOR | カテゴリ別 push (red_line/pr/progress/invite/system) + ダイジェスト |
| ⏳ | T-015-02 | REFACTOR | SVG 図解自動生成 (existing output_processor REFACTOR / pure svg  |
| ⏳ | T-016-02 | REFACTOR | artifact MD 化 (existing obsidian_sync 拡張) |

#### Wave 8.3 — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-016-03 | NEW | export trigger (manual/realtime/hourly/on_completion) |

#### Wave 8.99 (Integration Test) — 0/1 done, 1 parallel groups

| Status | ID | Label | Title (60ch) |
|---|---|---|---|
| ⏳ | T-IT-S7 | NEW | 最終統合テスト (自社 1 案件 End-to-End 完走) |

---

## 並列実行ガイド

`parallel_group` が **同じ** task は **互いに依存しない** ので、Claude セッションを
分けて並列実行できる (= Swarm 機能完成前でも手動並列化可能).

**運用ルール**:
- 同 wave + 同 group → 1 PR (compound task) で集約推奨
- 同 wave + 異 group → 別 Claude session で並列実行可
- 異 wave → 順次実行 (前 wave 全完了後に次 wave 着手)

---

## 検証方法 (per-Slice / per-Wave)

```bash
# Slice S1 全体の AC × test × impl × lint 覆い率を機械検査
python3 scripts/verify-slice.py S1

# Wave 1.1 だけ検査
python3 scripts/verify-slice.py S1 1.1

# 全 Slice まとめて検査 (Phase 1 ゲート用)
python3 scripts/verify-slice.py --all
```

検査項目:
- AC 件数 vs テストファイル件数の比較
- audit MD 存在チェック (pre-flight protocol 準拠)
- existing_files の存在チェック (REUSE/REFACTOR は元コード健在か)
- lint pass チェック (pre-commit-check.sh 全項目)

---

## 既存ドキュメントとの関係

| ファイル | 役割 | 改変 |
|---|---|---|
| `../2026-05-09_v1/tickets.json` | 元仕様 (187 task の AC/spec_link/deps) | **無改変** |
| `../IMPLEMENTATION_PROTOCOL.md` | 7 step SOP | **無改変** (slice 単位の合致は本ドキュメントが補助) |
| `../../audit/2026-05-13_v2/` | pre-flight audit MD (28 件) | **無改変** (継続使用) |
| `tickets-v2.json` | 上記 + slice/wave/parallel_group/dogfood/unlocks/done_status | **本ファイルが指す対象** |
| `kanban-by-slice.html` | Slice/Wave 別 Kanban view | 本 v2 で新規 |