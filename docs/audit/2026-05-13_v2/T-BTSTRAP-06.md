# Pre-flight AC Audit — T-BTSTRAP-06 (e2e workspace bootstrap)

- **Task**: T-BTSTRAP-06 (e2e テスト = workspace 作成 → 強制レイヤー検証)
- **Sprint**: S3 / **Feature**: F-003 / **Layer**: TST
- **Slice**: S4 / **Wave**: 4.3
- **Label**: NEW
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-BTSTRAP-06`
- **Deps**: T-BTSTRAP-02 (Jinja2 placeholder service ✅)
- **Status**: ✅ VERIFIED (6 spec tests PASS)

---

## AC × test 1:1 対応

### AC-1 EVENT-DRIVEN: bootstrap 完了で必須ファイル揃う

| # | spec sub-clause | impl/path | test | status |
|---|---|---|---|---|
| 1.1 | 7 必須ファイル全部生成 | tests/e2e/test_workspace_bootstrap.py:REQUIRED_FILES | `test_ac1_required_files_present` | ✅ |
| 1.2 | CLAUDE.md.j2 → CLAUDE.md (Jinja2 適用) | bootstrapped_workspace fixture | `test_ac1_claude_md_is_rendered_not_template` | ✅ |

### AC-2 UBIQUITOUS: Build-Factory 文字列を含む

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 2.1 | grep -c 'Build-Factory' CLAUDE.md >= 1 | bootstrapped_workspace + content.count | `test_ac2_claude_md_contains_build_factory` | ✅ |

### AC-3 EVENT-DRIVEN: bash scripts/lint-mock.sh pass

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 3.1 | scripts/lint-mock.sh 配置 + bash -n syntax check | shutil.copytree + bash -n | `test_ac3_lint_mock_script_exists_and_executable` | ✅ |

### AC-4 STATE-DRIVEN: 60 秒以内

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 4.1 | bootstrap 全 process < 60s | time.time() 計測 | `test_ac4_bootstrap_under_60_seconds` | ✅ |

### AC-5 UNWANTED: 必須ファイル欠損で test fail

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 5.1 | missing detection が clear error 出す | REQUIRED_FILES iteration + assert msg | `test_ac5_missing_required_file_caught` | ✅ |

---

## 既存実装

- ✅ `templates/project-bootstrap/` (T-BTSTRAP-01 で配置済み)
- ✅ `backend/tests/e2e/test_workspace_bootstrap.py` (本 PR で新規)

## 既存 test ファイル

- `backend/tests/e2e/test_workspace_bootstrap.py` (6 test 関数, all PASS)

## 完了判定 (ADR-011 単一ゲート)

- [x] templates/project-bootstrap/ から 7 必須ファイルが揃うことを e2e で検証
- [x] AC 5 件すべてに 1:1 test (6 関数)
- [x] `pytest backend/tests/e2e/test_workspace_bootstrap.py` = 6 PASS
- [x] 60 秒制約クリア (実測: 0.05 秒程度)
- [x] `bash scripts/lint-mock.sh` 16/16 OK
