# T-FIXTURE-VALID audit (fixture for audit-md-check.sh --self-test)

> このファイルは scripts/audit-md-check.sh の self-test で使われる valid サンプル。
> 3 セクション (Tier 1 / 2 / 3) すべて存在し、generic phrase は含まない。

## Tier 1: Structural

- [x] AC-S1: mock との一致 (h1 text "Dashboard" / kpi label 5 件) → impl: frontend/src/app/dashboard/page.tsx:L12-L48

## Tier 2: Functional

- [x] AC-F1: EVENT-DRIVEN When the user clicks the "Run" button, the system shall start the workflow within 200ms → impl: backend/api/workflow.py:L34
- [x] AC-F2: UNWANTED If the user is not authenticated, the system shall return 401 → impl: backend/api/workflow.py:L18

## Tier 3: Regression

- [x] AC-R1: backend pytest PASS (124 tests, 0 fail) → 実行ログ: pytest -q
- [x] AC-R2: frontend `npm run build` PASS → 実行ログ
- [x] AC-R3: coverage >= 70% → coverage report 76.3%

## 着手記録
- 着手日: 2026-05-16
- 担当 session: fixture
- branch: claude/T-FIXTURE-VALID

## 完了記録
- 完了日: 2026-05-16
- Decision: DONE
- PR: (fixture only)

## ノート
self-test 用 fixture。実際のタスクではない。
