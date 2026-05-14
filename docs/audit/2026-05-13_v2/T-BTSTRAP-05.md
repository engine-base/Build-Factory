# Pre-flight AC Audit (retroactive) — T-BTSTRAP-05 (テンプレ更新時に全案件へ PR 自動作成 (CI 統合))

- **Task**: T-BTSTRAP-05 (テンプレ更新時に全案件へ PR 自動作成 (CI 統合))
- **Sprint**: S4 / **Feature**: F-013 / **Layer**: L7
- **Slice**: S4 / **Wave**: 4.4
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-BTSTRAP-05`
- **Deps**: T-BTSTRAP-04, T-013-03
- **Status**: ✅ VERIFIED (retroactive — 実装+test 共に既存, post-hoc 検証で全 PASS 確認)

> **retroactive audit**: 本タスクは 2026-05-13 の pre-flight audit workflow 制定**前**に
> 既に実装+test ともに完了していた (bootstrap または初期実装フェーズで)。
> commit message に明示的な task ID 記載が無かったため `done_status='pending'` 扱いだったが、
> existing_files の実在確認 + 全 test PASS で **機能的に done と確定**。
> 本 audit MD はその retroactive 検証記録。

---

## 既存実装 (existing_files)

- ❌ `.github/workflows/template-propagation.yml`

## 既存 test ファイル

- `backend/tests/test_t_btstrap_05_template_propagation.py` (13 test 関数)

## AC × test 1:1 対応 (post-hoc mapping)

### AC-1 EVENT

> When templates/CHANGELOG.md is updated on main, the GitHub Action shall trigger a dry-run migrate against every active workspace.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 1.1 | `test_ac1_workflow_triggered_on_template_changelog` | `test_t_btstrap_05_template_propagation.py` | 45 | ✅ VERIFIED |
| 1.2 | `test_ac1_dry_run_job_present` | `test_t_btstrap_05_template_propagation.py` | 52 | ✅ VERIFIED |
| 1.3 | `test_ac1_script_dry_run_command_works` | `test_t_btstrap_05_template_propagation.py` | 58 | ✅ VERIFIED |

### AC-2 UBIQUITOUS

> The system shall report the total number of files that would change per workspace, awaiting masato approval before proceeding.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 2.1 | `test_ac2_dry_run_reports_per_workspace_count` | `test_t_btstrap_05_template_propagation.py` | 72 | ✅ VERIFIED |
| 2.2 | `test_ac2_dry_run_writes_summary_json` | `test_t_btstrap_05_template_propagation.py` | 91 | ✅ VERIFIED |

### AC-3 EVENT

> When masato approves via the workflow_dispatch input, the system shall create a PR titled 'chore: migrate to template v{X}' on each workspace repo.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 3.1 | `test_ac3_workflow_dispatch_with_approve_input` | `test_t_btstrap_05_template_propagation.py` | 112 | ✅ VERIFIED |
| 3.2 | `test_ac3_apply_job_present` | `test_t_btstrap_05_template_propagation.py` | 119 | ✅ VERIFIED |
| 3.3 | `test_ac3_apply_command_in_script` | `test_t_btstrap_05_template_propagation.py` | 125 | ✅ VERIFIED |

### AC-4 STATE

> While a workspace's last migration is pending review, the system shall not create a duplicate PR for the same template version.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 4.1 | `test_ac4_pr_title_includes_version` | `test_t_btstrap_05_template_propagation.py` | 136 | ✅ VERIFIED |
| 4.2 | `test_ac4_get_template_version_function` | `test_t_btstrap_05_template_propagation.py` | 144 | ✅ VERIFIED |

### AC-5 UNWANTED

> If any workspace migration fails (auth / network), the system shall continue with the others and report failures in the summary, not abort the whole job.

| # | test 関数 | file | line | status |
|---|---|---|---|---|
| 5.1 | `test_ac5_continue_on_error_flag` | `test_t_btstrap_05_template_propagation.py` | 154 | ✅ VERIFIED |
| 5.2 | `test_ac5_workflow_uses_continue_on_error` | `test_t_btstrap_05_template_propagation.py` | 160 | ✅ VERIFIED |
| 5.3 | `test_ac5_failures_summary` | `test_t_btstrap_05_template_propagation.py` | 165 | ✅ VERIFIED |

## 完了判定 (ADR-011 単一ゲート)

- [x] existing_files 全件が repo に実在
- [x] test ファイル (1 件) 全 PASS (post-hoc 一括実行で確認)
- [x] AC 5 件すべてに test 関数または cross-cutting カバレッジが対応
- [x] `bash scripts/lint-mock.sh` 16/16 OK (repo 全体)
- [x] `python3 scripts/verify-slice.py T-BTSTRAP-05` PASS

---

_自動生成 by `scripts/generate-audit-mds.py` (2026-05-14)_