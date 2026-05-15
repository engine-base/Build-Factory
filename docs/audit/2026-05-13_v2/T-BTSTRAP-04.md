# Pre-flight AC Audit — T-BTSTRAP-04 (build-factory project migrate)

- **Task**: T-BTSTRAP-04 (既存案件への遡及適用 / build-factory project migrate)
- **Sprint**: S4 / **Feature**: F-003 (bootstrap) / **Layer**: CLI
- **Slice**: S4 / **Wave**: 4.3
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-BTSTRAP-04`
- **Deps**: T-BTSTRAP-02 (WorkspaceService.bootstrap ✅)
- **Status**: ✅ VERIFIED (13 spec tests PASS / 5 AC × 1:1 mapping)

---

## 経緯

Phase 9 完走 honest review (`docs/REVIEW_REPORT_2026-05-14.md`) で **genuine gap (実装も test も不在)** と特定された 1 件。Phase 10 着手の最優先項目として実装。

---

## Spec literal expansion

### Ticket text (逐語)

> "既存案件への遡及適用 (build-factory project migrate)"

### AC (5 件 EARS canonical)

1. **UBIQUITOUS** — `build-factory project migrate --workspace={id}` shall fetch the workspace's repo, diff with the latest template, and **add only missing files**.
2. **EVENT-DRIVEN** — When an existing file would be overwritten, the system shall **skip it and report a manual-merge needed**.
3. **STATE-DRIVEN** — While dry-run mode is on (`--dry-run`), the system shall print the diff but shall **not commit or push**.
4. **OPTIONAL** — Where `--all` is specified, the system shall iterate through every workspace and **migrate sequentially**.
5. **UNWANTED** — If the workspace repo is dirty (uncommitted changes), the system shall **abort the migration** and shall not force any change.

---

## 実装

### `backend/cli/project_commands.py` (新規)

公開 API:
- `MigrateError` (Exception subclass)
- `@dataclass MigratePlan` (workspace_id, missing_files, existing_files_skipped, dirty_files)
- `get_template_version(changelog)` → "v1.2"
- `list_template_files(template_dir)` → all files under templates/project-bootstrap/
- `template_relative_target(template_file, template_dir)` → workspace 配下の相対パス (.j2 除去)
- `check_repo_dirty(workspace_repo)` → list of uncommitted file paths
- `compute_migrate_plan(workspace_id, workspace_repo)` → MigratePlan (副作用なし)
- `apply_migrate_plan(plan, dry_run=False)` → result dict
- `cmd_migrate(args)` → exit code (CLI entry)
- `build_parser()` → argparse parser
- `main(argv)` → CLI main

### `backend/tests/test_t_btstrap_04_project_migrate.py` (新規)

13 test 関数 / AC 1:1 mapping:

| AC | test | status |
|---|---|---|
| 1.1 CLI script 存在 | `test_ac1_cli_script_exists` | ✅ |
| 1.2 compute_migrate_plan で missing 検出 | `test_ac1_compute_migrate_plan_returns_missing_files` | ✅ |
| 1.3 apply で missing-only 追加 | `test_ac1_apply_adds_missing_files_only` | ✅ |
| 2.1 既存 file skipped in plan | `test_ac2_existing_file_skipped_in_plan` | ✅ |
| 2.2 apply 結果に skipped 件数 | `test_ac2_apply_reports_skipped_count` | ✅ |
| 3.1 dry-run で file 不変 | `test_ac3_dry_run_does_not_create_files` | ✅ |
| 3.2 CLI --dry-run stdout 確認 | `test_ac3_dry_run_cli_returns_diff_only` | ✅ |
| 4.1 --all parser 登録 | `test_ac4_cli_supports_all_flag` | ✅ |
| 4.2 --all + env で iterate | `test_ac4_all_uses_active_workspaces_env` | ✅ |
| 4.3 --all 空でも exit 0 | `test_ac4_all_empty_returns_zero_no_error` | ✅ |
| 5.1 check_repo_dirty 検出 | `test_ac5_check_repo_dirty_detects_uncommitted` | ✅ |
| 5.2 apply で dirty abort | `test_ac5_apply_aborts_when_dirty` | ✅ |
| 5.3 CLI dirty で exit !=0 | `test_ac5_cli_aborts_with_nonzero_exit_when_dirty` | ✅ |

---

## 補足: T-BTSTRAP-05 (CI workflow) との関係

- **T-BTSTRAP-05** (.github/workflows/template-propagation.yml + scripts/propagate-template.py) = 「テンプレ更新で全 workspace に PR 自動作成」
- **T-BTSTRAP-04** (本 task / backend/cli/project_commands.py) = 「個別 workspace の migrate ロジック (CLI)」

→ T-BTSTRAP-05 は **将来** T-BTSTRAP-04 の CLI を internally invoke する形に refactor 可能 (現状は separate ですが、両方 spec を満たす)。

---

## 完了判定 (ADR-011 単一ゲート)

- [x] CLI script `backend/cli/project_commands.py` 実装 (357 行)
- [x] AC 5 件すべてに 1:1 test 対応 (13 test 関数)
- [x] `pytest test_t_btstrap_04_project_migrate.py` = **13 PASS**
- [x] `bash scripts/lint-mock.sh` = 16/16 OK
- [x] dry-run / --all / dirty-abort の 3 主要動作を CLI 通しで確認

---

_手動執筆 audit MD (pre-flight format, retroactive 化なし)_
