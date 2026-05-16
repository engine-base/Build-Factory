# v3 拡張 — integration

> 2026-05-15 v3 から、integration は **Wave 単位の集計 + Phase gate 開放判定 + drift fix Group D 流し込み** を主軸に再設計。30-50 並列 Claude Code × 8 CI gate auto-merge 前提。

## なぜ v3 拡張が必要か

v1 / v2 では:
- 10 本程度のブランチを手動順序付けでマージする想定 → 30-50 並列 Wave に対応できない
- conflict は「発生したら解決する」前提 → file mutex で事前防止する仕組みがない
- Phase ゲート判定が「リリース判断」レベルで止まり、Phase 0 → 1 / Phase 1 → 1.5 の機械的判定基準がない
- drift 検出時の対応 (どこに流すか) が定義されていない
- rollback がブランチ単位の reset → 30-50 並列に対応できない

v3 では:
- **Wave 完了時の集計** が integration の主タスク (個別マージは auto-merge 済)
- **work-package boundary (file mutex)** で conflict を事前防止 → 発生は仕様違反として原因記録
- **Phase gate 判定** は mechanical / observable な条件で機械判定
- **drift は Group D Wave に流す** (修正タスクを generate-tickets で自動生成)
- **rollback は PR revert** (task 単位) + Group D 再起動

## 入力 (上流出力 pull)

| 上流 | pull する内容 |
|---|---|
| distributed-dev | 管理 JSON 群 (各 task の branch-package.json) — 全 N 件の status |
| schedule-design | wave-schedule.json — phases / waves / milestones / critical_path |
| test-verification | gate-config.yml + ears-test-mapping.json |
| GitHub | PR list + auto-merge 状態 + CI status |

## 主軸 1: Wave 完了集計

### Wave 完了レポート (wave-integration-report.md) スキーマ

```markdown
# Wave Integration Report: W<N>

## 概要
- wave_id: W<N>
- phase_id: P<X>
- 期間: YYYY-MM-DD 〜 YYYY-MM-DD
- 並列セッション数: 30
- task 件数: 30
- Group 内訳: A=0 / B=21 / C=3 / D=6

## auto-merge 集計
| 状態 | 件数 |
|------|-----|
| ✅ auto-merged (8 gate green) | 27 |
| ⚠️ retried (1 〜 2 失敗で recovery) | 2 |
| 🔴 escalated (連続 3 失敗 → human) | 1 |
| 🟡 rolled back (post-merge 問題) | 0 |

## 連続失敗の原因分析
- T-005-03: gate #3 RLS coverage で 3 連続失敗 → boundary 設計に entities.json の rls_policies 漏れがあった
  - 対応: pre-flight audit MD に追記、distributed-dev で再起動

## drift 検出 (Group D 行き)
| lint | 件数 | 修正 task |
|------|------|----------|
| #17 mock-impl-diff | 3 | T-DRIFT-W1-01〜03 |
| #18 screens-API | 1 | T-DRIFT-W1-04 |
| #19 entity-table-naming | 0 | - |

→ 次 Wave (W2) の Group D に追加。

## 統合先 git state
- main ahead: 27 commit
- main HEAD: <sha>
- backend pytest cov: 78%
- frontend tsc: 0 error
- 全 8 gate: green
```

### 集計の自動化

`scripts/wave-integration-report.py`:

```bash
python3 scripts/wave-integration-report.py \
  --wave-id W1 \
  --branch-packages .claude/branches/*.json \
  --gh-prs "claude/t-*" \
  --output docs/wave-integration/W1.md
```

## 主軸 2: Phase gate 開放判定

### Phase gate 判定基準 (mechanical / observable)

| Phase 移行 | 判定基準 | tool |
|---|---|---|
| Phase 0 → Phase 1 | 8 CI gate 全 green + lint #1-19 全 0 件 + AC validator pass | `scripts/check-phase-gate.py --phase 0` |
| Phase 1 → Phase 1.5 | dogfood 完走 (8 phase 全て Build-Factory 自身で実装可) + 187 task 全 merge 済 | `scripts/check-dogfood-completion.py` |
| Phase 1.5 → Phase 2 | lint #17-19 全 0 件 + REFACTOR タスク 全 done + drift 累積 0 件 | `scripts/check-phase-gate.py --phase 1.5` |
| Phase 2 release | multi-tenant E2E pass + billing E2E pass + SLA 99.9% × 30 日 | `scripts/check-saas-readiness.py` |

### phase-gate-decision.json スキーマ

```json
{
  "version": "v3",
  "skill": "integration",
  "decisions": [
    {
      "phase_transition": "P0 → P1",
      "evaluated_at": "2026-05-23T18:00:00Z",
      "criteria": [
        {"name": "8 CI gate", "status": "green", "evidence": "all gates passed for last 10 commits"},
        {"name": "lint #1-19", "status": "0 violations", "evidence": "lint-mock.sh exit 0"},
        {"name": "AC validator", "status": "pass", "evidence": "validate-tickets.py exit 0"}
      ],
      "decision": "OPEN_GATE",
      "block_release_until": null,
      "next_wave": "W1",
      "approver": "automated (mechanical gate)"
    },
    {
      "phase_transition": "P1 → P1.5",
      "evaluated_at": null,
      "criteria": [],
      "decision": "PENDING",
      "block_release_until": "187 tasks 全 merge",
      "next_wave": "W6",
      "approver": null
    }
  ]
}
```

## 主軸 3: drift fix → Group D 流し込み

### drift 検出フロー

```
W<N> 完了集計 (wave-integration-report.py)
  ↓ lint #17-19 違反検出
drift 修正 task を自動生成 (T-DRIFT-W<N>-<seq>)
  ↓ tickets.json に追加
W<N+1> の Group D 候補リストに追加
  ↓ schedule-design.wave-schedule.json 更新
W<N+1> 起動時に Group D 20% を割当
```

### drift task の自動生成

`scripts/generate-drift-tickets.py`:

```bash
python3 scripts/generate-drift-tickets.py \
  --report docs/wave-integration/W1.md \
  --output docs/task-decomposition/<date>_v3/drift-tickets-W1.json \
  --target-wave W2
```

各 drift task は 3-tier AC を持つ通常 task と同じ schema。`task_id: T-DRIFT-W<N>-<seq>` で識別。

## 主軸 4: conflict 発生時の原因追跡

v3 では work-package boundary (file mutex) で conflict が事前防止される前提。発生時は仕様違反として原因記録:

### conflict 発生時のフロー

```
PR merge 時に conflict 検出
  ↓
1. check-wave-mutex.py の漏れ調査
   - 同 Wave 内に同一 file への editable task が複数 ない か
   - shared_no_concurrent_edit の宣言漏れ ない か
2. boundary 設計修正 (tickets.json の work_package_boundary 更新)
3. 該当 task を revert
4. drift task として Group D Wave に再投入
5. wave-integration-report.md に原因記録
```

## 主軸 5: rollback (v3 / task 単位)

### task 単位 rollback

```bash
# 1. 該当 PR を revert
gh pr create --base main --head revert/T-005-03 \
  --title "revert: T-005-03 (post-merge issue: <reason>)" \
  --body "Reverts #<PR>. See docs/wave-integration/W1.md#L42"

# 2. revert PR を auto-merge
gh pr merge revert/T-005-03 --auto --squash

# 3. drift task を Group D Wave に追加
python3 scripts/generate-drift-tickets.py --task T-005-03-redo --target-wave W2
```

ブランチ単位の `git reset --hard` は **使用禁止** (30-50 並列で他 task に影響)。

## connections (連携先)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **distributed-dev** | branch-package.json (各 task の管理 JSON) |
| **schedule-design** | wave-schedule.json (Phase × Wave 構成) |
| **test-verification** | gate-config.yml (8 gate 定義) |
| **GitHub** | PR list + CI status + auto-merge 状態 |

| 下流 | このスキルが供給する情報 |
|---|---|
| **schedule-design** (drift fix back-feed) | drift-tickets-W<N>.json → 次 Wave の Group D に追加 |
| **delivery** | phase-gate-decision.json (Phase 2 release ゲート) |
| **task-decomposition** | drift task 自動生成依頼 |

## 互換性

- v1: freeze
- v3 (新運用): Wave 集計 + Phase gate 機械判定 + drift fix → Group D + conflict 仕様違反扱い

## 旧 v1 fall-back (Phase 2 SaaS 外部納品時)

外部納品プロジェクトで 1 receipt 案件 = 5-10 ブランチ程度の場合は v1 流のブランチ単位整理を併用。判定: `team_size < 30 && parallel_wave_count == 0` なら v1 path、それ以外は v3 path。
