# Wave Integration Report: W0a

## 概要
- wave_id: W0a
- phase_id: Foundation
- 期間: 2026-05-16 〜 2026-05-16
- 並列セッション数: 3
- task 件数: 3
- カテゴリ内訳: Foundation=3 / Backend=0 / UI=0 / Polish=0 / Drift fix=0

## auto-merge 集計 (4 カテゴリ × deliverable category)
| 状態 | Foundation | Backend | UI | Polish | Drift fix | 合計 |
|------|-----------|---------|----|----|--------|-----|
| auto-merged (N gate green) | 2 | 0 | 0 | 0 | 0 | 2 |
| retried (1 〜 2 失敗で recovery) | 1 | 0 | 0 | 0 | 0 | 1 |
| escalated (連続 N 失敗 → human) | 0 | 0 | 0 | 0 | 0 | 0 |
| rolled back (post-merge 問題) | 0 | 0 | 0 | 0 | 0 | 0 |

## 連続失敗の原因分析
- 連続失敗 (failure_count >= 3) の task は無し

## drift 検出 (drift fix queue 行き)
- drift 検出無し (drift = 0)

## 統合先 git state
- main ahead: 3 commit
- main HEAD: 08d7df3
- backend test cov: 92%
- frontend type check: 0 error
- 全 N gate (project-defined): green
