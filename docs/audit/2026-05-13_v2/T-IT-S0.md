# T-IT-S0 Pre-flight Audit — Sprint 0 統合テスト

**Date**: 2026-05-13
**Task**: T-IT-S0 — Sprint 0 統合テスト
**Sprint / Feature / Layer / Label**: 0 / META / TST / NEW
**Spec link**: `docs/requirements/2026-05-09_v1/requirements-v1.html#m-1`
**Mock link**: `docs/mocks/2026-05-09_v1/account/S-006-account-dashboard.html`
**Branch**: `claude/build-t-it-s0-sprint0-integration-audit`

---

## 1. タスク骨子

`tickets.json` の T-IT-S0 はメタタスク (`META / TST / NEW / 0.5 day`).
deps は **`all_sprint_0`** で「Sprint 0 全タスクが merge 済みであることを前提に
組み合わせ動作を検証する end-to-end integration smoke」と読み取れる.

仕様 stub の拡張:

> Sprint 0 統合テスト = Sprint 0 で投入した bootstrap/scaffold 一式
> (FastAPI モジュラーモノリス基盤 / Supabase env validation / 11+ migrations /
>  共通 UI / observability 3 層 / sandbox / BF_ENV guard / RLS / tenant 階層)
> が **同時に動く** ことを 1 つのプロセスで verify する.

ユニットテストの再実行ではなく **module 間契約・boot 時整合性** を確認する.

---

## 2. Sprint 0 タスク一覧 (28 件) と merge 状態

| ID         | タイトル要約                                                    | merge | 統合 touchpoint                                                         |
|------------|-----------------------------------------------------------------|-------|-------------------------------------------------------------------------|
| T-019-01   | bootstrap archive 9 ファイル / dirs                              | merged | repo に `onlook/`, `penpot/` が無いこと                                  |
| T-019-02   | modify 対象 GitHub Issue 化 scanner                              | merged | side-effect free / 直接統合 touchpoint 無し                              |
| T-019-03   | bootstrap 動作確認 (main:app import / required routes)            | merged | main:app import / 重要 router 登録                                       |
| T-S0-01    | docker-compose.yml 全サービス                                    | merged | docker-compose.yml が存在 / 4+ service 定義                              |
| T-S0-02    | GitHub Actions ci.yml                                           | merged | `.github/workflows/ci.yml` 存在 + 4 parallel jobs                        |
| T-S0-03    | license-check.yml (AGPL 防御 + ADR-010 ガード)                   | merged | `.github/workflows/license-check.yml` 存在                              |
| T-S0-04    | deploy-staging.yml                                              | merged | `.github/workflows/deploy-staging.yml` 存在                             |
| T-S0-05    | shadcn/ui + Tailwind config (frontend)                          | merged | `frontend/components.json` / `tailwind.config.*` (FE 側 / 本 smoke 範囲外) |
| T-S0-06    | 共通 UI components                                              | merged | frontend 側 / 本 smoke 範囲外                                            |
| T-S0-07    | Supabase FE wrapper                                             | merged | frontend 側 / 本 smoke 範囲外                                            |
| T-S0-08    | claude-agent-sdk runner 基盤 (chat_threads / chat_messages 同梱) | merged | `routers.chat_threads` 登録 / `services.claude_runner` import OK         |
| T-S0-09    | OS-level sandbox 基盤                                            | merged | `backend.sandbox` 公開 API 一式                                          |
| T-S0-09b   | RLS context helper                                              | merged | `services.auth_middleware` import / RLS helper 存在                      |
| T-S0-10    | Sentry 設定                                                     | merged | `sentry_config` import OK / graceful no-op                              |
| T-S0-11    | structlog + pino                                                | merged | `logging_config.configure_structlog` 等の 4 API 公開                      |
| T-S0-12    | Better Stack uptime                                             | merged | `uptime_heartbeat` import OK / graceful degradation                     |
| T-S0-13    | 既存実装インベントリ監査                                          | merged | `docs/audit/.../existing-inventory.json` 存在                            |
| T-S0-13b   | UNDETERMINED 0 化 + Orphan annotation                            | merged | `tickets.json` UNDETERMINED 0 件                                         |
| T-S0-13c   | tickets.json 全件 AC 整合検査                                    | merged | `scripts/validate-tickets.py` 通過                                      |
| T-001-01   | Supabase env 必須化                                              | merged | `config.validate_required_env` + 4 keys                                  |
| T-001-02   | 認証 6 テーブル DDL + RLS                                        | merged | `20260510000000_auth_tables.sql` 存在                                    |
| T-001-03   | AI 5 テーブル DDL                                                | merged | `20260512200000_ai_hierarchy_clone_tables.sql` 存在                      |
| T-001-04   | Build-Factory 11 テーブル DDL + RLS                              | merged | `20260510000001_bf_project_tables.sql` 存在                              |
| T-001-05   | 実装・連携・運用 17 テーブル                                      | merged | `20260512000000_impl_integration_ops_tables.sql` 存在                   |
| T-001-06   | RLS 全 23 ユーザデータテーブル enforcement                       | merged | `20260510000002_rls_full_enforcement.sql` 存在                          |
| T-001-07   | 拡張機能 4 種 + GIN/BRIN/partial index                           | merged | `20260501220100_pgvector.sql` + `..._extensions_pgsodium_pgcron_indexes.sql` |
| T-001-08   | クローン opt-in trigger + service                                 | merged | `services.clone_opt_in` import OK                                        |
| T-001-09   | 循環依存防止 trigger 2 種                                        | merged | `20260512300000_cycle_prevention_triggers.sql` 存在                      |
| T-001-10   | seed.sql + BF_ENV ガード                                         | merged | `services.bf_env_guard` 公開 API + `supabase/seed.sql` 存在               |
| T-001-11   | DB 統合テスト                                                    | merged | 別 file (DB) / 本 smoke は service-layer only                            |
| T-002-01/02 | スキル管理 UI / archive                                          | merged | `routers.skills` 登録                                                    |
| T-004-01〜06 | account / workspace / invitation                                | merged | `routers.accounts` + `routers.workspaces` (含 invitations_router) 登録   |

**merge 状態結論**: deps `all_sprint_0` は満たされている (28/28 merged, T-019-02/T-004-06 は git log で確認).

---

## 3. AC × impl × test × status

T-IT-S0 は META タスクで自身は production code を持たない. AC は「統合テスト
そのもの」の振舞いを規定する.

| AC   | EARS type     | テキスト要約                                       | impl                                                                 | test                                                                          | status |
|------|---------------|----------------------------------------------------|----------------------------------------------------------------------|-------------------------------------------------------------------------------|--------|
| AC-1 | UBIQUITOUS    | T-IT-S0 を Sprint 0 統合テストとして実装           | `backend/tests/test_t_it_s0_sprint0_integration.py` を新規追加         | `test_ac1_*` (smoke: main:app boot / 重要 router 登録)                          | 本 PR  |
| AC-2 | EVENT-DRIVEN  | 実装ステップで audit entry を残す                  | pytest 実行で行われる sentinel write / `audit_logs` table 検証無し (smoke) | `test_ac2_*` (statistics file write / boot timestamp asserts)                  | 本 PR  |
| AC-3 | STATE-DRIVEN  | 機能 enable 時に RLS / audit_logs を適用 (§5.3)    | RLS migration 存在 + auth_middleware RLS helper import + bf_env_guard | `test_ac3_*` (RLS migration 存在 / RLS helper / BF_ENV guard / audit migration) | 本 PR  |
| AC-4 | UNWANTED      | invalid input/unauth で 4xx + state 変更なし       | `app` の error contract = `{detail:{code,message}}` (T-S0-08 確認済み)     | `test_ac4_*` (validate_required_env が missing で SystemExit / accounts 401)    | 本 PR  |

---

## 4. Sprint 0 統合シナリオ (本 PR で実装)

各シナリオは **2+ Sprint 0 deliverable** を同時に触る.

### (a) Bootstrap 整合性 (T-019-01 + T-019-03 + T-S0-08 + T-001-01)
- `main:app` が import できる
- archive 対象 (`onlook/`, `penpot/`) repo root に存在しない
- Sprint 0 重要 router (`accounts`, `workspaces`, `chat_threads`, `skills`,
  `sandbox_landlock`, `byok`) が `app.routes` に登録されている
- `app.routes` 数が >= 200 (full bootstrap の最小ライン)

### (b) Supabase 環境 + BF_ENV guard (T-001-01 + T-001-10)
- `config.REQUIRED_SUPABASE` が exact 4 keys
- `validate_required_env(exit_on_failure=False)` が missing list を返す
- 1 key 欠けで `SystemExit(1)`
- `bf_env_guard.VALID_ENVS == ('dev','test','local','staging','prod')`
- prod で `is_destructive_allowed` False, dev で True
- `seed_sql_path()` が `supabase/seed.sql` を指す

### (c) Migrations 集合 (T-001-02〜09)
- `supabase/migrations/` 内に Sprint 0 で投入された 11 種 (auth / bf_project /
  rls_full / runner_session / ai_hierarchy_clone / impl_integration_ops /
  cycle_prevention / extensions / audit_logs / pgvector / initial_schema)
  全部存在
- ファイル数 >= 11

### (d) Observability 3 層 (T-S0-10 + T-S0-11 + T-S0-12)
- `sentry_config` import + 主要 API (`init_sentry`, `capture_exception`,
  `set_user`, `set_tag`) が存在
- `logging_config` import + (`configure_structlog`, `get_logger`,
  `bind_context`, `clear_context`) が存在
- `uptime_heartbeat` import OK
- SENTRY_DSN / BETTER_STACK_HEARTBEAT_URL 未設定でも全 API が graceful no-op

### (e) Sandbox 基盤 (T-S0-09 / T-S0-09b)
- `backend.sandbox` 公開 API (`SandboxConfig`, `SandboxResult`, `SandboxError`,
  `SandboxViolation`, `SandboxUnavailable`, `run_sandboxed`) が import OK
- `services.auth_middleware` import OK + `get_current_user` / `require_user` 存在

### (f) ADR-010 invariant (Sprint 0 全体)
- `services/agent_runner.py` / `services/claude_runner.py` (もし存在) で
  `langgraph` / `langchain` import が無い (string レベル grep)

### (g) Tenant 階層 (T-004-01〜06)
- `routers.accounts` の prefix `/api/accounts` 等のいずれかが登録
- `routers.workspaces` の prefix `/api/workspaces` 等のいずれかが登録
- `services.account_service` / `services.workspace_service` の主要関数が import OK

### (h) CI / workflows (T-S0-02 + T-S0-03 + T-S0-04)
- `.github/workflows/ci.yml` / `license-check.yml` / `deploy-staging.yml` が存在
- workflows ディレクトリ内 `*.yml` >= 3

### (i) Error contract (AC-4 / T-S0-08 共通)
- accounts POST に anon で送ると 401/422 のいずれか (4xx) であり、`detail`
  キーを返す ({detail:{code,message}} contract 互換)

---

## 5. Gap (upfront)

統合テスト追加のみ. Sprint 0 自体は全タスク merge 済みなので「不足機能」は
無いが、本 PR で塞ぐ gap は以下:

| # | gap                                                  | 解消方法                                            |
|---|------------------------------------------------------|-----------------------------------------------------|
| 1 | Sprint 0 全体に対する end-to-end integration smoke 無し | 新 file `test_t_it_s0_sprint0_integration.py` 追加 |
| 2 | bootstrap (T-019-01) archive 無除去の regression 未検出 | scenario (a) で `onlook/`, `penpot/` directory 不在 assert |
| 3 | observability 3 層が同時 import 可能か未保証          | scenario (d) で同一プロセス内 import + no-op 動作確認 |
| 4 | ADR-010 違反 (runner 内 LangGraph) が test layer で未検証 | scenario (f) で grep-based assertion              |
| 5 | Sprint 0 migrations 集合の存在保証が pytest 経路に無い | scenario (c) で 11 件の migration ファイル 存在 assert |

**追加コード行数見積**: ~400 LOC (1 file 新規, production code には触れない).

---

## 6. テスト戦略

- file: `backend/tests/test_t_it_s0_sprint0_integration.py` (1 file)
- 既存 test を `import` / `call` しない (自己完結)
- 外部 network / DB call なし (pure in-process / monkeypatch / Path)
- TestClient は `from main import app` を最小限使用 (router 登録の確認用)
- ENV は `monkeypatch.setenv` で Supabase 4 keys を仮置 (T-001-01 fail-fast 起動回避)
- 各 AC ごとに `test_acN_xxx` 命名 + scenario ごとに `test_scenario_<letter>_xxx`
- pyproject の `pytest` config (default `backend/`) で同じ collection 経路
- 期待 test 件数: **20 件前後** (各 scenario 2-3 件 + AC explicit 4 件)

---

## 7. 影響範囲

- production code: **無変更**
- Sprint 0 deliverable: **検証対象** (変更しない)
- CI 上の `bash scripts/lint-mock.sh` / `bash scripts/pre-commit-check.sh`:
  既存 lint 12 check + smoke を維持
- 既存テスト件数: 6500+ 維持. T-IT-S2 同様の独立 file として coexist.

---

## 8. 完了条件

1. `backend/tests/test_t_it_s0_sprint0_integration.py` が `-x` で all pass
2. `backend/tests/` 全体が `-q` で all pass (regression なし)
3. `bash scripts/lint-mock.sh` 12/12 OK (本 PR は production code 触らないので影響無し)
4. `bash scripts/pre-commit-check.sh` exit_code=0
5. PR が merged

---

**作成者**: Claude Code (worktree-agent-ad4552fc33cd8d058)
**最終更新**: 2026-05-13
