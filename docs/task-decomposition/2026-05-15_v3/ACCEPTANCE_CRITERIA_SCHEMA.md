# v3 Acceptance Criteria Schema — 3-tier 定義

> **作成日**: 2026-05-15
> **目的**: v1 で発生した「test pass = done」の判定誤りを構造的に防ぐ
> **適用範囲**: v3 (`docs/task-decomposition/2026-05-15_v3/`) 配下の全 task

## 背景

v1 (2026-05-09 / 187 task) は次の判定で done フラグを立てていた:
- `regression` のみ (= unit test PASS + lint PASS)

結果、以下が **検知されずに done** となった:
- 画面の見出し / KPI / セクションが mock と一致しないケース (S-006 で発覚)
- API endpoint が backend に存在しないケース (S-001〜S-005 / `/api/accounts/{id}/dashboard`)
- RLS policy が宣言数の 35% しか実装されていなかったケース

## v3 の Done 定義

各 task は **acceptance_criteria を 3 種類のサブ配列** に分けて記述する。**3 種全て pass で初めて done フラグを立てる**。

```json
{
  "acceptance_criteria": {
    "structural": [...],
    "functional": [...],
    "regression": [...]
  }
}
```

### Tier 1 : `structural` — 画面 / Spec の構造一致

UI を持つ task で必須 (backend-only task は省略可)。

| 検証対象 | 検査方法 |
|---|---|
| mock HTML の `<h1>` テキストと実装 page.tsx の `<h1>` が完全一致 | `scripts/lint-mock-impl-diff.sh` (新規, lint #17) |
| mock の Hero KPI ラベルと実装の KPI コンポーネントの label prop が一致 | 同上 |
| mock の主要セクション見出し (h2) と実装の `<section>` 見出しが集合として一致 | 同上 |
| mock の `<meta name="bf-screen-id">` が実装の対応 page.tsx の screen-id コメントと一致 | 同上 |

**書式例**:
```
STATE-DRIVEN: While the page is rendered, the system shall display an h1 element with the exact text "10 案件 俯瞰" (matching docs/mocks/2026-05-09_v1/account/S-006-account-dashboard.html#L42).
```

### Tier 2 : `functional` — Spec の機能要求一致

全 task で必須。EARS notation の 5 形式のいずれかで記述する。

| 検証対象 | 検査方法 |
|---|---|
| screens.json の `related_apis` に書かれた endpoint が backend に存在し、200/4xx を正しく返す | `scripts/lint-screens-api.py` (新規, lint #18) + pytest |
| entities.json の関連 entity に対する RLS policy が CREATE POLICY で存在し、unauthorized は拒否 | `scripts/verify-rls-coverage.py` (拡張) |
| feature.happy_path / error_paths のフローが実装で動く | pytest (機能 test) |
| EARS の UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED いずれかで spec を逐語的に表現 | `scripts/validate-ears-ac.py` |

**書式例**:
```
EVENT-DRIVEN: When GET /api/accounts/{id}/dashboard is called by an account_owner, the system shall return 200 with JSON containing { active_projects, running_sessions, monthly_cost, anomalies_24h }.
UNWANTED: If the caller is not a member of the account, the system shall return 403 (verified by RLS policy on accounts.account_members).
```

### Tier 3 : `regression` — 退行検知

全 task で必須。**v1 時点ではここしか見ていなかった**。

| 検証対象 | 検査方法 |
|---|---|
| unit test PASS | pytest backend/tests/ + jest frontend/tests/ |
| lint PASS | ruff (Python) + ESLint (TS) + lint-mock.sh 全 19 check |
| TypeScript strict 通過 | tsc --noEmit |
| pyright strict 通過 | pyright (新規ゲート) |
| coverage ≥ 70% | pytest --cov / vitest --coverage |
| (UI task のみ) Playwright e2e PASS | playwright/test |

**書式例**:
```
The system shall pass backend/tests/test_T-V3-AUTH-01.py (>= 8 test cases: success, wrong_email, wrong_password, rate_limited, mfa_required, sql_injection_attempt, csrf_check, replay_attack).
The system shall pass pyright strict mode with 0 errors.
The system shall maintain coverage >= 70% on touched files.
```

## task 個別の必須要素

各 v3 task object は最低限以下のフィールドを持つ:

```json
{
  "id": "T-V3-AUTH-01",
  "title": "POST /api/auth/login endpoint",
  "category": "backend|frontend|db|test|infra|cleanup",
  "label": "NEW|REFACTOR|REUSE|ARCHIVE|FIX",
  "feature_id": "F-001",
  "screen_ids": ["S-001"],
  "entity_ids": ["E-001 User", "E-038 AuthSession"],
  "legacy_task_id": "T-001-XX|null",
  "phase": 1,
  "wave": 1,
  "estimate_hours": 6,
  "estimate_sessions": 1,
  "depends_on": ["T-V3-INFRA-01"],
  "files_changed": ["backend/routers/auth.py (new)"],
  "acceptance_criteria": {
    "structural": [...],
    "functional": [...],
    "regression": [...]
  },
  "rls_policies_required": ["accounts:account_owner_select", ...],
  "spec_links": ["docs/decisions/ADR-013-auth-strategy.md"],
  "audit_md_path": "docs/audit/2026-05-15_v3/T-V3-AUTH-01.md"
}
```

## 新規 lint script

v3 で新規追加する lint check は **3 つ**:

| ID | script | 検査内容 |
|---|---|---|
| **lint #17** | `scripts/lint-mock-impl-diff.sh` | mock HTML の h1 / KPI / セクション h2 と実装 page.tsx の対応要素が一致するか |
| **lint #18** | `scripts/lint-screens-api.py` | screens.json の `related_apis` が全て backend FastAPI に存在するか + 命名規約 (`/api/<resource>/...`) |
| **lint #19** | `scripts/lint-entity-table-naming.py` | entities.json の entity 名 (PascalCase) と DB migration の CREATE TABLE 名 (snake_case で対応) が 1:1 一致するか (旧 `bf_` prefix 検出) |

これらは PR の CI で must-pass。

## audit MD format (v3)

各 task の audit MD (`docs/audit/2026-05-15_v3/T-V3-XXX-NN.md`) は **strict format** を遵守:

```markdown
# T-V3-AUTH-01 audit

## Tier 1: Structural
- [ ] mock h1 == impl h1: <diff result>
- [ ] mock KPI labels == impl: <diff result>

## Tier 2: Functional (AC verbatim)
- [ ] AC-1: <EARS text> → impl line: backend/routers/auth.py:42-58
- [ ] AC-2: <EARS text> → impl line: backend/services/auth_service.py:21-39

## Tier 3: Regression
- [ ] pytest result: 8/8 PASS
- [ ] coverage: 84% (>= 70%)
- [ ] pyright: 0 errors
- [ ] lint-mock: 19/19 OK

## Decision: ✅ DONE / 🟡 BLOCKED / 🔴 GAP
```

generic 文言 (`shall implement T-XXX as specified by feature F-XXX` 等) は **不可**。検出する `validate-audit-md.py` を併設する。

## v1 → v3 移行ルール

| v1 状態 | v3 での扱い |
|---|---|
| pre-flight audit 済 (30 件) | v3 task の `legacy_task_id` に v1 id を保持、新 3-tier AC で再検証のみ |
| post-hoc auto audit (116 件のうち健全) | REFACTOR task として 3-tier AC に書き直し |
| audit MD 不在 (36 件) | NEW task としてゼロから書き直し (v1 ID は legacy 参照のみ) |
| 確定 gap (T-008-04 / T-013-04b / T-007-03b / T-BTSTRAP-04) | v3 で新規 task として再起票 |
