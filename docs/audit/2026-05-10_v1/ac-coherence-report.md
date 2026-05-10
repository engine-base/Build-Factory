# T-S0-13c: tickets.json AC 整合検査結果

- Total tickets: 178
- 既修正 (PREVIOUSLY_FIXED): 12
- Verbatim 重複 AC text: 0 件
- title↔AC キーワード乖離: 57 件
- AC < 3 件 (insufficient): 0 件
- AC 不在 / review_needed: 147 件

## 1. Verbatim 重複 AC text (テンプレ転用シグナル)

(なし)


## 2. title↔AC キーワード乖離

### T-S0-05 (theme: UI/frontend)
- title: "shadcn/ui setup + Tailwind config"
- AC excerpt:

### T-S0-06 (theme: UI/frontend)
- title: "共通 UI components (Button/Input/Modal/Toast/Badge)"
- AC excerpt:

### T-001-01b `[previously_fixed]` (theme: API)
- title: "FastAPI モジュラーモノリス 13 ドメイン bounded-context 整理"
- AC excerpt:
  - [UBIQUITOUS] The backend code shall be organized into 13 bounded-context domain modules under backend/domains/.
  - [UBIQUITOUS] Each domain module shall expose only its public interface to other modules via a domains/<name>/__init__.py barrel.

### T-001-03 (theme: DDL/schema)
- title: "AI 5 テーブル DDL (hierarchy + clone)"
- AC excerpt:

### T-001-05 (theme: DDL/schema)
- title: "実装・連携・運用 20 テーブル DDL + ChatThread/ChatMessage/Template"
- AC excerpt:

### T-001-10 (theme: env/config)
- title: "seed.sql + BF_ENV ガード"
- AC excerpt:

### T-001-11 (theme: RLS)
- title: "DB 統合テスト (RLS/権限/soft delete/拡張)"
- AC excerpt:

### T-002-01 (theme: UI/frontend)
- title: "スキル管理 UI (existing skills.py 拡張)"
- AC excerpt:

### T-004-01 (theme: UI/frontend)
- title: "account 作成 API+UI (existing accounts.py 拡張)"
- AC excerpt:

### T-004-02 (theme: UI/frontend)
- title: "workspace 作成 API+UI (existing workspaces.py 拡張)"
- AC excerpt:

### T-004-03 (theme: API)
- title: "workspace_invitations 発行 API"
- AC excerpt:

### T-004-04 (theme: API)
- title: "招待受入 API + signup"
- AC excerpt:

### T-004-05 (theme: UI/frontend)
- title: "owner 移譲 UI"
- AC excerpt:

### T-021-02 (theme: RLS)
- title: "custom_permissions JSONB バリデータ"
- AC excerpt:

### T-021-04 (theme: UI/frontend)
- title: "permission matrix UI grid"
- AC excerpt:

### T-023-01 (theme: UI/frontend)
- title: "プロフィール編集 UI (existing user_profile 拡張)"
- AC excerpt:

### T-023-02 (theme: UI/frontend)
- title: "API キー管理 UI (existing credentials_store 活用)"
- AC excerpt:

### T-023-04 (theme: auth)
- title: "OAuth 連携 (Slack/GitHub/Anthropic)"
- AC excerpt:

### T-020-02 (theme: API)
- title: "Memory 3 tier (claude-agent-sdk session + Memory API + Mem0 + Obsidian)"
- AC excerpt:
  - [UBIQUITOUS] The memory service shall expose a unified API combining: Tier 1 (claude-agent-sdk session, raw messages), Tier 2 (compressed + 9-section summary auto-
  - [EVENT] When the SDK's auto compaction triggers at 95% context, the system shall persist the 9-section summary to chat_messages and emit a memory_compacted ev

### T-022-01 (theme: DDL/schema)
- title: "ai_employees DDL 拡張確認"
- AC excerpt:

### T-022-03 (theme: API)
- title: "AI 社員 CRUD API (existing employees.py/staff_service.py 拡張)"
- AC excerpt:

### T-022-04 (theme: UI/frontend)
- title: "組織図 UI (React Flow tree)"
- AC excerpt:

### T-003-03 (theme: UI/frontend)
- title: "parent guideline 継承"
- AC excerpt:

### T-M28-01 (theme: UI/frontend)
- title: "Context Builder skeleton (existing conversation_memory/rag_context 統合)"
- AC excerpt:
  - [UBIQUITOUS] The long-tier memory shall expose Mem0 vector search, Obsidian markdown read/write, and Constitution decision lookup as a unified API.
  - [EVENT] When a user message references a past decision (D-XXX), the system shall retrieve the related constitution entry within 200ms.

### T-025-02 (theme: UI/frontend)
- title: "EARS 形式分類 AI prompt + 書き直し suggest UI"
- AC excerpt:

### T-005-02 (theme: UI/frontend)
- title: "対話 UI + slot 永続化 (existing slot_state/slot_extractor 活用)"
- AC excerpt:

### T-005-03 (theme: UI/frontend)
- title: "requirements AI (Preston) 6STEP (existing requirements.py 拡張)"
- AC excerpt:

### T-005b-02 (theme: UI/frontend)
- title: "ui-mockup スキル統合 (existing designer_ai 拡張)"
- AC excerpt:

### T-005b-03 (theme: UI/frontend)
- title: "コンポーネントカタログ + 画面遷移マップ"
- AC excerpt:

### T-005b-04 (theme: UI/frontend)
- title: "仕様 ↔ モック双方向リンク"
- AC excerpt:

### T-006-04 (theme: UI/frontend)
- title: "タスク分解 UI"
- AC excerpt:

### T-008-02 (theme: UI/frontend)
- title: "phase_management UI (フェーズ + ガント + ゲート編集)"
- AC excerpt:

### T-008-04 (theme: UI/frontend)
- title: "フェーズ削除タスク移動 UI"
- AC excerpt:

### T-009-02 (theme: UI/frontend)
- title: "DAG 可視化 UI (React Flow)"
- AC excerpt:

### T-024-01 (theme: UI/frontend)
- title: "Cmd+K UI modal"
- AC excerpt:

### T-024-02 (theme: API)
- title: "search API (existing knowledge_search/embedding_service 拡張)"
- AC excerpt:

### T-024-03 (theme: RLS)
- title: "RLS 連動"
- AC excerpt:

### T-026-01 (theme: DDL/schema)
- title: "constitutions DDL 確認"
- AC excerpt:

### T-026-02 (theme: UI/frontend)
- title: "Constitution editor UI (content_md + version diff)"
- AC excerpt:

### T-012-01 (theme: DDL/schema)
- title: "red_lines DDL + 5 主要 category seed"
- AC excerpt:

### T-012-02 (theme: DDL/schema)
- title: "pattern 検出 middleware (existing approval.py 拡張)"
- AC excerpt:

### T-012-03 (theme: runner/sandbox)
- title: "OS-level sandbox (Codex CLI 参考・Linux Landlock + seccomp)"
- AC excerpt:

### T-012-04 (theme: UI/frontend)
- title: "red_line_approval キュー UI (existing approval ページ拡張)"
- AC excerpt:

### T-010b-01 (theme: runner/sandbox)
- title: "claude-agent-sdk 統合 (existing task_executor + skill_runner 拡張)"
- AC excerpt:

### T-010b-02 (theme: auth)
- title: "OAuth フロー (Claude Pro/Max トークン)"
- AC excerpt:

### T-010b-04 (theme: UI/frontend)
- title: "▶︎ ボタン UI + session 起動 API"
- AC excerpt:

### T-011-03 (theme: UI/frontend)
- title: "エスカレ通知 (Slack DM + UI バッジ)"
- AC excerpt:

### T-010c-04 (theme: UI/frontend)
- title: "circuit breaker (連続失敗 N で auto-block)"
- AC excerpt:

### T-010d-01 (theme: API)
- title: "FastAPI WebSocket endpoint (session subscribe)"
- AC excerpt:

### T-010d-02 (theme: UI/frontend)
- title: "swarm_grid UI (4×4 default + 4/9/16/64 + 仮想化)"
- AC excerpt:

### T-010d-03 (theme: UI/frontend)
- title: "swarm_session_detail UI (個別全画面 + ライブログ)"
- AC excerpt:

### T-013-01 (theme: UI/frontend)
- title: "GitHub OAuth + repo 紐付け UI"
- AC excerpt:

### T-016-01 (theme: UI/frontend)
- title: "obsidian_vaults 設定 UI (existing obsidian_sync 活用)"
- AC excerpt:

### T-018-01 (theme: DDL/schema)
- title: "audit_logs trigger (主要テーブルに変更検出)"
- AC excerpt:

### T-018-02 (theme: UI/frontend)
- title: "audit_log_viewer UI (検索 + before/after diff + CSV/JSON export)"
- AC excerpt:

### T-AI-02 (theme: API)
- title: "Mem0 ベクトル検索 + Anthropic Memory API ブリッジ"
- AC excerpt:
  - [UBIQUITOUS] The bridge shall mirror every Memory API write to Mem0 (pgvector) for similarity search.
  - [EVENT] When a session asks 'recall similar past decisions to X', the system shall query Mem0 vector top-5 within 300ms and re-rank against Memory API results

### T-AI-07 (theme: UI/frontend)
- title: "Streaming UI (claude-agent-sdk → WebSocket bridge)"
- AC excerpt:
  - [EVENT] When claude-agent-sdk emits a streaming token, the system shall forward it via WebSocket to the subscribed frontend within 50ms.
  - [EVENT] When a tool_use event occurs, the system shall send a structured ws message {type:'tool_use', tool, input} and append to session_logs.


## 3. AC < 3 件 (insufficient — EARS は最低 3 件推奨)

(なし)


## 4. AC 不在 / review_needed

- T-019-02: no AC at all
- T-019-03: no AC at all
- T-S0-01: no AC at all
- T-S0-02: no AC at all
- T-S0-03: no AC at all
- T-S0-04: no AC at all
- T-S0-05: no AC at all
- T-S0-06: no AC at all
- T-S0-07: no AC at all
- T-S0-10: no AC at all
- T-S0-11: no AC at all
- T-S0-12: no AC at all
- T-001-03: no AC at all
- T-001-05: no AC at all
- T-001-07: no AC at all
- T-001-08: no AC at all
- T-001-09: no AC at all
- T-001-10: no AC at all
- T-001-11: no AC at all
- T-002-01: no AC at all
- T-002-02: no AC at all
- T-004-01: no AC at all
- T-004-02: no AC at all
- T-004-03: no AC at all
- T-004-04: no AC at all
- T-004-05: no AC at all
- T-004-06: no AC at all
- T-IT-S0: no AC at all
- T-021-01: no AC at all
- T-021-02: no AC at all
- T-021-04: no AC at all
- T-021-05: no AC at all
- T-023-01: no AC at all
- T-023-02: no AC at all
- T-023-03: no AC at all
- T-023-04: no AC at all
- T-023-05: no AC at all
- T-020-01: no AC at all
- T-020-03: no AC at all
- T-020-04: no AC at all
- T-022-01: no AC at all
- T-022-02: no AC at all
- T-022-03: no AC at all
- T-022-04: no AC at all
- T-003-01: no AC at all
- T-003-03: no AC at all
- T-003-04: no AC at all
- T-003-05: no AC at all
- T-M27-01: no AC at all
- T-M27-02: no AC at all
- T-M27-03: no AC at all
- T-M28-02: no AC at all
- T-M28-03: no AC at all
- T-M28-04: no AC at all
- T-M28-05: no AC at all
- T-M30-01: no AC at all
- T-M30-02: no AC at all
- T-M30-03: no AC at all
- T-M30-04: no AC at all
- T-M30-05: no AC at all
- T-IT-S2: no AC at all
- T-025-01: no AC at all
- T-025-02: no AC at all
- T-015-01: no AC at all
- T-015-02: no AC at all
- T-015-03: no AC at all
- T-005-01: no AC at all
- T-005-02: no AC at all
- T-005-03: no AC at all
- T-005-04: no AC at all
- T-005b-01: no AC at all
- T-005b-02: no AC at all
- T-005b-03: no AC at all
- T-005b-04: no AC at all
- T-006-01: no AC at all
- T-006-02: no AC at all
- T-006-03: no AC at all
- T-006-04: no AC at all
- T-IT-S3: no AC at all
- T-008-01: no AC at all
- T-008-02: no AC at all
- T-008-03: no AC at all
- T-008-04: no AC at all
- T-009-01: no AC at all
- T-009-02: no AC at all
- T-009-03: no AC at all
- T-009-04: no AC at all
- T-009-05: no AC at all
- T-007-01: no AC at all
- T-007-02: no AC at all
- T-007-03: no AC at all
- T-007-04: no AC at all
- T-024-01: no AC at all
- T-024-02: no AC at all
- T-024-03: no AC at all
- T-IT-S4: no AC at all
- T-026-01: no AC at all
- T-026-02: no AC at all
- T-026-03: no AC at all
- T-012-01: no AC at all
- T-012-02: no AC at all
- T-012-03: no AC at all
- T-012-04: no AC at all
- T-010a-01: no AC at all
- T-010a-02: no AC at all
- T-010a-03: no AC at all
- T-010a-04: no AC at all
- T-010b-01: no AC at all
- T-010b-02: no AC at all
- T-010b-03: no AC at all
- T-010b-04: no AC at all
- T-010b-05: no AC at all
- T-011-01: no AC at all
- T-011-02: no AC at all
- T-011-03: no AC at all
- T-011-04: no AC at all
- T-IT-S5: no AC at all
- T-M29-01: no AC at all
- T-M29-02: no AC at all
- T-M29-03: no AC at all
- T-010c-01: no AC at all
- T-010c-02: no AC at all
- T-010c-03: no AC at all
- T-010c-04: no AC at all
- T-010c-05: no AC at all
- T-010c-06: no AC at all
- T-010d-01: no AC at all
- T-010d-02: no AC at all
- T-010d-03: no AC at all
- T-010d-04: no AC at all
- T-IT-S6: no AC at all
- T-013-01: no AC at all
- T-013-02: no AC at all
- T-013-03: no AC at all
- T-013-04: no AC at all
- T-014-01: no AC at all
- T-014-02: no AC at all
- T-016-01: no AC at all
- T-016-02: no AC at all
- T-016-03: no AC at all
- T-017-01: no AC at all
- T-017-02: no AC at all
- T-017-03: no AC at all
- T-018-01: no AC at all
- T-018-02: no AC at all
- T-018-03: no AC at all
- T-IT-S7: no AC at all
