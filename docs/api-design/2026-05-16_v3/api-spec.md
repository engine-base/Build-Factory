# Build-Factory v3 API 仕様書

> **作成日**: 2026-05-16
> **バージョン**: v3
> **総エンドポイント数**: 140 (HTTP 138 + WebSocket 2)
> **対応機能数**: 35 features (F-001 〜 F-033)
> **対応 entity 数**: 68
> **採用ロール数**: 6 (R-001 〜 R-006)
> **trust source**: `docs/functional-breakdown/2026-05-16_v3/features.json`
> **生成スクリプト**: `_generate.py`

このドキュメントは **人間向け要約**。機械可読な信頼源は同ディレクトリの:
- `openapi.yaml` — OpenAPI 3.1 完全仕様 (140 endpoint)
- `ears-ac-seed.json` — Tier 2 functional AC seed (task-decomposition が逐語コピー)
- `lint-mapping.json` — endpoint-implementation-existence check 用 (lint #18 screens-API)
- `decision-log.json` — 設計判断ログ (12 件)
- `types.ts` — TypeScript 型 surface (openapi-typescript 生成物の wrapper)

---

## 1. 設計方針

### 1.1 API スタイル

- **RESTful HTTP/JSON** が主軸 (138/140 endpoint)。
- **WebSocket** は long-running stream 2 endpoint のみ:
  - `WS /ws/hearing/{session_id}` — F-005 (ヒアリング)
  - `WS /ws/sessions/{id}/log` — F-010 (セッションログ)
- GraphQL / RPC / gRPC は **採用しない**。理由: features.json が REST 構造を前提に書かれており、既存 backend 453 endpoint も REST。

### 1.2 URL 規約

- 全 endpoint は `/api/<resource>/...` (kebab-case)。
- バージョンプレフィクス (`/api/v1/`) は **付けない**。
- 将来 break する場合のみ `/api/v2/` を introduce する (deprecation policy: 半年以上)。
- BF profile `URL pattern` 規約 (`skills/api-design/references/profiles/build-factory.md` §規約) に準拠。

### 1.3 命名

- 動詞は HTTP method で表現 (action verb を path に含めない)。例外: `POST /api/tasks/{id}/play` のような **副作用が動詞でしか表現できない** ケースのみ。
- リソース名は **複数形**: `/api/tasks`, `/api/workspaces`, `/api/ai-employees`。
- ネストは 2 階層まで: `/api/workspaces/{id}/tasks`。3 階層以上は flat に展開する。

### 1.4 backend / frontend 連携

```
docs/api-design/2026-05-16_v3/openapi.yaml    ← 信頼源
  │
  ├─ openapi-typescript --input openapi.yaml \
  │                     --output frontend/src/api/openapi-generated.ts
  │   (frontend は types.ts 経由で消費)
  │
  ├─ datamodel-codegen --input openapi.yaml \
  │                    --output backend/schemas.py
  │   (Pydantic v2 出力 / 任意 / backend は SQLAlchemy + pydantic models を持つので diff のみチェック)
  │
  └─ schemathesis run openapi.yaml \
                     --base-url http://localhost:8000
      (Foundation phase CI gate に組込)
```

---

## 2. 認証

### 2.1 方式

- **Supabase Auth (GoTrue)** が発行する **JWT Bearer Token**。
- Header: `Authorization: Bearer <JWT>`
- OpenAPI: `components.securitySchemes.bearerAuth = { type: http, scheme: bearer, bearerFormat: JWT }`
- 2FA: TOTP (`/api/auth/mfa/enroll` + `/api/auth/mfa/verify`)
- OAuth: Anthropic / GitHub / Slack / Google (`/api/auth/oauth/{provider}/callback`)

### 2.2 認可ロール (`x-bf-auth-role`)

| ロール | OpenAPI security | 説明 |
|---|---|---|
| `public` | `[]` (no auth) | 認証不要。signup / login / OAuth callback / client portal token。 |
| `authenticated` | `[{bearerAuth: []}]` | Bearer JWT 必須。workspace context 不問。 |
| `member` | `[{bearerAuth: []}]` | workspace 内 member 以上。RLS で workspace_member 判定。 |
| `workspace_admin` | `[{bearerAuth: []}]` | workspace 管理者。 |
| `account_owner` | `[{bearerAuth: []}]` | account 所有者。skill / billing / 不可逆操作。 |

`roles.json` 内 6 ロール (Account Owner / Workspace Admin / Contributor / Viewer / Client / Monitor) と整合。
詳細マトリクスは `docs/functional-breakdown/2026-05-16_v3/roles.json` 参照。

### 2.3 endpoint レベル access control policy (`x-bf-access-control-policies`)

各 operation に `x-bf-access-control-policies: ["<table>:<policy_name>", ...]` を付与。
例: `users:authenticated_select`, `tasks:workspace_member_rw`, `accounts:account_owner_all`。

**消費者**: `scripts/verify-rls-coverage.py` (CI lint) — 全 endpoint が 1 つ以上の policy にマップされるか検証。

---

## 3. 共通仕様

### 3.1 エラーレスポンス (`components.responses` 共通参照)

| status | response 名 | code 例 | 典型 trigger |
|---|---|---|---|
| 401 | `Unauthorized` | `UNAUTHORIZED` / `INVALID_CREDENTIALS` | 認証情報なし or 不正 |
| 403 | `Forbidden` | `FORBIDDEN` / `ACCESS_DENIED` | 認証済だが権限なし (RLS 越境含む) |
| 404 | `NotFound` | `NOT_FOUND` | リソース不在 or RLS で不可視 |
| 409 | `Conflict` | `CONFLICT` / `EMAIL_ALREADY_EXISTS` | 一意制約 / 状態競合 |
| 422 | `ValidationError` | `VALIDATION_ERROR` | リクエスト schema / business rule 違反 |
| 429 | `RateLimited` | `RATE_LIMITED` | レート超過 (`Retry-After` header 必須) |
| 500 | `InternalServerError` | `INTERNAL_SERVER_ERROR` | サーバ内部エラー (詳細は外に出さない) |

全 4xx / 5xx は **`ErrorBody`** schema (error / code / message / details / retry_after_sec) を返す。
endpoint 固有の trigger / EARS form は `x-bf-error-seeds[]` に記録され、`ears-ac-seed.json` 経由で task-decomposition に渡る。

### 3.2 Rate limit (`x-bf-rate-limit`)

- 形式: `<count>/<window>/<scope>` (例: `5/min/ip`, `100/hour/user`, `20/min/workspace`)
- 実装: FastAPI middleware (slowapi、ADR-013 で確定)
- 超過時: 429 + `Retry-After: <sec>` header + `ErrorBody.retry_after_sec`

### 3.3 paginate

- query: `?page=1&page_size=20` または `?cursor=<opaque>`
- response body: `{ items: [...], total: int, next_cursor?: string }`
- features.json では `outputs_2xx` に `items` + `total` を明示している endpoint がこれに該当。

### 3.4 OpenAPI 拡張フィールド一覧

| 拡張キー | 場所 | 用途 |
|---|---|---|
| `x-bf-feature-id` | operation | F-NNN |
| `x-bf-screen-ids` | operation | このエンドポイントを呼ぶ画面 (S-NNN[]) |
| `x-bf-auth-role` | operation | public / authenticated / member / workspace_admin / account_owner |
| `x-bf-related-entities` | operation | 影響 entity (E-NNN[]) |
| `x-bf-access-control-policies` | operation | RLS policy (`<table>:<policy>`)[] |
| `x-bf-implementation-path` | operation | backend router 予定 path |
| `x-bf-rate-limit` | operation | rate limit 仕様 |
| `x-bf-protocol` | operation | `websocket` (WS のみ) |
| `x-bf-error-seeds` | operation | 4xx ごとの trigger + EARS form |
| `x-bf-drift` | operation | drift severity / task_id / 推奨対応 |
| `x-bf-version` | info | "v3" |
| `x-bf-generated-at` | info | "2026-05-16" |
| `x-bf-endpoint-count` | info | 140 |

---

## 4. 統計 / 分布

### 4.1 機能別 endpoint 数

| Feature | Endpoints | Auth roles | Drift critical |
|---|---|---|---|
| F-001 認証 (email+pwd / MFA / OAuth) | 6 | authenticated,public | 6 |
| F-002 既存 96 スキル整理 / archive 管理 | 4 | account_owner,authenticated | 1 |
| F-003 AI 社員ハイブリッド統合 | 6 | authenticated,workspace_admin | 3 |
| F-004 account / workspace / members 階層管理 | 17 | account_owner,authenticated,public,workspace_admin | 6 |
| F-005 ヒアリング → 仕様書 HTML パイプライン | 5 | authenticated,member | 4 |
| F-005b 画面モック自動生成パイプライン | 8 | member,workspace_admin | 8 |
| F-006 機能・タスク分解 + EARS AC | 6 | member,workspace_admin | 4 |
| F-007 多 view タスク管理 (Kanban / List / DAG) | 9 | member,workspace_admin | 7 |
| F-008 プロジェクト・フェーズ管理基盤 | 3 | member,workspace_admin | 3 |
| F-009 依存グラフ + 影響範囲伝搬 | 3 | member | 3 |
| F-010 Claude Code セッション・スポナー | 8 | member,workspace_admin | 7 |
| F-010a MCP サーバー (データ流通) | 3 | workspace_admin | 0 |
| F-011 リーダー AI 壁打ちループ | 3 | member,workspace_admin | 0 |
| F-012 赤線リスト + 自動停止 | 6 | member,workspace_admin | 6 |
| F-013 GitHub 連携 + 顧客レビュー | 12 | member,public,workspace_admin | 12 |
| F-014 Slack 通知 (片方向) | 4 | workspace_admin | 0 |
| F-015 HTML レポート全種 (7 種) | 2 | member | 0 |
| F-016 Obsidian ナレッジ母艦 | 2 | member | 2 |
| F-017 Langfuse self-host (観測 + コスト) | 3 | account_owner,workspace_admin | 2 |
| F-018 監査ログ + 通知 + バックアップ | 6 | authenticated,workspace_admin | 6 |
| F-023 アカウント設定 / プロフィール画面 | 4 | authenticated | 4 |
| F-024 グローバル検索 (Cmd+K) + ダッシュボード | 2 | authenticated,member | 2 |
| F-026 Constitution (プロジェクト不変原則) | 3 | member,workspace_admin | 3 |
| F-027 オンボーディング flow | 3 | authenticated | 3 |
| F-028 メール配信 | 4 | public,workspace_admin | 2 |
| F-029 デザインシステム / コンポーネントカタログ | 2 | member | 0 |
| F-030 API トークン管理 / extras | 3 | authenticated | 0 |
| F-031 Export pipeline (spec PDF / delivery report) | 2 | member | 0 |
| F-033 システムページ (404 / 500 / 403 / maintenance) | 1 | public | 0 |
| **計** | **140** | | **94** |

### 4.2 HTTP method 分布

| Method | Count |
|---|---|
| POST | 62 |
| GET | 58 |
| PUT | 9 |
| DELETE | 9 |
| WS | 2 |

### 4.3 認可ロール分布

| Role | Count |
|---|---|
| `member` | 49 |
| `workspace_admin` | 47 |
| `authenticated` | 23 |
| `public` | 12 |
| `account_owner` | 9 |

### 4.4 Drift severity 分布 (vs 既存 backend ~453 endpoint)

| Severity | Count | 推奨対応 |
|---|---|---|
| critical (未実装) | 94 | Group B-1 (Vertical Slice / Backend) |
| high (method mismatch) | 7 | Group D (Drift fix) |
| medium | 1 | Group D 低優先度 |
| low (WS) | 2 | 監視のみ |
| implemented (既存に対応あり) | 36 | REUSE / REFACTOR |

`api-drift-summary.md` 参照。各 endpoint の x-bf-drift.task_id (`T-V3-DRIFT-F-XXX-NN`) は task-decomposition Group B-1/D に流し込まれる。

---

## 5. 主要 endpoint カテゴリ抜粋

完全な 140 endpoint 列挙は `openapi.yaml` を参照。以下はカテゴリ別代表例。

### 5.1 認証 (F-001)

| Method | Path | Auth | Rate limit |
|---|---|---|---|
| POST | /api/auth/login | public | 5/min/ip |
| POST | /api/auth/signup | public | 3/hour/ip |
| POST | /api/auth/password-reset | public | 3/hour/ip |
| POST | /api/auth/mfa/enroll | authenticated | — |
| POST | /api/auth/mfa/verify | public | 5/min/user |
| GET | /api/auth/oauth/{provider}/callback | public | — |

### 5.2 タスク管理 (F-006 / F-007)

| Method | Path | Auth |
|---|---|---|
| GET | /api/workspaces/{id}/tasks | member |
| GET | /api/workspaces/{id}/tasks/dag | member |
| GET | /api/workspaces/{id}/tasks/export.csv | member |
| POST | /api/workspaces/{id}/tasks/bulk-play | workspace_admin |
| POST | /api/workspaces/{id}/tasks/bulk-archive | workspace_admin |
| POST | /api/tasks/{id}/play | workspace_admin |
| PUT | /api/tasks/{id} | member |
| POST | /api/tasks/{id}/comments | member |
| ... | ... | ... |

### 5.3 Claude Code セッション (F-010)

| Method | Path | Auth |
|---|---|---|
| GET | /api/workspaces/{id}/sessions | member |
| POST | /api/workspaces/{id}/sessions | workspace_admin |
| GET | /api/sessions/{id} | member |
| WS | /ws/sessions/{id}/log | member |
| POST | /api/sessions/{id}/kill | workspace_admin |
| POST | /api/sessions/{id}/pause | workspace_admin |
| POST | /api/sessions/{id}/resume | workspace_admin |
| POST | /api/sessions/{id}/rollback | workspace_admin |
| POST | /api/workspaces/{id}/sessions/kill-all | workspace_admin |

### 5.4 顧客レビュー (F-013 — client portal, token gated)

| Method | Path | Auth |
|---|---|---|
| GET | /api/client/workspaces/{token} | public |
| GET | /api/client/workspaces/{token}/spec | public |
| GET | /api/client/comments/{thread_id} | public |
| POST | /api/client/comments | public |
| POST | /api/comments/{id}/resolve | workspace_admin |
| POST | /api/workspaces/{id}/delivery/send-client | workspace_admin |

`{token}` は時間制限 + 1 workspace 単位の opaque token。`x-bf-access-control-policies: [public_workspace_view:token_match]`。

---

## 6. ears_ac_seed (Tier 2 functional AC source)

各 endpoint には EARS 5 形式 (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED) のドラフト AC が **最低 EVENT-DRIVEN 1 件 + UNWANTED 1 件** 付与されている。

source: features.json の `ears_ac_seed[]` を **逐語移植** + outputs_4xx trigger を UNWANTED form に展開。

例 (`POST /api/auth/login`):

```text
EVENT-DRIVEN: When valid email/password is submitted to POST /api/auth/login,
   the system shall return 200 with access_token + refresh_token + user_id.
UNWANTED: If invalid credentials are submitted to POST /api/auth/login,
   the system shall return 401 with a generic message (no user enumeration).
STATE-DRIVEN: While MFA is enabled for the user, the system shall require
   POST /api/auth/mfa/verify with a valid TOTP code before issuing access_token.
UNWANTED: If 5 failed login attempts occur within 15 min from the same IP,
   the system shall return 429 with retry_after_sec=900.
EVENT-DRIVEN: When OAuth callback GET /api/auth/oauth/{provider}/callback is invoked
   with a valid state token, the system shall complete the OAuth handshake and
   return access_token + refresh_token.
UNWANTED: If OAuth state token does not match the originating session,
   the system shall return 401 and reject the callback.
EVENT-DRIVEN: When POST /api/auth/password-reset is called with an email,
   the system shall always return 2xx (no account enumeration) and send reset email
   only if the account exists.
UNWANTED: If invalid credentials (generic, no user enumeration), the system shall return 401.
UNWANTED: If account locked, the system shall return 403.
UNWANTED: If email format invalid or password too short, the system shall return 422.
EVENT-DRIVEN: When rate limit exceeded (5 failed attempts in 15 min),
   the system shall return 429 (rate limited).
UNWANTED: If internal server error, the system shall return 500.
```

**task-decomposition が逐語コピー** する (paraphrase 禁止)。差異が出ると EARS validator (`scripts/validate-tickets.py`) が fail する。

---

## 7. Foundation phase CI gate との結合

BF 8 CI gate のうち api-design 関連は:

| Gate | 内容 | 検証コマンド |
|---|---|---|
| #1 mock lint | `lint-mock.sh` 全 19 ルール (うち #18 screens-API は lint-mapping.json を消費) | `bash scripts/lint-mock.sh` |
| #7 TypeScript strict | `frontend/src/api/openapi-generated.ts` が openapi.yaml と drift なし | `npm run tsc --strict` |
| (任意) contract test | Schemathesis が openapi.yaml に対し fuzz 通過 | `schemathesis run openapi.yaml --base-url <staging>` |

`lint-mapping.json` の `endpoints[].implementation_path` が **backend router の関数定義に存在** することを `scripts/lint-screens-api.py` が確認する。94 critical drift が解消されるまで gate #1 は intentional fail を返す (task-decomposition Group B-1 で順次クリア)。

---

## 8. 次のアクション (下流 skill 引き継ぎ)

1. **task-decomposition** (次フェーズ):
   - `ears-ac-seed.json` を読み込み、各 task の `acceptance_criteria.functional` に逐語コピー。
   - `lint-mapping.json` の `drift_task_id` (T-V3-DRIFT-F-XXX-NN) を Group B-1 / D に割当。
2. **frontend** scaffold:
   - `npx openapi-typescript openapi.yaml -o frontend/src/api/openapi-generated.ts`
   - `types.ts` をそのまま `frontend/src/api/types.ts` に配置。
3. **backend** scaffold:
   - `datamodel-codegen --input openapi.yaml --output backend/schemas.py` (任意 / SQLAlchemy models 優先)。
   - 94 critical endpoint の router 実装 (Group B-1)。
4. **CI integration**:
   - `scripts/lint-screens-api.py` が `lint-mapping.json` を消費するよう実装。
   - Schemathesis を staging に対し実行する GitHub Action 追加。

---

## 9. 参照

- `openapi.yaml` (このディレクトリ) — OpenAPI 3.1 完全仕様
- `ears-ac-seed.json` — 140 endpoint × EARS seeds
- `lint-mapping.json` — endpoint-implementation-existence check 入力
- `decision-log.json` — 12 設計判断 (AD-001 〜 AD-012)
- `types.ts` — TypeScript 型 surface (openapi-typescript wrapper)
- `docs/functional-breakdown/2026-05-16_v3/features.json` — 信頼源 (api_endpoints / ears_ac_seed)
- `docs/functional-breakdown/2026-05-16_v3/entities.json` — entity / RLS policy 紐付け
- `docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md` — drift 一覧
- `skills/api-design/references/v3-core.md` — v3 汎用仕様
- `skills/api-design/references/profiles/build-factory.md` — BF profile

---

**最終更新**: 2026-05-16
**生成スクリプト**: `_generate.py`
**生成エンドポイント数**: 140 (138 HTTP + 2 WebSocket)
**unique operationId**: 140 / 140
**dangling \$ref**: 0
**EARS minimum (EVENT-DRIVEN + UNWANTED)**: 140 / 140 endpoints OK
