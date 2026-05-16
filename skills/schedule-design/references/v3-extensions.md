# v3 拡張 — schedule-design

> 2026-05-15 v3 から、schedule-design は **Phase 0/1/1.5/2 + Sprint = Wave 単位** + **30-50 並列 Claude Code セッション** + **8 CI gate auto-merge** 前提で再設計。

## なぜ v3 拡張が必要か

v1 / v2 では:
- 「外部実装者 N 名」(人数前提) のリソース計画で、30-50 並列セッションのスケジュールに合わない
- Phase 0 (Foundation: lint / AC validator / CI gate) を「準備期間」扱いし、Phase 1 と並列で進めて drift が増殖
- クライアント確認待ちが各フェーズ末に組まれているが、Build-Factory は内製 dogfood → 確認は Phase ゲート時のみ
- ガント表が「週次 × 担当」で粒度が荒く、Wave 単位 (2-4h) で実行する並列セッションに対応できない

v3 では:
- **Phase 0 (Foundation) を Wave 0 で必ず単独実行** → CI gate 整備済まで他 task を起動しない
- **Sprint = Wave = ガント横軸** (1 Wave = 30-50 並列 × 2-4h)
- **完了判定 = 8 CI gate auto-merge** (lint / AC validator / RLS / audit MD / pytest cov ≥70% / pyright / tsc / mock-impl-diff)
- **wave-schedule.json** で Wave 単位の実行プランを出力 → claude-runner / Swarm が読む

## 入力 (上流出力 pull)

### task-decomposition 出力
- `tickets.json` — 全 task の 3-tier AC + dependencies + status
- `DEPENDENCIES.md` — DAG (Mermaid + 隣接リスト)
- `tasks-overview.md` — Foundation 群 + Vertical Slice の分類

### feature-decomposition 出力
- `DAG.md` — Sprint 0/1/2/3 (Slice 0-7) の依存関係
- `phase-mapping.md` — Phase 0/1/1.5/2 マッピング

### architecture-design 出力
- `phase_0_gates.json` — 8 CI gate の定義
- `selected-stack.json` — 採用技術 (work-package size に影響)

## Phase × Wave × Sprint マッピング

### Build-Factory 標準モデル

```
Phase 0 (Foundation 整備 / Wave 0)
  ├─ T-FND-01〜10 (lint / AC validator / CI gate / templates)
  └─ 完了判定: 8 gate 全 pass + drift 0 件
       ↓
Phase 1 (dogfood / Wave 1-5)
  ├─ Wave 1 = Slice 0 (auth + workspace + base schema)
  ├─ Wave 2 = Slice 1 (project + hearing)
  ├─ Wave 3 = Slice 2 (requirement + screen-spec)
  ├─ Wave 4 = Slice 3-4 (architecture + functional-breakdown)
  ├─ Wave 5 = Slice 5-7 (task + DAG + impl orchestrator)
  └─ 完了判定: 内製 dogfood で全 8 phase 完走
       ↓
Phase 1.5 (REFACTOR / Wave 6)
  ├─ drift 修正 + REFACTOR タスク
  └─ 完了判定: lint #17-19 すべて 0 件
       ↓
Phase 2 (SaaS 公開 / Wave 7+)
  ├─ multi-tenant / billing / oncall / 監視
  └─ 完了判定: 外部 5 社 dogfood + SLA 99.9%
```

### Wave の粒度

| 指標 | 値 |
|---|---|
| 並列度 | 30-50 セッション (Claude Code 単独 task 完結) |
| 1 Wave 実行時間 | 2-4 時間 (task 1 件 / Wave 1 周期) |
| 1 Wave のタスク数 | 30-50 件 (並列 Vertical Slice + Group D drift fix) |
| 完了判定 | 全 task が 8 CI gate auto-merge 済 |
| Wave 切替 | 前 Wave の Foundation 依存 task が全 done でゲート開放 |

## v3 必須出力フィールド

### wave-schedule.json (v3 新規)

```json
{
  "version": "v3",
  "skill": "schedule-design",
  "phases": [
    {
      "phase_id": "P0",
      "name": "Foundation 整備",
      "wave_ids": ["W0"],
      "start_date": "2026-05-16",
      "end_date": "2026-05-23",
      "duration_days": 7,
      "completion_gate": "8 CI gate 全 pass + drift 0 件",
      "phase_review_required": true
    },
    {
      "phase_id": "P1",
      "name": "dogfood (内製で 8 phase 完走)",
      "wave_ids": ["W1", "W2", "W3", "W4", "W5"],
      "start_date": "2026-05-24",
      "end_date": "2026-08-31",
      "duration_days": 100,
      "completion_gate": "Build-Factory 自身を Build-Factory で開発完走",
      "phase_review_required": true
    }
  ],
  "waves": [
    {
      "wave_id": "W0",
      "phase_id": "P0",
      "name": "Foundation: lint / AC validator / CI gate",
      "start_date": "2026-05-16",
      "end_date": "2026-05-19",
      "parallel_session_count_target": 10,
      "tasks": ["T-FND-01", "T-FND-02", "T-FND-03", "T-FND-04", "T-FND-05"],
      "depends_on_waves": [],
      "completion_criteria": [
        "all 8 CI gates pass",
        "lint #1-19 all 0 violations",
        "AC validator validates 3-tier schema",
        "audit MD template generates from tickets.json"
      ]
    },
    {
      "wave_id": "W1",
      "phase_id": "P1",
      "name": "Slice 0: auth + workspace + base schema",
      "start_date": "2026-05-24",
      "end_date": "2026-05-28",
      "parallel_session_count_target": 30,
      "tasks": ["T-001-01", "T-001-02", "T-S0-08", "T-S0-09", "T-019-01", "..."],
      "depends_on_waves": ["W0"],
      "completion_criteria": [
        "auth flow E2E pass (login/logout/signup/MFA)",
        "workspace dashboard renders KPI",
        "all RLS policies tested via verify-rls-coverage"
      ]
    }
  ],
  "milestones": [
    {
      "milestone_id": "M0",
      "name": "Phase 0 完了 / Foundation gate 開放",
      "date": "2026-05-23",
      "depends_on": ["W0"],
      "type": "phase_gate"
    }
  ],
  "ci_gate_auto_merge": {
    "enabled": true,
    "gates": [
      "lint-mock (19 checks)",
      "AC validator (3-tier schema + EARS form)",
      "RLS coverage (verify-rls-coverage)",
      "audit MD existence",
      "pytest cov >= 70%",
      "pyright strict",
      "tsc strict",
      "mock-impl-diff (lint #17)"
    ],
    "consecutive_failure_threshold": 3,
    "human_escalation_after": 3
  }
}
```

## CI gate auto-merge 経路

各 task の完了判定 = 8 CI gate 全 pass で **PR を Claude Code が自動 merge**:

```
Claude Code session (1 task)
  ↓ commit + push
GitHub PR
  ↓ CI run (8 gate parallel)
  ├─ gate #1: lint-mock.sh (19 check)
  ├─ gate #2: AC validator (validate-tickets.py)
  ├─ gate #3: RLS coverage (verify-rls-coverage)
  ├─ gate #4: audit MD existence check
  ├─ gate #5: pytest cov >= 70%
  ├─ gate #6: pyright strict
  ├─ gate #7: tsc strict
  └─ gate #8: lint #17 mock-impl-diff
  ↓ 全 pass
mcp__github__merge_pull_request (auto)
  ↓ Wave 進行表更新
```

連続 3 失敗 → human エスカ (Slack / メール通知)。

## drift 修正 task の組み込み

各 Phase 1 Wave で **Group D (drift fix)** タスクを 5-10 件並列実行:

| Group | 役割 | Wave 内割合 |
|---|---|---|
| Group A (Foundation) | gate / validator / template | Phase 0 でのみ |
| Group B (Vertical Slice impl) | screen + API + service + repo | Phase 1 で 70% |
| Group C (Integration test) | E2E + contract | Phase 1 で 10% |
| Group D (Drift fix) | lint #17-19 違反修正 | Phase 1 で 20% |

## v3 リスク追加

| リスク ID | リスク | 発生確率 | 対応策 |
|---|---|---|---|
| R-V3-01 | CI gate 連続失敗 (1 task / 3+ 回 reject) | 中 | 3 回で human エスカ + audit MD で原因記録 |
| R-V3-02 | 並列セッション競合 (同一 file への並列 edit) | 中 | task 分解時に file-level mutex (work-package boundary) |
| R-V3-03 | drift 増殖 (Group D 滞留) | 高 | Phase 1 Wave で常時 20% を drift fix に割当 |
| R-V3-04 | Phase 0 ゲート未達のまま Phase 1 開始 | 高 | Wave 0 完了判定を mechanical gate にし、Wave 1 起動を機械的に block |

## connections (連携先)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **task-decomposition** | tickets.json (3-tier AC) / DEPENDENCIES.md (DAG) |
| **feature-decomposition** | DAG.md / phase-mapping.md (Sprint 0/1/2/3) |
| **architecture-design** | phase_0_gates.json (8 CI gate) |

| 下流 | このスキルが供給する情報 |
|---|---|
| **distributed-dev** | wave-schedule.json → 各 task の起動順序を決定 |
| **claude-runner / Swarm** | wave-schedule.json + ci_gate_auto_merge 設定 |
| **delivery** | milestones + Phase gate 完了基準 |

## 互換性

- v1 (旧 schedule.md): freeze
- v3 (新出力): wave-schedule.json + Phase 0/1/1.5/2 + 30-50 並列 + CI gate auto-merge を必須化
