# Build-Factory v3 Phase 1.0-fix — Group B-1 (Critical-Missing API) タスク分解

> 作成日: 2026-05-17
> profile: `skills/task-decomposition/references/profiles/build-factory.md`
> output: `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b1-api-missing.json`
> 上流: `docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md` (critical 94 件)
> 上流 OpenAPI: `docs/api-design/2026-05-16_v3/openapi.yaml`

## サマリー

| metric | 値 |
|---|---|
| 総 task 数 | 94 |
| group 内訳 | B-1 (critical-missing endpoint 実装) 94 |
| category | backend 94 |
| label | NEW 94 |
| deliverable_layer | backend 94 |
| 推定総工数 | 283h |
| 並列実時間 | ~47h (parallel capacity 6 想定) |
| Wave | 3 (W1 / W2 / W3) |
| 想定 PR 数 | 94 |

## 背景

Phase 1 完走宣言の検証で **mock 宣言 / backend 未実装の critical-missing endpoint が 94 件** 検出された (`api-drift-summary.md` severity:critical)。
これら 94 件は v3 OpenAPI 仕様 (`openapi.yaml`) に **operationId / request-schema / response-schema / error-seeds / x-bf-rate-limit / x-bf-access-control-policies / x-bf-drift.task_id** が全て確定済みであり、本 Group B-1 で **1 endpoint = 1 task** に分解して並列実装する。

## Wave 配置

Wave 0 (本 task 群) は **Phase 1.0-fix 着手 wave** であり Group A (Foundation: Schemathesis contract test gate) の完了を前提とする。

### Wave 1 (Foundation / 認証 + アカウント基盤) — 23 tasks / 68h

`auth + skills + ai-employees + accounts + me + onboarding` の **認証 / アイデンティティ基盤** を先行実装。後続 Wave のテストが認証 token を発行できるようにする。

| Feature | endpoint 数 | 備考 |
|---|---:|---|
| F-001 認証 (login / signup / password-reset / mfa enroll&verify / oauth callback) | 6 | **head-of-line** — depends_on=[] |
| F-002 skills test | 1 | |
| F-003 AI 社員 (org-chart / clone-from-user / test) | 3 | |
| F-004 account / workspace member CRUD | 6 | |
| F-023 me profile (GET/PUT/api-keys/oauth-delete) | 4 | |
| F-027 onboarding (GET / advance / skip) | 3 | |

### Wave 2 (Workspace-scoped CRUD) — 32 tasks / 82h

ワークスペース内のリソース (spec / mock / requirement / task / phase / dependency / constitution) CRUD。**Wave 1 の F-001 login 完了が前提**。

| Feature | endpoint 数 |
|---|---:|
| F-005 spec (hearing/save / specs / comments) | 4 |
| F-005b mocks + components + screen-flow | 8 |
| F-006 requirements + task comments | 4 |
| F-007 tasks (kanban / dag / bulk / play) | 7 |
| F-008 phases + gate | 3 |
| F-009 dependencies + impact-analysis | 3 |
| F-026 constitution + version approval | 3 |

### Wave 3 (Cross-cutting / 観測 / 顧客面) — 39 tasks / 133h

セッション / PR / 通知 / 検索 / メール / コスト等の cross-cutting 機能。**外部 API 依存が多いため最後**。

| Feature | endpoint 数 |
|---|---:|
| F-010 sessions (kill / pause / resume / rollback) | 7 |
| F-012 red-lines / violations + approval | 6 |
| F-013 GitHub PR + delivery + client portal | 12 |
| F-016 knowledge + search | 2 |
| F-017 observability (cost-summary / token-limit) | 2 |
| F-018 audit-logs + notifications | 6 |
| F-024 global search + account dashboard | 2 |
| F-028 email templates + test-send | 2 |

## 依存関係 (DAG)

```
Wave 1 head:
  T-V3-B1-001 (POST /api/auth/login)  ←  Foundation (depends_on=[])
  T-V3-B1-002 (POST /api/auth/signup)  ←  Foundation (depends_on=[])
  T-V3-B1-003 (POST /api/auth/password-reset)  ←  depends_on=[B1-002]
  T-V3-B1-004..006 (mfa/oauth)  ←  depends_on=[B1-001]
  W1 other tasks (F-002〜F-027)  ←  depends_on=[B1-001]

Wave 2 全 task  ←  depends_on=[B1-001]  (token issuance 必須)

Wave 3 全 task  ←  depends_on=[B1-001]  (token issuance 必須)
```

並列実行ルール: depends_on を満たした task は **wave 内で全並列可** (file mutex は `backend/app/main.py` / `backend/tests/contract/test_openapi_contract.py` のみ shared)。

## 3-tier acceptance_criteria (各 task 共通方針)

各 task は **平均 15.9 件の AC** (合計 1494 件) を持つ:

- **structural** (~3 件): FastAPI route 実在 / `backend/app/main.py` 登録 / Schemathesis contract test pass
- **functional** (~8 件): success path (2xx) + 各 `outputs_4xx` (401/403/404/409/422/429/500) の openapi `x-bf-error-seeds` を 1:1 で EARS 化 + RLS policy enforcement (`x-bf-access-control-policies`) + rate-limit (`x-bf-rate-limit`)
- **regression** (~6 件): pytest -k <task_id> coverage >= 70% / pyright strict / ruff / validate-tickets / lint-mock 17/17 / audit-md-check

全 AC は **EARS 5 形式** (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED) のいずれか。

## work_package_boundary (各 task 共通)

```
editable:
  - backend/routers/<module>.py
  - backend/services/<module>.py
  - backend/schemas/<module>.py
  - backend/tests/integration/test_<module>_endpoints.py
  - docs/audit/2026-05-16_v3/T-V3-B1-NNN.md

shared_no_concurrent_edit:
  - backend/app/main.py
  - backend/tests/contract/test_openapi_contract.py

readonly:
  - docs/api-design/2026-05-16_v3/openapi.yaml
  - docs/functional-breakdown/2026-05-16_v3/{features,entities,api-drift-summary}.json,.md

forbidden:
  - frontend/
  - supabase/migrations/
  - scripts/lint-mock.sh
  - scripts/validate-tickets.py
  - .claude/settings.json
```

`<module>` は feature_id ベースで決定 (例: F-001 → `auth`, F-005b → `mocks`, F-013 → `github_pr`)。

## 着手プロトコル (各 task 共通)

1. `cp docs/audit/2026-05-13_v2/_template.md docs/audit/2026-05-16_v3/T-V3-B1-NNN.md`
2. tickets-group-b1-api-missing.json から該当 task の 3-tier AC を逐語コピーして audit MD に貼り付け
3. branch 作成: `git checkout -b claude/T-V3-B1-NNN`
4. work_package_boundary.editable 配下のみ編集 (forbidden / readonly を尊重)
5. openapi.yaml の対象 operationId を 1 つずつ確認しながら実装 (request/response schema 完全準拠)
6. Schemathesis contract test に新 operationId 用 stub を `backend/tests/contract/test_openapi_contract.py` に追加
7. 完了後 3-tier AC × audit MD impl line × CI gate (8 件: pytest / pyright / ruff / coverage / validate-tickets / lint-mock / audit-md / Schemathesis) を 1:1 で確認
8. PR 作成 → CI gate auto-merge

## 重要 (慎重に扱う事項)

- **依存 chain 単一点**: 全 non-F-001 task が **T-V3-B1-001 (login)** に依存。B1-001 の遅延が全体を block する。**最優先で着手**。
- **security_critical**: F-001 auth 系 6 件 / F-013 PR merge / `/mfa/` 系 — credential / token 流出が無いことを functional AC で gate.
- **external_api_dependent**: F-001 OAuth callback (Anthropic/Slack/GitHub) / F-013 GitHub PR API / F-016 Obsidian Vault FS / F-017 Langfuse / F-028 email provider — mock 化必須.
- **public_token_path**: F-013 `/api/client/*` (顧客レビュー) — Supabase JWT ではなく per-workspace public-link token. RLS とは別系統の RBAC を実装.
- **destructive**: F-010 session kill/rollback / F-013 PR merge — 副作用が不可逆. UNWANTED AC で safety net.

## 関連ファイル

- 構造化 JSON (94 task): `tickets-group-b1-api-missing.json`
- 生成スクリプト (再生成可): `_generate_group_b1_api_missing.py`
- audit MD 94 件 (要生成): `docs/audit/2026-05-16_v3/T-V3-B1-001.md` 〜 `T-V3-B1-094.md`
- 上流 OpenAPI: `docs/api-design/2026-05-16_v3/openapi.yaml`
- 上流 drift summary: `docs/functional-breakdown/2026-05-16_v3/api-drift-summary.md`
- 上流 features.json: `docs/functional-breakdown/2026-05-16_v3/features.json`
- profile: `skills/task-decomposition/references/profiles/build-factory.md`
