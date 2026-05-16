# Build-Factory Profile — api-design

> このファイルは v3 api-design スキルを **Build-Factory プロジェクト** に適用するための profile 例。`references/v3-core.md` の汎用 placeholder (`<lint_runner>`, `<backend_router_path>` 等) を BF 固有値に mapping する。
> **他プロジェクトはこの profile をコピーして独自値で書き換える** (このファイルは強制ではなく「例」として位置づけ)。

## script path mapping

| 汎用名 | BF 固有 path |
|---|---|
| `<lint_runner>` | `scripts/lint-mock.sh` |
| `<ac_validator>` | `scripts/validate-tickets.py` |
| `<access_control_verifier>` | `scripts/verify-rls-coverage.py` |
| `<endpoint_existence_check>` | `scripts/lint-screens-api.py` (lint-mock.sh 内 lint #18) |

## lint rule id mapping

BF の `scripts/lint-mock.sh` 内の番号付き lint rule:

| 汎用概念 | BF lint rule id |
|---|---|
| endpoint-implementation-existence check (screens の related_apis × api endpoints × backend router) | **lint #18 screens-API** |
| mock ↔ 実装 drift 検知 | lint #17 mock-impl-diff |
| entity ↔ table naming 検証 | lint #19 entity-table-naming |

`lint-mapping.json` (api-design 出力) は `scripts/lint-screens-api.py` (lint #18) が消費する。

## 採用技術スタック (selected-stack.json から)

| カテゴリ | BF 採用 |
|---|---|
| API framework | **FastAPI** (Python 3.13) |
| ORM | **SQLAlchemy 2.0 async** |
| 入出力 schema | **Pydantic v2** |
| auth provider | **Supabase Auth (GoTrue)** + JWT (Bearer Token) + 2FA (TOTP) + OAuth (Anthropic / Slack / GitHub) |
| access control | **Supabase Postgres + RLS** (Row Level Security) — `access_control_policies` フィールドは `<table>:<policy_name>` 形式 (例: `auth_sessions:user_own_select`) |
| rate limit | FastAPI middleware (`slowapi` 等、ADR-013 で確定) |
| backend router base path | `backend/routers/` |
| backend service path | `backend/services/` |
| backend schemas path | `backend/schemas/` |
| frontend types output | `frontend/src/api/types.ts` |

## 型自動生成チェーン (BF 固有)

```
api-design SKILL.md
  ↓ STEP 5
docs/api-design/<date>_v3/openapi.yaml  ← 信頼源
  ↓ npx openapi-typescript openapi.yaml -o frontend/src/api/types.ts
frontend/src/api/types.ts  (生成物 / 編集禁止 / commit する)
  ↓ datamodel-codegen --input openapi.yaml --output backend/schemas.py
backend/schemas.py  (生成物 / 編集禁止 / commit する、任意)
  ↓ schemathesis run openapi.yaml --base-url http://localhost:8000
contract regression test (Foundation phase の CI gate に組込)
```

採用ツール:
- **TS client generator**: `openapi-typescript`
- **server-side schema generator**: `datamodel-code-generator` (Pydantic v2 出力)
- **contract test framework**: `Schemathesis` (OpenAPI fuzz) + 必要に応じ `Pact` (consumer-driven)

## Foundation phase の CI gate (BF: 8 CI gate)

api-design に関連する gate (8 CI gate のうち):
1. **gate #1 (mock lint)**: `bash scripts/lint-mock.sh` が pass — lint #18 screens-API で endpoint 実在性 + lint #17 mock-impl-diff
2. **gate #7 (TypeScript strict)**: `npm run tsc --strict` が pass — `frontend/src/api/types.ts` が openapi-typescript で再生成しても drift しない
3. **(任意) contract test gate**: `schemathesis run openapi.yaml` が pass — backend が OpenAPI spec の挙動を満たす

## phase 名 mapping

| 汎用名 | BF 固有 |
|---|---|
| Foundation phase | Phase 0 (Foundation 整備 / 8 CI gate + lint #1-19) |
| Backend phase | Phase 1 dogfood の backend 部 |
| UI phase | Phase 1 dogfood の frontend 部 |
| Polish phase | Phase 1.5 (REFACTOR) → Phase 2 (SaaS 公開) |

## 並列数

- N parallel sessions = **30-50** (Claude Code Wave 単位)
- N CI gates = **8**

## 出力先 path

| 出力 | BF path |
|---|---|
| API 仕様書 (Markdown) | `docs/api-design/<YYYY-MM-DD>_v3/api-spec.md` |
| OpenAPI YAML | `docs/api-design/<YYYY-MM-DD>_v3/openapi.yaml` |
| TS 型定義 | `frontend/src/api/types.ts` (openapi-typescript 自動生成) |
| 判断ログ JSON | `docs/api-design/<YYYY-MM-DD>_v3/decision-log.json` |
| ears-ac-seed.json | `docs/api-design/<YYYY-MM-DD>_v3/ears-ac-seed.json` |
| lint-mapping.json | `docs/api-design/<YYYY-MM-DD>_v3/lint-mapping.json` |

## 上流 skill 出力 path (pull する場所)

| 上流 | BF path |
|---|---|
| functional-breakdown features.json | `docs/functional-breakdown/<date>_v<N>/features.json` |
| functional-breakdown screens.json | `docs/functional-breakdown/<date>_v<N>/screens.json` |
| functional-breakdown entities.json | `docs/functional-breakdown/<date>_v<N>/entities.json` |
| architecture-design selected-stack.json | `docs/architecture/<date>_v<N>/selected-stack.json` |
| architecture-design adrs-to-create.json | `docs/architecture/<date>_v<N>/adrs-to-create.json` (ADR-013 AUTH 戦略) |

## 規約

- URL pattern: `/api/<resource>/...` (kebab-case)
- backend router naming: `backend/routers/<resource>.py::<verb_resource>` (例: `backend/routers/auth.py::login`)
- access_control_policies entry 形式: `<table>:<policy_name>` (例: `auth_sessions:user_own_select`)
- auth.role 値: `public` / `authenticated` / `account_owner` / `workspace_admin` / `system_admin` (BF の 6 role と整合)

## 数値例 (BF 実績)

- 想定 endpoint 総数: 100+ (43 screens × 平均 2-3 endpoint)
- 想定 auth role: 6 種 (public + 5 authenticated role)
- ADR 関連: ADR-013 (AUTH 戦略 / Supabase Auth + JWT)

## 補足

BF は **Lucide Icons / 絵文字禁止** / **ENGINE BASE green `#1a6648`** などの design token を持つが、これは API 設計には直接関係しないため省略。`docs/mocks/2026-05-09_v1/design-tokens.md` 参照。
