# 3-tier Acceptance Criteria スキーマ

> task-decomposition スキルが各タスクの `acceptance_criteria` を生成するときの厳密スキーマ
> source of truth: `docs/task-decomposition/2026-05-15_v3/ACCEPTANCE_CRITERIA_SCHEMA.md`

## なぜ 3-tier か

v1 (2026-05-09) は `regression` のみ (= unit test PASS + lint PASS) で done と判定した結果、画面 drift 21 件 / API 不在 8 件 / RLS 不足 28 件が検知されずに done フラグが立った。

**3 種全 pass で初めて done** にすることで構造的に漏れを防ぐ。

## 構造

各タスクの `acceptance_criteria` は **3 配列** を持つ JSON:

```json
{
  "acceptance_criteria": {
    "structural": [...],
    "functional": [...],
    "regression": [...]
  }
}
```

## Tier 1: structural — 画面 / Spec の構造一致

UI を持つタスクで必須 (backend-only タスクは省略可)。

| 検証対象 | 検査方法 |
|---|---|
| mock HTML の `<h1>` テキストと実装 page.tsx の `<h1>` が完全一致 | `scripts/lint-mock-impl-diff.sh` (lint #17) |
| mock の Hero KPI ラベルと実装 KPI コンポーネントの label prop が一致 | 同上 |
| mock の主要セクション見出し (h2) と実装 `<section>` 見出しが集合として一致 | 同上 |
| mock の `<meta name="bf-screen-id">` が実装 page.tsx の screen-id コメントと一致 | 同上 |

**書式例 (EARS STATE-DRIVEN)**:
```
STATE-DRIVEN: While the page is rendered, the system shall display an h1 element with the exact text "10 案件 俯瞰" (matching docs/mocks/2026-05-15_v3/account/S-006-account-dashboard.html h1).
```

## Tier 2: functional — Spec の機能要求一致

全タスクで必須。**EARS 5 形式のいずれかで記述**。

| 検証対象 | 検査方法 |
|---|---|
| screens.json の `related_apis` が backend に存在し 200/4xx を正しく返す | `scripts/lint-screens-api.py` (lint #18) + pytest |
| entities.json の関連 entity の RLS policy が存在し unauthorized を拒否 | `scripts/verify-rls-coverage.py` |
| feature.happy_path / error_paths が実装で動く | pytest (機能 test) |
| EARS 5 形式で spec を逐語表現 | `scripts/validate-ears-ac.py` |

**EARS 5 形式**:

| 形式 | 書式 |
|---|---|
| **UBIQUITOUS** | The system **shall** ... |
| **EVENT-DRIVEN** | When [event], the system **shall** ... |
| **STATE-DRIVEN** | While [state], the system **shall** ... |
| **OPTIONAL** | Where [feature is enabled], the system **shall** ... |
| **UNWANTED** | If [unwanted condition], the system **shall not** ... |

**書式例**:
```
EVENT-DRIVEN: When GET /api/accounts/{id}/dashboard is called by an account_owner, the system shall return 200 with JSON containing { active_projects, running_sessions, monthly_cost, anomalies_24h }.
UNWANTED: If the caller is not a member of the account, the system shall return 403 (verified by RLS policy on accounts.account_members).
```

## Tier 3: regression — 退行検知

全タスクで必須。**v1 時点ではここしか見ていなかった**。

| 検証対象 | 検査方法 |
|---|---|
| unit test PASS | pytest backend/tests/ + jest frontend/tests/ |
| lint PASS | ruff + ESLint + lint-mock.sh (19/19) |
| TypeScript strict 通過 | tsc --noEmit |
| pyright strict 通過 | pyright |
| coverage ≥ 70% | pytest --cov / vitest --coverage |
| (UI task のみ) Playwright e2e PASS | playwright/test |

**書式例**:
```
The system shall pass backend/tests/test_T-V3-AUTH-01.py (>= 8 test cases: success, wrong_email, wrong_password, rate_limited, mfa_required, sql_injection_attempt, csrf_check, replay_attack).
The system shall pass pyright strict mode with 0 errors.
The system shall maintain coverage >= 70% on touched files.
```

## タスク種別ごとの必須 Tier

| タスク category | structural | functional | regression |
|---|:---:|:---:|:---:|
| frontend (画面実装) | ✅ 必須 | ✅ 必須 | ✅ 必須 |
| backend (API 実装) | ⚪ 省略可 | ✅ 必須 | ✅ 必須 |
| db (schema/migration) | ⚪ 省略可 | ✅ 必須 (RLS) | ✅ 必須 |
| test | ⚪ 省略可 | ✅ 必須 | ✅ 必須 |
| infra (lint/CI) | ⚪ 省略可 | ✅ 必須 | ✅ 必須 |
| cleanup | ⚪ 省略可 | ⚪ 省略可 | ✅ 必須 |

省略する場合は明示的に `"structural": []` を書く。`null` や field 欠落は validator が reject する。

## audit MD への展開

`structural` / `functional` / `regression` の各項目は audit MD (`docs/audit/<date>_v<N>/T-XXX.md`) で逐語マッピングする:

```markdown
## Tier 1: Structural
- [ ] AC-S1: mock h1 「10 案件 俯瞰」== impl <h1> → frontend/app/page.tsx:23
- [ ] AC-S2: mock KPI 4 ラベル == impl → frontend/components/DashboardKpis.tsx:14-28

## Tier 2: Functional (AC verbatim)
- [ ] AC-F1: EVENT-DRIVEN When GET /api/accounts/{id}/dashboard ... → backend/routers/accounts.py:42-58
- [ ] AC-F2: UNWANTED If caller not member ... → backend/middleware/rls.py:31-45

## Tier 3: Regression
- [ ] pytest: 8/8 PASS
- [ ] coverage: 84% (>= 70%)
- [ ] pyright: 0 errors
- [ ] lint-mock: 19/19 OK

## Decision: ✅ DONE / 🟡 BLOCKED / 🔴 GAP
```

generic 文言 (`shall implement T-XXX as specified by feature F-XXX` 等) は **不可**。`scripts/validate-audit-md.py` が generic phrase を検出して reject する。
