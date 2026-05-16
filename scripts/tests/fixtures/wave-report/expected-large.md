# Wave Integration Report: W1

## 概要
- wave_id: W1
- phase_id: Backend
- 期間: 2026-05-20 〜 2026-05-21
- 並列セッション数: 10
- task 件数: 30
- カテゴリ内訳: Foundation=2 / Backend=12 / UI=10 / Polish=4 / Drift fix=2

## auto-merge 集計 (4 カテゴリ × deliverable category)
| 状態 | Foundation | Backend | UI | Polish | Drift fix | 合計 |
|------|-----------|---------|----|----|--------|-----|
| auto-merged (N gate green) | 2 | 8 | 8 | 3 | 2 | 23 |
| retried (1 〜 2 失敗で recovery) | 0 | 2 | 1 | 1 | 0 | 4 |
| escalated (連続 N 失敗 → human) | 0 | 2 | 0 | 0 | 0 | 2 |
| rolled back (post-merge 問題) | 0 | 0 | 1 | 0 | 0 | 1 |

## 連続失敗の原因分析
- T-B-08: gate gate-5-access-control で 4 連続失敗 → RLS policy gap - human review required
  - 対応: pre-flight audit MD に追記、distributed-dev で再起動
- T-U-06: gate post-merge-runtime で 3 連続失敗 → production runtime regression - reverted
  - 対応: pre-flight audit MD に追記、distributed-dev で再起動
- T-B-11: gate gate-2-pyright-strict で 5 連続失敗 → type inference failure on generic - needs human
  - 対応: pre-flight audit MD に追記、distributed-dev で再起動

## drift 検出 (drift fix queue 行き)
| rule_id | 件数 | 修正 task |
|---------|------|----------|
| ears-ac-missing-unwanted | 1 | T-DRIFT-W2-01 |
| lint-mock-1-emoji | 3 | T-DRIFT-W2-01, T-DRIFT-W2-02 |
| lint-mock-8-domain-boundaries | 1 | T-DRIFT-W2-03 |

→ 次 Wave (W2) の drift fix queue に追加。

## 統合先 git state
- main ahead: 30 commit
- main HEAD: ab12cd3
- backend test cov: 85%
- frontend type check: 0 error
- 全 N gate (project-defined): green
