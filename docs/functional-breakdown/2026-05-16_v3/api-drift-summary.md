# Build-Factory v3 API Drift Summary

> 生成日: **2026-05-16**  
> source: `docs/functional-breakdown/2026-05-16_v3/features.json`

## 概要

v3 mock の `bf-related-apis` メタタグから抽出した **mock 宣言 endpoint** と、`backend/routers/*.py` から抽出した **backend 実装 endpoint** を比較し、drift を検出した。

| 指標 | 件数 |
|---|---|
| mock 宣言 endpoint (unique) | 113 |
| backend 実装 endpoint (unique) | 453 |
| mock ↔ backend 完全一致 | 17 |
| method mismatch (path 一致 / method 違い) | 5 |
| critical missing (mock 宣言 / backend 未実装) | 89 |
| backend 実装あるが mock 宣言なし | TBD (内部 API 多数 / Phase 1.5 候補) |
| features.json に記録された drift 件数 | 104 |

## severity 別件数

| severity | 件数 | 流し込み先 group |
|---|---|---|
| **critical** | 94 | Group B-1 (Vertical Slice / Backend) |
| **high** | 7 | Group D (Drift fix) |
| **medium** | 1 | Group D (Drift fix) — low priority |
| **low** | 2 | Group D 監視のみ |

## critical 詳細 (backend 未実装の mock 宣言)

これらは frontend mock が呼び出す URL だが backend router が無い。
**Task-decomposition Group B-1 (Vertical Slice / Backend)** で新規実装が必要。

| Feature | Endpoint | Task ID |
|---|---|---|
| F-001 認証 (email+pwd / MFA / OAuth) | `POST /api/auth/login` | T-V3-DRIFT-F-001-01 |
| F-001 認証 (email+pwd / MFA / OAuth) | `POST /api/auth/signup` | T-V3-DRIFT-F-001-02 |
| F-001 認証 (email+pwd / MFA / OAuth) | `POST /api/auth/password-reset` | T-V3-DRIFT-F-001-03 |
| F-001 認証 (email+pwd / MFA / OAuth) | `POST /api/auth/mfa/enroll` | T-V3-DRIFT-F-001-04 |
| F-001 認証 (email+pwd / MFA / OAuth) | `POST /api/auth/mfa/verify` | T-V3-DRIFT-F-001-05 |
| F-001 認証 (email+pwd / MFA / OAuth) | `GET /api/auth/oauth/{provider}/callback` | T-V3-DRIFT-F-001-06 |
| F-002 既存 96 スキル整理 / archive 管理 | `POST /api/skills/{id}/test` | T-V3-DRIFT-F-002-01 |
| F-003 AI 社員ハイブリッド統合 (BMAD + Agent Teams + 既存) | `GET /api/ai-employees/org-chart` | T-V3-DRIFT-F-003-01 |
| F-003 AI 社員ハイブリッド統合 (BMAD + Agent Teams + 既存) | `POST /api/ai-employees/{id}/test` | T-V3-DRIFT-F-003-03 |
| F-003 AI 社員ハイブリッド統合 (BMAD + Agent Teams + 既存) | `POST /api/ai-employees/{id}/clone-from-user` | T-V3-DRIFT-F-003-04 |
| F-004 account / workspace / members 階層管理 | `POST /api/accounts/{id}/transfer-owner` | T-V3-DRIFT-F-004-02 |
| F-004 account / workspace / members 階層管理 | `POST /api/accounts/{id}/invitations` | T-V3-DRIFT-F-004-03 |
| F-004 account / workspace / members 階層管理 | `DELETE /api/accounts/{id}/members/{user_id}` | T-V3-DRIFT-F-004-04 |
| F-004 account / workspace / members 階層管理 | `PUT /api/workspaces/{id}/members/{user_id}/role` | T-V3-DRIFT-F-004-06 |
| F-004 account / workspace / members 階層管理 | `DELETE /api/workspaces/{id}/invitations/{token}` | T-V3-DRIFT-F-004-08 |
| F-004 account / workspace / members 階層管理 | `GET /api/invitations/{token}` | T-V3-DRIFT-F-004-09 |
| F-005 ヒアリング → 仕様書 HTML パイプライン | `POST /api/workspaces/{id}/hearing/save` | T-V3-DRIFT-F-005-02 |
| F-005 ヒアリング → 仕様書 HTML パイプライン | `GET /api/workspaces/{id}/specs` | T-V3-DRIFT-F-005-03 |
| F-005 ヒアリング → 仕様書 HTML パイプライン | `GET /api/workspaces/{id}/specs/{spec_id}/comments` | T-V3-DRIFT-F-005-04 |
| F-005 ヒアリング → 仕様書 HTML パイプライン | `POST /api/workspaces/{id}/specs/{spec_id}/comments` | T-V3-DRIFT-F-005-05 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `GET /api/workspaces/{id}/mocks` | T-V3-DRIFT-F-005b-01 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `GET /api/workspaces/{id}/mocks/{screen_id}` | T-V3-DRIFT-F-005b-02 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `GET /api/workspaces/{id}/mocks/{screen_id}/html` | T-V3-DRIFT-F-005b-03 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `PUT /api/workspaces/{id}/mocks/{screen_id}/html` | T-V3-DRIFT-F-005b-04 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `POST /api/workspaces/{id}/mocks/{screen_id}/ai-edit` | T-V3-DRIFT-F-005b-05 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `GET /api/workspaces/{id}/components` | T-V3-DRIFT-F-005b-06 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `GET /api/workspaces/{id}/components/{id}/usage` | T-V3-DRIFT-F-005b-07 |
| F-005b 画面モック自動生成パイプライン (M-5b) | `GET /api/workspaces/{id}/screen-flow` | T-V3-DRIFT-F-005b-08 |
| F-006 機能・タスク分解 + acceptance-criteria (EARS) | `GET /api/workspaces/{id}/requirements` | T-V3-DRIFT-F-006-01 |
| F-006 機能・タスク分解 + acceptance-criteria (EARS) | `PUT /api/workspaces/{id}/requirements` | T-V3-DRIFT-F-006-02 |
| F-006 機能・タスク分解 + acceptance-criteria (EARS) | `POST /api/workspaces/{id}/requirements/versions` | T-V3-DRIFT-F-006-03 |
| F-006 機能・タスク分解 + acceptance-criteria (EARS) | `POST /api/tasks/{id}/comments` | T-V3-DRIFT-F-006-05 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `POST /api/workspaces/{id}/tasks/bulk-play` | T-V3-DRIFT-F-007-01 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `POST /api/workspaces/{id}/tasks/bulk-archive` | T-V3-DRIFT-F-007-02 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `GET /api/workspaces/{id}/tasks/export.csv` | T-V3-DRIFT-F-007-03 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `GET /api/workspaces/{id}/tasks/dag` | T-V3-DRIFT-F-007-04 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `POST /api/tasks/{id}/play` | T-V3-DRIFT-F-007-05 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `POST /api/workspaces/{id}/tasks/play-all` | T-V3-DRIFT-F-007-06 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | `POST /api/workspaces/{id}/play-all` | T-V3-DRIFT-F-007-07 |
| F-008 プロジェクト・フェーズ管理基盤 | `GET /api/workspaces/{id}/phases` | T-V3-DRIFT-F-008-01 |
| F-008 プロジェクト・フェーズ管理基盤 | `POST /api/workspaces/{id}/phases` | T-V3-DRIFT-F-008-02 |
| F-008 プロジェクト・フェーズ管理基盤 | `POST /api/workspaces/{id}/phases/{phase_id}/gate` | T-V3-DRIFT-F-008-03 |
| F-009 依存グラフ + 影響範囲伝搬 | `GET /api/workspaces/{id}/dependencies` | T-V3-DRIFT-F-009-01 |
| F-009 依存グラフ + 影響範囲伝搬 | `POST /api/workspaces/{id}/dependencies` | T-V3-DRIFT-F-009-02 |
| F-009 依存グラフ + 影響範囲伝搬 | `POST /api/workspaces/{id}/dependencies/impact-analysis` | T-V3-DRIFT-F-009-03 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `GET /api/workspaces/{id}/sessions` | T-V3-DRIFT-F-010-01 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `GET /api/sessions/{id}` | T-V3-DRIFT-F-010-02 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `POST /api/sessions/{id}/kill` | T-V3-DRIFT-F-010-04 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `POST /api/sessions/{id}/pause` | T-V3-DRIFT-F-010-05 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `POST /api/sessions/{id}/resume` | T-V3-DRIFT-F-010-06 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `POST /api/sessions/{id}/rollback` | T-V3-DRIFT-F-010-07 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `POST /api/workspaces/{id}/sessions/kill-all` | T-V3-DRIFT-F-010-08 |
| F-012 赤線リスト + 自動停止 (5 項目) | `GET /api/workspaces/{id}/red-lines` | T-V3-DRIFT-F-012-01 |
| F-012 赤線リスト + 自動停止 (5 項目) | `POST /api/workspaces/{id}/red-lines` | T-V3-DRIFT-F-012-02 |
| F-012 赤線リスト + 自動停止 (5 項目) | `POST /api/workspaces/{id}/red-lines/test` | T-V3-DRIFT-F-012-03 |
| F-012 赤線リスト + 自動停止 (5 項目) | `GET /api/workspaces/{id}/violations` | T-V3-DRIFT-F-012-04 |
| F-012 赤線リスト + 自動停止 (5 項目) | `POST /api/violations/{id}/approve` | T-V3-DRIFT-F-012-05 |
| F-012 赤線リスト + 自動停止 (5 項目) | `POST /api/violations/{id}/reject` | T-V3-DRIFT-F-012-06 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `GET /api/workspaces/{id}/prs/{pr_number}` | T-V3-DRIFT-F-013-01 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/prs/{id}/approve` | T-V3-DRIFT-F-013-02 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/prs/{id}/comments` | T-V3-DRIFT-F-013-03 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/prs/{id}/merge` | T-V3-DRIFT-F-013-04 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `GET /api/client/workspaces/{token}` | T-V3-DRIFT-F-013-05 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `GET /api/client/workspaces/{token}/spec` | T-V3-DRIFT-F-013-06 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `GET /api/client/comments/{thread_id}` | T-V3-DRIFT-F-013-07 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/client/comments` | T-V3-DRIFT-F-013-08 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/comments/{id}/resolve` | T-V3-DRIFT-F-013-09 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `GET /api/workspaces/{id}/delivery` | T-V3-DRIFT-F-013-10 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/workspaces/{id}/delivery/approve` | T-V3-DRIFT-F-013-11 |
| F-013 GitHub 連携 (PR + HTML diff 注釈) / 顧客レビュー | `POST /api/workspaces/{id}/delivery/send-client` | T-V3-DRIFT-F-013-12 |
| F-016 Obsidian ナレッジ母艦 (単方向 export) | `GET /api/workspaces/{id}/knowledge` | T-V3-DRIFT-F-016-01 |
| F-016 Obsidian ナレッジ母艦 (単方向 export) | `GET /api/workspaces/{id}/knowledge/search` | T-V3-DRIFT-F-016-02 |
| F-017 Langfuse self-host (観測 + コスト) | `GET /api/observability/cost-summary/export.csv` | T-V3-DRIFT-F-017-01 |
| F-017 Langfuse self-host (観測 + コスト) | `POST /api/workspaces/{id}/token-limit` | T-V3-DRIFT-F-017-02 |
| F-018 監査ログ + 通知 + バックアップ | `GET /api/audit-logs` | T-V3-DRIFT-F-018-01 |
| F-018 監査ログ + 通知 + バックアップ | `GET /api/audit-logs/export.csv` | T-V3-DRIFT-F-018-02 |
| F-018 監査ログ + 通知 + バックアップ | `GET /api/audit-logs/export.json` | T-V3-DRIFT-F-018-03 |
| F-018 監査ログ + 通知 + バックアップ | `GET /api/notifications` | T-V3-DRIFT-F-018-04 |
| F-018 監査ログ + 通知 + バックアップ | `POST /api/notifications/{id}/read` | T-V3-DRIFT-F-018-05 |
| F-018 監査ログ + 通知 + バックアップ | `POST /api/notifications/read-all` | T-V3-DRIFT-F-018-06 |
| F-023 アカウント設定 / プロフィール画面 | `GET /api/me` | T-V3-DRIFT-F-023-01 |
| F-023 アカウント設定 / プロフィール画面 | `PUT /api/me` | T-V3-DRIFT-F-023-02 |
| F-023 アカウント設定 / プロフィール画面 | `POST /api/me/api-keys` | T-V3-DRIFT-F-023-03 |
| F-023 アカウント設定 / プロフィール画面 | `DELETE /api/me/oauth/{provider}` | T-V3-DRIFT-F-023-04 |
| F-024 グローバル検索 (Cmd+K) + アカウントダッシュボード | `GET /api/search` | T-V3-DRIFT-F-024-01 |
| F-024 グローバル検索 (Cmd+K) + アカウントダッシュボード | `GET /api/accounts/{id}/dashboard` | T-V3-DRIFT-F-024-02 |
| F-026 Constitution (プロジェクト不変原則) | `GET /api/workspaces/{id}/constitution` | T-V3-DRIFT-F-026-01 |
| F-026 Constitution (プロジェクト不変原則) | `POST /api/workspaces/{id}/constitution/versions` | T-V3-DRIFT-F-026-02 |
| F-026 Constitution (プロジェクト不変原則) | `POST /api/workspaces/{id}/constitution/versions/{v}/approve` | T-V3-DRIFT-F-026-03 |
| F-027 オンボーディング flow (welcome / setup / AI intro) | `GET /api/me/onboarding` | T-V3-DRIFT-F-027-01 |
| F-027 オンボーディング flow (welcome / setup / AI intro) | `POST /api/me/onboarding/advance` | T-V3-DRIFT-F-027-02 |
| F-027 オンボーディング flow (welcome / setup / AI intro) | `POST /api/me/onboarding/skip` | T-V3-DRIFT-F-027-03 |
| F-028 メール配信 (signup verify / password reset / invitation / task notif / weekly summary) | `GET /api/email/templates` | T-V3-DRIFT-F-028-01 |
| F-028 メール配信 (signup verify / password reset / invitation / task notif / weekly summary) | `POST /api/email/test-send` | T-V3-DRIFT-F-028-02 |

## high 詳細 (method mismatch)

backend に同 path の router はあるが、method が違う。例: mock は `PUT /api/accounts/{id}` を呼ぶが backend は `PATCH` を実装。
**Task-decomposition Group D (Drift fix)** で対応 (どちらに合わせるかの判断含む)。

| Feature | Endpoint | backend 実装 method | Task ID |
|---|---|---|---|
| F-003 AI 社員ハイブリッド統合 (BMAD + Agent Teams + 既存) | `PUT /api/ai-employees/{id}` | path exists with methods ['DELETE', 'GET', 'PATCH'], mock expects PUT | T-V3-DRIFT-F-003-02 |
| F-004 account / workspace / members 階層管理 | `PUT /api/accounts/{id}` | path exists with methods ['DELETE', 'GET', 'PATCH'], mock expects PUT | T-V3-DRIFT-F-004-01 |
| F-004 account / workspace / members 階層管理 | `PUT /api/workspaces/{id}` | path exists with methods ['DELETE', 'GET', 'PATCH'], mock expects PUT | T-V3-DRIFT-F-004-05 |
| F-004 account / workspace / members 階層管理 | `GET /api/workspaces/{id}/invitations` | path exists with methods ['POST'], mock expects GET | T-V3-DRIFT-F-004-07 |
| F-006 機能・タスク分解 + acceptance-criteria (EARS) | `PUT /api/tasks/{id}` | path exists with methods ['GET', 'PATCH'], mock expects PUT | T-V3-DRIFT-F-006-04 |
| F-030 API トークン管理 / extras | `POST /api/me/api-tokens` | missing | T-V3-DRIFT-F-030-01 |
| F-031 Export pipeline (spec PDF / delivery report) | `POST /api/workspaces/{id}/exports` | missing | T-V3-DRIFT-F-031-01 |

## medium 詳細

| Feature | Endpoint | 推奨 | Task ID |
|---|---|---|---|
| F-029 デザインシステム / コンポーネントカタログ | `GET /api/design-system/tokens` | Component catalog API: B-1 で新規実装 (low priority) | T-V3-DRIFT-F-029-01 |

## low 詳細 (WebSocket / 観測のみ)

| Feature | Endpoint | 備考 | Task ID |
|---|---|---|---|
| F-005 ヒアリング → 仕様書 HTML パイプライン | `WS /ws/hearing/{session_id}` | WebSocket endpoint — backend WS routes not enumerated | T-V3-DRIFT-F-005-01 |
| F-010 Claude Code セッション・スポナー & swarm マネージャ | `WS /ws/sessions/{id}/log` | WebSocket endpoint — backend WS routes not enumerated | T-V3-DRIFT-F-010-03 |

## 推奨対応 (task-decomposition group 割当)

```
Wave 0 (Foundation)
  └─ API contract test (Schemathesis / Pact)  ← Foundation gate

Wave 1 (Backend / Vertical Slice)
  ├─ Group B-1: critical missing endpoint 実装 (94 件)
  │   ├─ F-001 auth: /api/auth/login /signup /password-reset /mfa/* /oauth/callback (6)
  │   ├─ F-003 ai-employees: org-chart / clone-from-user / test (3)
  │   ├─ F-005 spec: hearing/save / specs / comments (4)
  │   ├─ F-005b mocks: html GET/PUT / ai-edit / components / screen-flow (5)
  │   ├─ F-007 tasks: bulk-* / dag / export.csv / play-all (5)
  │   ├─ F-008 phases: gates / phases (2)
  │   ├─ F-009 dependencies: edges / impact-analysis (2)
  │   ├─ F-010 sessions: kill / pause / resume / rollback / kill-all (5)
  │   ├─ F-012 red-lines: violations / approve / reject (5)
  │   ├─ F-013 PRs + delivery + client portal (8)
  │   ├─ F-016 knowledge: search (1)
  │   ├─ F-017 cost: cost-summary export / token-limit (2)
  │   ├─ F-018 audit-logs / notifications (6)
  │   ├─ F-023 me: GET /me / POST /me/api-keys / DELETE /me/oauth (3)
  │   ├─ F-024 search: /api/search + /api/accounts/{id}/dashboard (2)
  │   ├─ F-026 constitution: versions / approve (2)
  │   └─ NEW features (F-027〜F-031): onboarding / email / design-system / api-tokens / exports (10+)
  └─ Group D: method mismatch fix (PUT → PATCH 統一 5 件)

Wave 2 (UI)
  └─ frontend が OpenAPI generated client を消費

Wave 3 (Polish)
  └─ contract test 再実行 / drift fix queue クローズ
```

## 次のアクション

1. **api-design スキル STEP 1-5** に features.json (api_endpoints) を渡し、OpenAPI 3.0 spec + lint-mapping.json + ears-ac-seed.json を生成
2. **task-decomposition スキル**: features.legacy_drift_notes から `T-V3-DRIFT-F-XXX-NN` タスクを Group B-1 / D に流し込み
3. **screens-API lint** (lint-mock.sh rule_id=screens-API) を CI に組み込み、新規 mock 追加時に backend 実在性を検証
4. **method mismatch 5 件** は ADR 起票して PUT/PATCH 統一方針を決定 (REST 慣習的には PATCH 推奨)

## 参照

- `docs/functional-breakdown/2026-05-16_v3/features.json` ← drift notes 完全版
- `docs/mocks/2026-05-15_v3/` ← bf-related-apis source
- `backend/routers/*.py` ← implementation source (104 ファイル / 453 endpoints)
- `skills/functional-breakdown/references/v3-core.md` ← v3 schema reference
- `skills/api-design/references/v3-core.md` ← ears_ac_seed 形式 reference

