# T-FOUNDATION-06 audit (完成版)

> Source: `docs/task-decomposition/2026-05-16_v3_phase0/tickets.json` (entry "T-FOUNDATION-06")
> 着手前に template を完成版に編集。3-tier AC を逐語コピー + impl line を記録。

## Tier 1: Structural

`acceptance_criteria.structural` は `[]` (none)。本 task は infra script の追加であり、mock / spec / design-system との構造的整合性検証は対象外。

## Tier 2: Functional

| # | AC (EARS) | 実装箇所 (impl line) |
|---|---|---|
| 1 | UBIQUITOUS: The system shall accept --phase from {foundation, backend, ui, polish, release} and refuse other values with exit code 2 and 'unknown phase: <value>' | `scripts/check-phase-gate.py:43 VALID_PHASES`, `:401-407 main()` の `args.phase` validate + `unknown phase: <value>` stderr + return 2 |
| 2 | EVENT-DRIVEN: When a criterion's tool_command exits 0, the system shall record {name, status: 'green', evidence: <command output snippet up to 200 chars>} | `scripts/check-phase-gate.py:186-256 evaluate_criterion()` の `proc.returncode == 0` 分岐 + `combined[:200]` 切詰 (:207) |
| 3 | EVENT-DRIVEN: When all criteria for the phase are green, the system shall set decision: 'OPEN_GATE' and exit 0 | `scripts/check-phase-gate.py:260-275 build_decision()` の `failing == []` 分岐 + `run_phase_check()` で `BLOCKED` 以外 return 0 (:307-322) |
| 4 | UNWANTED: If any criterion fails (non-zero exit or evidence file missing), the system shall set decision: 'BLOCKED', populate block_release_until with failing criteria list, and exit 1 | `scripts/check-phase-gate.py:269-275 build_decision()` の `failing != []` 分岐 + `block_release_until` 集計 + `run_phase_check()` の BLOCKED 時 return 1 (:319-322) |
| 5 | EVENT-DRIVEN: When the profile lacks criteria for the requested phase, the system shall set decision: 'PENDING' and exit 0 | `scripts/check-phase-gate.py:265-268 build_decision()` の `not results` 分岐 + `parse_profile()` で section 不在時 空 list (:83-109) |
| 6 | STATE-DRIVEN: While --self-test is active, the system shall verify 2 fixtures (all-pass → OPEN_GATE / one-fail → BLOCKED) behave as expected | `scripts/check-phase-gate.py:326-360 run_self_test()` + fixtures `scripts/tests/fixtures/phase-gate/profile-all-pass.md` / `profile-one-fail.md` |

## Tier 3: Regression

| # | 検証項目 | 実行結果 |
|---|---|---|
| 1 | `python3 scripts/check-phase-gate.py --self-test` PASS | PASS (2026-05-16 実行: all-pass=OPEN_GATE exit=0 / one-fail=BLOCKED exit=1 両方 expected と一致) |
| 2 | `pyright --strict` 0 errors | PASS (`pyright -p /tmp/pyright-config` typeCheckingMode=strict / pythonVersion=3.13 で `0 errors, 0 warnings, 0 informations`) |
| 3 | `ruff check scripts/check-phase-gate.py` 0 warnings | PASS (`All checks passed!`) |
| 4 | `bash scripts/pre-commit-check.sh` PASS | PASS for new content (本 task の追加分は emoji 0 / AGPL 0 / ARCHIVE 残留 0 / secrets 0 / tickets メタ 0 件追加違反)。`lint-emoji 44 > baseline 0` 失敗は parent commit `ff527ea` から継承する既存 backlog (Slack/Chatwork integration や mock HTML 等) であり本 task の責務範囲外。 |
| 5 | `python3 scripts/validate-tickets.py` PASS | PASS (`OK: all tickets pass validation. 187/187 compliant`) |
| 6 | `audit_md_path` (本 file) に Tier 1-3 逐語 | PASS (本 MD に Tier 1=none / Tier 2 6 件逐語 / Tier 3 6 件逐語を impl line / 実行結果付きで記載) |

## 着手記録
- 着手日: 2026-05-16
- 担当 session: claude-code (Opus 4.7 / 1M)
- branch: claude/T-FOUNDATION-06

## 完了記録
- 完了日: 2026-05-16
- Decision: DONE
- PR: (push 後に追記)

## 成果物
- `scripts/check-phase-gate.py` (new, 408 行)
- `scripts/templates/phase-gate-decision.json.jinja2` (new, 14 行)
- `scripts/tests/fixtures/phase-gate/profile-all-pass.md` (new)
- `scripts/tests/fixtures/phase-gate/profile-one-fail.md` (new)
- `skills/task-decomposition/references/profiles/build-factory.md` (+ `## Phase gate criteria: foundation` section: lint-mock / validate-tickets / audit-md-check の 3 criterion)

## ノート

- `subprocess.run(..., shell=True, timeout=60)` を採用。`shell=True` は profile が internal (committed) である前提で安全。外部 profile を渡す運用に変更する場合は再検討 (script 冒頭 docstring に明記)。
- profile parser は (a) Markdown table と (b) `- name: tool=cmd evidence=path` list の両方を受理する柔軟 parser。
- jinja2 を強制依存にしないため、JSON 生成は標準 `json` モジュールで完結。`scripts/templates/phase-gate-decision.json.jinja2` は仕様 reference として残置 (将来 jinja2 で render する場合に使用)。
- BF profile に foundation phase criteria の表を追記したことで `python3 scripts/check-phase-gate.py --phase foundation` が実プロジェクトでも稼働可能になった (lint-mock / validate-tickets / audit-md-check の 3 件)。
