# Build-Factory Profile (例として位置づけ) — integration

> このファイルは v3 integration スキルを Build-Factory プロジェクトに適用するための profile 例。他プロジェクトは独自 profile (`references/profiles/<project>.md`) を作成すること。SKILL.md / v3-core.md に書かれた汎用概念に対し、本ファイルが「具体値」を埋める。

## script path mapping

| 汎用 placeholder | Build-Factory での具体 path |
|---|---|
| `<lint_runner>` | `scripts/lint-mock.sh` |
| `<ac_validator>` | `scripts/validate-tickets.py` |
| `<access_control_verifier>` | `scripts/verify-rls-coverage.py` |
| `<audit_md_check>` | `scripts/audit-md-check.sh` |
| `<mock_impl_diff>` | `scripts/lint-mock-impl-diff.py` |
| `<mutex_checker>` | `scripts/check-wave-mutex.py` |
| `<wave_integration_reporter>` | `scripts/wave-integration-report.py` |
| `<drift_ticket_generator>` | `scripts/generate-drift-tickets.py` |
| `<phase_gate_checker>` | `scripts/check-phase-gate.py` |
| `<release_readiness_checker>` | `scripts/check-saas-readiness.py` |
| `<dogfood_completion_checker>` | `scripts/check-dogfood-completion.py` |

## phase 名 mapping

| 汎用 phase | Build-Factory phase id |
|---|---|
| Foundation phase (Wave 0) | Phase 0 |
| Backend / UI phase (per slice) | Phase 1 (dogfood) |
| Polish phase (REFACTOR + cross-cutting) | Phase 1.5 |
| Release / SaaS 公開 | Phase 2 |

## Wave / phase transition mapping

| 汎用 transition | Build-Factory transition |
|---|---|
| Foundation completion → Backend phase | Phase 0 → Phase 1 |
| Backend completion → UI phase | Phase 1 内部の slice 完了 (Group B → Group C へ進む) |
| UI completion → Polish phase | Phase 1 → Phase 1.5 |
| Polish completion → Release | Phase 1.5 → Phase 2 |

## Phase gate 判定基準 (Build-Factory 具体)

| Phase 移行 | 判定基準 (具体) | tool |
|---|---|---|
| Phase 0 → Phase 1 | 8 CI gate 全 green + lint #1-19 全 0 件 + AC validator pass | `scripts/check-phase-gate.py --phase 0` |
| Phase 1 → Phase 1.5 | dogfood 完走 (8 phase 全て Build-Factory 自身で実装可) + 187 task 全 merge 済 | `scripts/check-dogfood-completion.py` |
| Phase 1.5 → Phase 2 | lint #17-19 全 0 件 + REFACTOR タスク 全 done + drift 累積 0 件 | `scripts/check-phase-gate.py --phase 1.5` |
| Phase 2 release | multi-tenant E2E pass + billing E2E pass + SLA 99.9% × 30 日 | `scripts/check-saas-readiness.py` |

## 並列数 / CI gate 数

- N parallel sessions = **30-50** (Claude Code 並列セッション)
- N CI gates = **8** (lint-mock / AC validator / RLS coverage / audit MD / pytest cov ≥70% / pyright / tsc / mock-impl-diff)
- 連続失敗エスカ閾値 = **3 連続失敗 → human エスカ**

## rule_id mapping (lint-mock.sh 内の番号)

| 汎用 rule_id | Build-Factory lint 番号 |
|---|---|
| 絵文字検出 | lint #1 |
| AGPL ライセンス検出 | lint #2 |
| ARCHIVE 残留検出 | lint #3 |
| tickets.json メタ検証 | lint #4 |
| secrets 漏洩検出 | lint #5 |
| LangGraph 検出 (メイン経路) | lint #6 |
| LiteLLM 検出 (メイン経路) | lint #7 |
| domain-boundaries 違反 | lint #8 |
| self-provider-routing | lint #9 |
| self-tool-trim | lint #10 |
| template-skeleton 整合性 | lint #11 |
| self-constitution-inject | lint #12 |
| (lint #13-16) | プロジェクト内検証ルール |
| `mock-impl-diff` | lint #17 |
| `screens-API` (backend FastAPI router 実在性) | lint #18 |
| `entity-table-naming` | lint #19 |

## drift fix queue group naming (Build-Factory 流)

| 汎用 group | Build-Factory group |
|---|---|
| Foundation deliverable | Group A |
| Backend / UI Vertical Slice | Group B |
| Integration test | Group C |
| Drift fix queue | **Group D** (20% を Wave 内に確保) |

drift task 自動生成時は次 Wave (W<N+1>) の **Group D 20% 割当** に追加する。

## meta タグ schema

- `bf_meta` = `<meta name="screen-id|feature-id|task-ids|entities|phase">`

## technology stack 例示

- access control: Supabase RLS (PostgreSQL row-level security)
- vector DB: pgvector
- AI stack: 3-layer (claude-agent-sdk / anthropic-python / LiteLLM サブ)
- hosting: Vercel + Oracle Cloud + Supabase
- CI: GitHub Actions

## 数値例 (Build-Factory での実値)

- screens: 43
- tasks: 187
- backend tests: 8000 (Phase 9 完走時点)
- audit MD: 146+ 件

## 固有名詞

- project name: Build-Factory
- company: ENGINE BASE
- responsible person: 高本まさと

## 出力 path 規約

| 出力ファイル | Build-Factory での保存先 |
|---|---|
| wave-integration-report.md | `docs/wave-integration/W<N>.md` |
| phase-gate-decision.json | `docs/integration/<date>_v3/phase-gate-decision.json` |
| drift-tickets-W<N>.json | `docs/task-decomposition/<date>_v3/drift-tickets-W<N>.json` |
| 統合計画書 | `docs/integration/<date>_v3/integration-plan.md` |

## design token (例示のみ / integration では直接使わない)

- primary color: ENGINE BASE green `#1a6648` (`eb-500`)
- icon library: Lucide (絵文字禁止)
- font: Noto Sans JP + JetBrains Mono

## 上流出力 path (Build-Factory)

| 上流 | Build-Factory path |
|---|---|
| distributed-dev (branch-package.json) | `.claude/branches/*.json` |
| schedule-design (wave-schedule.json) | `docs/schedule-design/<date>_v<N>/wave-schedule.json` |
| test-verification (gate-config.yml) | `docs/test-verification/<date>_v<N>/gate-config.yml` |
| GitHub PR pattern | `claude/t-*` |
