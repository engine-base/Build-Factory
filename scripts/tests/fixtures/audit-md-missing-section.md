# T-FIXTURE-MISSING audit (fixture for audit-md-check.sh --self-test)

> このファイルは Tier 1 セクションが欠落している invalid サンプル。
> audit-md-check.sh は exit code 2 を返し、欠損 section を stderr に列挙する。

## Tier 2: Functional

- [x] AC-F1: EVENT-DRIVEN When invoked, the system shall do something correctly → impl: somewhere

## Tier 3: Regression

- [x] AC-R1: tests pass → 実行ログ

## 着手記録
- 着手日: 2026-05-16
- 担当 session: fixture

## 完了記録
- 完了日: 2026-05-16
- Decision: BLOCKED

## ノート
Tier 1: Structural セクションが意図的に欠落している fixture。
