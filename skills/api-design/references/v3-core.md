# v3 Core Concepts — api-design

> このファイルは api-design スキルの **汎用 v3 概念** を定義する。プロジェクト固有値 (script path / 固有 lint rule 番号 / 採用ライブラリ等) は `references/profiles/<project>.md` に分離する。例として `references/profiles/build-factory.md` を参照。

## なぜ v3 か (汎用)

旧バージョン (v1 / v2) では:
- endpoint が定義されても backend に実装が無いケースが drift として残った (frontend が呼ぶ URL が backend に存在しない)
- AC (acceptance criteria) が自然文で書かれ、下流 task-decomposition で EARS 形式に翻訳する手間 + 翻訳時の意味ズレ
- `outputs_4xx` が「エラー時 400 を返す」レベルで止まり、実装段階で UNWANTED 条件が漏れる
- access control policy (RLS / RBAC 等) と endpoint の対応が無く、auth middleware 設計が遅れる
- API ↦ UI の依存方向が暗黙化し、UI が決まってから API を後付けする逆転が発生

v3 では:
- **endpoint-implementation-existence check** (project profile で具体 lint rule に mapping) で backend router 実在性を CI 検証
- **ears_ac_seed[]** を EARS 5 形式で書き、下流 task-decomposition の `acceptance_criteria.functional` に逐語コピー
- **outputs_4xx[]** を 401/403/404/409/422/429/500 で細分化、各エラー条件を UNWANTED EARS で記述
- **access_control_policies[]** (RLS / RBAC / policy id 等、project-defined) を endpoint 単位で明示
- **API↦UI 依存方向を Foundation phase で固定**: contract test (Schemathesis / Pact / consumer-driven) を Foundation phase の CI gate に組込

## API ↦ UI 依存方向 (Foundation phase 固定)

```
Foundation phase
  ├─ CI/CD pipeline (lint / format / type check / coverage gate)
  ├─ Contract test framework (Schemathesis / Pact / consumer-driven)  ← API spec を信頼源化
  ├─ Access control framework (RLS / RBAC / policy enforcement, if adopted)
  └─ OpenAPI / IDL generation pipeline

   ↓ Foundation gate passes (API spec が信頼源として固定)

Backend phase (per slice / per feature)
  ├─ API spec → router / handler 実装
  ├─ Service layer (business logic)
  ├─ Data layer (entity / migration / access control policy)
  └─ Backend integration test (RLS / RBAC matrix / business logic E2E)

   ↓ Backend gate passes

UI phase (per slice / per feature)
  ├─ Generated client (例: openapi-typescript) を消費
  ├─ Component implementation
  ├─ State management (data fetching / cache)
  └─ UI integration test (visual regression / interaction)

   ↓ UI gate passes

Polish phase
  └─ Performance / Security / Docs / Release
```

**核心原則**: **API は UI より先に決まる**。frontend が backend API を消費する依存方向を逆転させない。これを保証するため、contract test を **Foundation phase の CI gate** に組み込む (API spec が変更されたら即座に CI が破綻し、frontend / backend 両方が追随を強制される)。

## endpoint オブジェクト v3 schema (汎用)

```json
{
  "method": "POST",
  "path": "/api/auth/login",
  "summary": "ユーザーログイン",
  "feature_id": "F-001",
  "screen_ids": ["S-001"],
  "category": "auth",

  "auth": {
    "required": false,
    "role": "public",
    "middleware": ["rate_limit"]
  },

  "rate_limit": "5/min/ip",

  "access_control_policies": [],

  "request": {
    "headers": {"Content-Type": "application/json"},
    "body": {
      "email": {"type": "string", "format": "email", "required": true},
      "password": {"type": "string", "min_length": 8, "required": true},
      "mfa_code": {"type": "string", "pattern": "^[0-9]{6}$", "required": false}
    }
  },

  "outputs_2xx": {
    "status": 200,
    "body": {
      "access_token": "string",
      "refresh_token": "string",
      "user_id": "uuid",
      "mfa_required": "boolean"
    }
  },

  "outputs_4xx": [
    {
      "status": 401,
      "code": "INVALID_CREDENTIALS",
      "body": {"error": "invalid_credentials"},
      "trigger": "credentials don't match",
      "ears_form": "UNWANTED: If credentials are invalid, the system shall return 401 with generic message (no user enumeration)."
    },
    {
      "status": 422,
      "code": "VALIDATION_ERROR",
      "body": {"error": "validation_failed", "details": [...]},
      "trigger": "email format invalid or password < 8 chars",
      "ears_form": "UNWANTED: If email format is invalid or password is shorter than 8 characters, the system shall return 422 with field-level errors."
    },
    {
      "status": 429,
      "code": "RATE_LIMITED",
      "body": {"error": "rate_limited", "retry_after_sec": 900},
      "trigger": "5 failed login attempts within 15 min for the same IP",
      "ears_form": "EVENT-DRIVEN: When 5 failed login attempts occur within 15 min for the same IP, the system shall return 429 with retry_after_sec=900."
    }
  ],

  "ears_ac_seed": [
    "EVENT-DRIVEN: When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.",
    "STATE-DRIVEN: While MFA is enabled for the user, the system shall return 200 with mfa_required=true and not issue access_token until POST /api/auth/mfa/verify succeeds.",
    "UNWANTED: If credentials are invalid, the system shall return 401 with generic message (no user enumeration).",
    "EVENT-DRIVEN: When 5 failed login attempts occur within 15 min for the same IP, the system shall return 429 (rate-limited)."
  ],

  "related_entities": ["E-001 User", "E-038 AuthSession"],
  "implementation_path": "<backend_router_path>::<function_name>"
}
```

### 各フィールドの役割

| フィールド | 役割 / 検証 |
|---|---|
| `auth.required` | true / false |
| `auth.role` | `public` / `authenticated` / `account_owner` / `workspace_admin` 等 (project-defined) |
| `auth.middleware` | `require_auth` / `rate_limit` / `csrf_check` 等の middleware 配列 |
| `rate_limit` | `<count>/<window>/<scope>` (例: `5/min/ip`, `100/hour/user`) |
| `access_control_policies` | access control per endpoint (RLS / RBAC, if adopted) — 形式は project profile で定義 |
| `outputs_2xx` | 正常系の status + body schema |
| `outputs_4xx[]` | エラーごとに status / code / body / trigger / ears_form (UNWANTED 形式) |
| `ears_ac_seed[]` | EARS 5 形式の AC ドラフト — task-decomposition の Tier 2 functional AC に逐語コピー |
| `implementation_path` | backend 側の予定実装 path — endpoint-implementation-existence check で実在性検証 |

### EARS 5 形式の使い分け

| 形式 | 構文 | 使う場面 |
|---|---|---|
| **UBIQUITOUS** | The system shall ... | 常時の動作 (例: HTTPS 必須) |
| **EVENT-DRIVEN** | When [event], the system shall ... | リクエスト到着時の動作 (= 正常系の主軸) |
| **STATE-DRIVEN** | While [state], the system shall ... | session / feature flag / MFA 有効中 等 |
| **OPTIONAL** | Where [feature is enabled], the system shall ... | 機能 flag のあるエンドポイント |
| **UNWANTED** | If [unwanted condition], the system shall not ... | 4xx 各条件 |

各 endpoint は **EVENT-DRIVEN 1 件以上 + UNWANTED 1 件以上** が最低必須。

## outputs_4xx[] の細分化 (汎用)

すべての endpoint について、以下の status を **検討** する (該当しなければ省略 OK だが、検討した形跡は判断ログに残す):

| status | code 例 | 典型 trigger |
|---|---|---|
| 401 | `UNAUTHORIZED` / `INVALID_CREDENTIALS` | 認証情報なし or 不正 |
| 403 | `FORBIDDEN` / `ACCESS_DENIED` | 認証済だが権限なし (RLS / RBAC 越境含む) |
| 404 | `NOT_FOUND` | リソース不在 |
| 409 | `CONFLICT` / `EMAIL_ALREADY_EXISTS` | 一意制約 / 状態競合 |
| 422 | `VALIDATION_ERROR` | リクエスト schema / business rule 違反 |
| 429 | `RATE_LIMITED` | レート超過 |
| 500 | `INTERNAL_SERVER_ERROR` | サーバ内部エラー (詳細は外に出さない) |

各 4xx に **`code` / `body` / `trigger` (条件) / `ears_form` (UNWANTED 形式)** を必ず付与する。

## endpoint-implementation-existence check (汎用)

API spec に書かれた endpoint が backend に **実在** するか、CI で機械検証する。

検証内容 (汎用):
1. `screens.json[*].related_apis` (UI から参照される API 一覧) の各 entry が `api_design/endpoints[*].method + path` に存在する
2. `api_design/endpoints[*].implementation_path` が backend router の関数定義に対応する (path は project profile で具体化)
3. URL pattern が project-defined naming convention に従う (例: `/api/<resource>/...`)

各 project は具体的な lint rule id (例: 自プロジェクトの lint runner 内の rule 番号) を `references/profiles/<project>.md` で mapping。

`lint-mapping.json` (api-design 出力) を生成:

```json
{
  "version": "v3",
  "endpoints": [
    {
      "method": "POST",
      "path": "/api/auth/login",
      "implementation_path": "<backend_router_path>::login",
      "screen_ids_referencing": ["S-001"]
    }
  ]
}
```

これを project の lint runner (project profile で具体化) が読んで検証する。

## OpenAPI 自動生成 + 型同期 (汎用)

### 出力チェーン

```
api-design SKILL.md
  ↓ STEP 5 出力
openapi.yaml (OpenAPI 3.0 spec)  ← 信頼源
  ↓ TS client generator (例: openapi-typescript / openapi-generator)
<frontend>/api/types.ts  (生成物 / 編集禁止)
  ↓ server-side schema generator (例: datamodel-code-generator / openapi-generator-python, 任意)
<backend>/schemas.<py|ts|...>  (生成物 / 編集禁止)
  ↓ contract test (例: Schemathesis / Pact / Dredd, Foundation phase で採用)
contract regression test
```

### Foundation phase の CI gate に組込

API spec が変更されたら **以下を必ず CI で blocking gate にする**:
1. **型生成同期 check**: OpenAPI から再生成した型と現在のリポジトリ内の型が一致 (drift 検出)
2. **endpoint-implementation-existence check**: 全 endpoint に backend 実装が存在
3. **contract test (Schemathesis / Pact 等)**: 実 backend が OpenAPI spec の挙動 (status / body schema / 4xx pattern) を満たす

これらは **Foundation phase の N CI gate (project-defined gate set) のうち最低 1 つ** に必ず含める。frontend / backend が独立して spec から離れないようにするため。

## ears-ac-seed の出力 (ears-ac-seed.json)

STEP 5 で `ears-ac-seed.json` を生成:

```json
{
  "version": "v3",
  "skill": "api-design",
  "endpoints_count": 24,
  "ac_seeds": [
    {
      "endpoint": "POST /api/auth/login",
      "feature_id": "F-001",
      "ears_ac_seed": [
        "EVENT-DRIVEN: When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.",
        "UNWANTED: If credentials are invalid, the system shall return 401 with generic message."
      ]
    }
  ]
}
```

これを task-decomposition が読んで各 task の `acceptance_criteria.functional` に逐語コピー (3-tier AC の Tier 2 functional source)。

## 入力 (上流 skill から pull する内容)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **functional-breakdown** | features.json の api_endpoints (method/path/auth/inputs/outputs ドラフト)、screens.json の related_apis、entities.json (access control 紐付け用) |
| **architecture-design** | selected-stack.json (auth library / api framework / orm)、adrs-to-create.json (AUTH 戦略 ADR) |

## 出力 (下流 skill に渡す内容)

| 下流 | このスキルが供給する情報 |
|---|---|
| **task-decomposition** | ears-ac-seed.json → 各 task の `acceptance_criteria.functional` に逐語コピー |
| **endpoint-implementation-existence check (CI lint)** | lint-mapping.json で実在性検証対象を提供 |
| **access control verifier (CI lint, if adopted)** | 各 endpoint の `access_control_policies` 配列 |
| **frontend** | OpenAPI YAML → TS client generator で types.ts 自動生成 |
| **backend** | OpenAPI YAML → server-side schema generator で schemas を自動生成 (任意) |
| **contract test (Foundation phase)** | OpenAPI YAML → Schemathesis / Pact 等で contract regression |

## connections (汎用 / project profile で具体化)

| 概念 | 汎用名 | project profile で mapping する値の例 |
|---|---|---|
| lint runner | `<lint_runner>` | `scripts/lint-mock.sh` 等 |
| AC validator | `<ac_validator>` | `scripts/validate-tickets.py` 等 |
| access control verifier | `<access_control_verifier>` | `scripts/verify-rls-coverage.py` 等 |
| backend router base path | `<backend_router_path>` | `backend/routers/` 等 |
| frontend type output | `<frontend_types_path>` | `frontend/src/api/types.ts` 等 |
| TS client generator | `<ts_client_generator>` | `openapi-typescript` / `openapi-generator` 等 |
| server-side schema generator | `<server_schema_generator>` | `datamodel-code-generator` / `openapi-generator-python` 等 |
| contract test framework | `<contract_test>` | `Schemathesis` / `Pact` / `Dredd` 等 |
| API framework | `<api_framework>` | FastAPI / Express / NestJS / Hono 等 |
| access control mechanism | `<access_control>` | Supabase RLS / Casbin RBAC / OPA / 独自 middleware 等 |

## 互換性

- 旧 v1 / v2 出力ディレクトリは freeze (再生成しない)
- v3 出力先は project が決める (例: `docs/api-design/<date>_v3/`)
- endpoint オブジェクトは **v3 必須フィールド全付与** が原則 (欠落時は `[]` または `null` を明示)
