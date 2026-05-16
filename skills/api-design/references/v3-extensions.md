# v3 拡張 — api-design

> 2026-05-15 v3 から、api-design の各 endpoint に **auth role / rate_limit / RLS policy / outputs_4xx 必須 / ears_ac_seed** を付与。
> functional-breakdown の features.json と architecture-design の selected-stack.json を pull し、下流 task-decomposition で 3-tier AC の Tier 2 functional に逐語コピーされる。

## なぜ v3 拡張が必要か

v1 / v2 では:
- endpoint が定義されても backend に実装が無いケース (S-001 login 等) が drift として残った
- AC が自然文で書かれ、task-decomposition 側で EARS 形式に翻訳する手間 + 翻訳時の意味ズレ
- outputs_4xx が「エラー時 400 を返す」レベルで止まり、実装段階で UNWANTED 条件が漏れる
- RLS policy と endpoint の対応が無く、auth middleware 設計が遅れる

v3 では:
- **lint #18 screens-API** で backend router 実在性を CI 検証
- **ears_ac_seed[]** を EARS 5 形式で書き、task-decomposition の `acceptance_criteria.functional` に逐語コピー
- **outputs_4xx[]** を 401/403/404/409/422/429/500 で細分化、各エラー条件を UNWANTED EARS で記述
- **rls_policies[]** を endpoint 単位で明示、verify-rls-coverage 連携

## endpoint オブジェクト v3 schema

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

  "rls_policies": [],

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
  "implementation_path": "backend/routers/auth.py::login"
}
```

### 各フィールドの役割

| フィールド | 役割 / 検証 |
|---|---|
| `auth.required` | true / false |
| `auth.role` | `public` / `authenticated` / `account_owner` / `workspace_admin` / etc. |
| `auth.middleware` | `require_auth` / `rate_limit` / `csrf_check` 等の middleware 配列 |
| `rate_limit` | `<count>/<window>/<scope>` (例: `5/min/ip`, `100/hour/user`) |
| `rls_policies` | `<table>:<policy_name>` (例: `auth_sessions:user_own_select`) — verify-rls-coverage で検証 |
| `outputs_2xx` | 正常系の status + body schema |
| `outputs_4xx[]` | エラーごとに status / code / body / trigger / ears_form (UNWANTED 形式) |
| `ears_ac_seed[]` | EARS 5 形式の AC ドラフト — task-decomposition の Tier 2 functional AC に逐語コピー |
| `implementation_path` | backend 側の予定実装 path — lint #18 で実在性検証 |

### EARS 5 形式の使い分け

| 形式 | 使う場面 |
|---|---|
| **UBIQUITOUS** | The system shall ... | 常時の動作 (例: HTTPS 必須) |
| **EVENT-DRIVEN** | When [event], the system shall ... | リクエスト到着時の動作 (= 正常系の主軸) |
| **STATE-DRIVEN** | While [state], the system shall ... | session / feature flag / MFA 有効中 等 |
| **OPTIONAL** | Where [feature is enabled], the system shall ... | 機能 flag のあるエンドポイント |
| **UNWANTED** | If [unwanted condition], the system shall not ... | 4xx 各条件 |

各 endpoint は **EVENT-DRIVEN 1 件以上 + UNWANTED 1 件以上** が最低必須。

## lint #18 screens-API 検証

`scripts/lint-screens-api.py` が以下を検証:
1. `screens.json[*].related_apis` の各 entry が `api_design/endpoints[*].method + path` に存在する
2. `api_design/endpoints[*].implementation_path` が `backend/routers/*.py` の関数定義に対応する
3. URL pattern が `/api/<resource>/...` の規約に従う

`lint-mapping.json` (api-design 出力) を生成:

```json
{
  "version": "v3",
  "endpoints": [
    {
      "method": "POST",
      "path": "/api/auth/login",
      "implementation_path": "backend/routers/auth.py::login",
      "screen_ids_referencing": ["S-001"]
    }
  ]
}
```

これを `scripts/lint-screens-api.py` が読んで検証する。

## OpenAPI 自動生成 + TS 型同期

### 出力チェーン

```
api-design SKILL.md
  ↓ STEP 5 出力
openapi.yaml (OpenAPI 3.0 spec)
  ↓ openapi-typescript / openapi-generator
frontend/src/api/types.ts (TS 型自動生成)
backend/schemas.py (Pydantic 自動生成 / 任意)
```

### 推奨ツール

- **openapi-typescript** (TS 型生成) — `npx openapi-typescript openapi.yaml -o frontend/src/api/types.ts`
- **datamodel-code-generator** (Pydantic 生成 / Python 側) — `datamodel-codegen --input openapi.yaml --output backend/schemas.py`
- **Schemathesis** (contract test) — `schemathesis run openapi.yaml --base-url http://localhost:8000`

### CI 連携

- gate #7 (TypeScript strict) で types.ts の同期が壊れていれば fail
- gate #1 (mock lint) の lint #18 で endpoint 実在性を検証
- (任意) Pact / Schemathesis で frontend ↔ backend contract を回帰検証

## ears_ac_seed の出力 (ears-ac-seed.json)

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

これを task-decomposition が読んで各 task の `acceptance_criteria.functional` に逐語コピー。

## connections (連携先一覧)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **functional-breakdown** | features.json の api_endpoints (method/path/auth/inputs/outputs ドラフト) |
| **architecture-design** | selected-stack.json (auth library / api framework) + adrs-to-create.json (AUTH 戦略 ADR-013) |

| 下流 | このスキルが供給する情報 |
|---|---|
| **task-decomposition** | ears_ac_seed → 各 task の acceptance_criteria.functional に逐語コピー |
| **lint #18 screens-API** | lint-mapping.json で実在性検証対象を提供 |
| **verify-rls-coverage** | 各 endpoint の rls_policies 配列 |
| **frontend** | OpenAPI YAML → openapi-typescript で types.ts 自動生成 |
| **backend** | OpenAPI YAML → datamodel-codegen で Pydantic schemas.py 自動生成 (任意) |

## 互換性

- v1 (`docs/api-design/2026-05-09_v1/`): freeze。v3 拡張なし
- v3 (`docs/api-design/<date>_v3/`): 新規出力先 / endpoint オブジェクトに v3 必須フィールド込み
