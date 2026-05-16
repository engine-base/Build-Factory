# Build-Factory Profile (例として位置づけ)

> このファイルは schedule-design v3 を Build-Factory プロジェクトに適用するための profile 例。**他プロジェクトは独自 profile を作成する**。汎用概念は `references/v3-core.md` を参照。

## phase 名 (project-defined naming)

Build-Factory では Foundation / Backend / UI / Polish phase の汎用順序を以下の固有名で実装：

| 汎用 phase 名 | Build-Factory phase 名 | 備考 |
|---|---|---|
| Foundation phase | Phase 0 | lint / AC validator / CI gate / templates |
| Backend phase    | Phase 1 (dogfood) 前半 | Build-Factory 自身を Build-Factory で開発 |
| UI phase         | Phase 1 (dogfood) 後半 | screen + component impl |
| Polish phase     | Phase 1.5 (REFACTOR) + Phase 2 (SaaS 公開) | drift 修正 → multi-tenant / billing / oncall |

## 並列度

| 指標 | 値 |
|---|---|
| Claude Code セッション並列数 (large 規模) | 30-50 |
| 1 Wave 周期 | 2-4 時間 |
| 1 Wave のタスク数 | 30-50 件 |

## CI gate (project-defined gate set)

8 gate 構成：
1. `lint-mock` (19 check)
2. `AC validator` (validate-tickets.py)
3. `RLS coverage` (verify-rls-coverage)
4. `audit MD` existence check
5. `pytest cov >= 70%`
6. `pyright strict`
7. `tsc strict`
8. `mock-impl-diff` (lint #17)

連続失敗閾値: **3 回** で human エスカ。

## script path

| 用途 | path |
|---|---|
| lint_runner | `scripts/lint-mock.sh` |
| ac_validator | `scripts/validate-tickets.py` |
| access_control_verifier | `scripts/verify-rls-coverage.py` |
| audit_md_check | `scripts/audit-md-check.sh` |
| mock_impl_diff | `scripts/lint-mock-impl-diff.py` |

## lint rule 番号 mapping (project-defined rule_id)

| rule_id (汎用) | Build-Factory lint 番号 |
|---|---|
| mock-impl-diff | lint #17 |
| screens-API | lint #18 |
| entity-table-naming | lint #19 |

(他 lint #1-16 は emoji / AGPL / ARCHIVE / tickets / secrets / langgraph / litellm-in-runner / domain-boundaries / self-provider-routing / self-tool-trim / template-skeleton / self-constitution-inject 等)

## Vertical Slice 構成 (8 Slice)

Build-Factory 標準 Slice (Phase 1 = dogfood)：

| Slice | 内容 |
|---|---|
| Slice 0 | auth + workspace + base schema |
| Slice 1 | project + hearing |
| Slice 2 | requirement + screen-spec |
| Slice 3 | architecture |
| Slice 4 | functional-breakdown |
| Slice 5 | task |
| Slice 6 | DAG / feature-decomposition |
| Slice 7 | impl orchestrator + claude-runner |

## Wave 構成 (Build-Factory 標準モデル)

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

## meta タグ schema

- `bf_meta` = `<meta name="screen-id|feature-id|task-ids|entities|phase">`

## technology stack

| 項目 | 採用 |
|---|---|
| access control | Supabase RLS |
| vector DB | pgvector |
| AI stack | 3-layer (claude-agent-sdk / anthropic-python / LiteLLM) |
| hosting | Vercel + Oracle Cloud + Supabase |

## 数値例

| 項目 | 値 |
|---|---|
| screens | 43 |
| tasks | 187 (v1) / 113 (v2) |
| backend tests | 8000 |

## 固有名詞

| 項目 | 値 |
|---|---|
| project name | Build-Factory |
| company | ENGINE BASE |
| responsible person | 高本まさと |
| context | 内製 dogfood (Phase 1) → 外部 SaaS 公開 (Phase 2) |

## design token

| 項目 | 値 |
|---|---|
| primary color | ENGINE BASE green `#1a6648` (eb-500) |
| icon library | Lucide (絵文字禁止) |
| font | Noto Sans JP + JetBrains Mono |

## クリティカルパス (Build-Factory v1)

```
T-019-01 → T-S0-13 → T-001-01 → T-001-02 → T-001-04 → T-001-06
 → T-S0-08 → T-S0-09 → T-021-03 → T-020-02 → T-003-02 → T-M28-01
```

## wave-schedule.json (Build-Factory 適用例 schema 抜粋)

```json
{
  "version": "v3",
  "skill": "schedule-design",
  "project_profile": "build-factory",
  "phases": [
    {
      "phase_id": "P0",
      "name": "Foundation 整備",
      "wave_ids": ["W0"],
      "completion_gate": "8 CI gate 全 pass + drift 0 件",
      "phase_review_required": true
    },
    {
      "phase_id": "P1",
      "name": "dogfood (内製で 8 phase 完走)",
      "wave_ids": ["W1", "W2", "W3", "W4", "W5"],
      "completion_gate": "Build-Factory 自身を Build-Factory で開発完走"
    }
  ],
  "ci_gate_auto_merge": {
    "enabled": true,
    "gates": [
      "lint-mock (19 checks)",
      "AC validator (validate-tickets.py)",
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

## 参照 ADR

- ADR-009: Build-Factory が回す各案件にも強制レイヤーを自動展開する仕組み
- ADR-010: AI スタック 3 層 (Anthropic 純正中心 + LiteLLM サブ)
- ADR-011: 完了判定ゲート (`pre-commit-check.sh` を完了報告の単一ゲートに)
- ADR-012: Anthropic 公式 Memory 機能採用
