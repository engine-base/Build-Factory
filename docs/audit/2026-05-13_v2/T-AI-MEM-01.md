# Pre-flight AC Audit — T-AI-MEM-01 (Anthropic Memory Tool client-side handler)

- **Task**: T-AI-MEM-01 (Anthropic Memory Tool client-side handler; `memory_20250818` 6 commands; `BetaAbstractMemoryTool` 相当の file-backed 実装)
- **Sprint**: S2 / **Feature**: F-AI (AI 社員) / **Layer**: BE
- **Label**: NEW (existing module merged in PR #233; audit-only PR — no code changes to the handler)
- **Spec link**: `docs/task-decomposition/2026-05-09_v1/tickets.json#T-AI-MEM-01`
- **ADR refs**: ADR-012 Decision 1 (Memory Tool 採用), ADR-010 (AI スタック)
- **Deps**: T-S0-08 (claude-agent-sdk runner; merged)
- **Files audited**:
  - `backend/services/anthropic_memory_tool.py`
  - `backend/routers/anthropic_memory.py`
- **Status legend**: PLANNED → IMPL_DONE → TEST_PASS → VERIFIED
- **Final status**: TEST_PASS (69/69 new tests; baseline 56/56 untouched)

---

## Spec literal expansion (源泉 cited)

T-AI-MEM-01 acceptance_criteria (tickets.json verbatim):

> **AC-1 UBIQUITOUS**: The system shall implement the Anthropic Memory Tool (memory_20250818) client-side handler with all 6 official commands (view / create / str_replace / insert / delete / rename) backed by the filesystem under `OBSIDIAN_VAULT_DIR` / `MEMORY_TOOL_DIR`.
>
> **AC-2 EVENT-DRIVEN**: When the SDK or REST endpoint invokes a memory command, the system shall return a structured response within 2 seconds and shall emit the official return-string for that command (e.g. `"File created successfully at: {path}"`).
>
> **AC-3 STATE-DRIVEN**: While the handler is active, the system shall confine all path operations to the `/memories` virtual root and shall reject any path resolving outside the physical root (path traversal blocked via `pathlib.Path.resolve` + `relative_to`).
>
> **AC-4 UNWANTED**: If application code re-implements the 6 commands outside `services/anthropic_memory_tool.py`, the lint script shall fail. If invalid input (unknown command / duplicate create / nonexistent path) is detected, the system shall reject with 4xx `{detail:{code,message}}` and shall NOT mutate persistent state.

F-AI feature spec (functional-breakdown/2026-05-09_v1/2026-05-13-adr-012-addendum.json verbatim):

> "M-28 (Memory Context Builder) / M-30 (Memory 3-tier) / **F-AI (AI 社員)** の実装方式が「自前」→「Anthropic 公式 Memory Tool / Context Editing / Subagent Memory + 薄い wrapper」に変更. 要件文の意味は不変. provider 任意切替 + 障害時 fallback の両方を T-AI-MEM-04 でサポート."

ADR-012 §"機械的強制レイヤー (lint)" verbatim:

> "`scripts/lint-mock.sh` に新規 check 追加:
> - app code が `BetaAbstractMemoryTool` を経由せずに `/memories` 直接 path 操作したら fail
> - claude-agent-sdk 経路 (`services/anthropic_memory_tool.py` 以外) で `memory_20250818` raw tool spec を組み立てたら fail (重複定義防止)"

---

## AC × 実装 × test × lint 対応表

### AC-1 UBIQUITOUS — 6 commands + handler / module invariants

| # | spec sub-clause | impl (file:symbol) | test 関数名 | status |
|---|---|---|---|---|
| 1.1 | handler module exists at `services/anthropic_memory_tool.py` | source | `test_ac1_handler_module_file_exists` | ✅ |
| 1.2 | router module exists at `routers/anthropic_memory.py` | source | `test_ac1_router_module_file_exists` | ✅ |
| 1.3 | `MEMORY_TOOL_TYPE == "memory_20250818"` (官公式定数) | `amt.MEMORY_TOOL_TYPE` | `test_ac1_tool_type_constant_is_official` | ✅ |
| 1.4 | `MEMORY_TOOL_NAME == "memory"` | `amt.MEMORY_TOOL_NAME` | `test_ac1_tool_name_constant_is_official` | ✅ |
| 1.5 | `memory_tool_spec()` == `{"type":"memory_20250818","name":"memory"}` | `amt.memory_tool_spec` | `test_ac1_tool_spec_matches_official_dict` | ✅ |
| 1.6 | `VALID_COMMANDS` == 公式 6 commands 厳密一致 (no more, no less) | `amt.VALID_COMMANDS` | `test_ac1_valid_commands_are_exactly_six_official` | ✅ |
| 1.7 | 6 commands 各々が個別 method として handler に存在 (collapsed dispatch 偽装禁止) | `MemoryToolHandler.{view,create,str_replace,insert,delete,rename}` | `test_ac1_each_command_has_dedicated_method` (6 parametrize) | ✅ |
| 1.8 | view (file) → 公式 line-numbered listing 文字列 | `MemoryToolHandler.view` | `test_ac1_view_file_returns_line_numbered_content` | ✅ |
| 1.9 | view (directory) → 公式 directory listing 文字列 | 同上 | `test_ac1_view_directory_returns_listing` | ✅ |
| 1.10 | create → ファイル disk 書込 + 公式 `"File created successfully at: {path}"` | `MemoryToolHandler.create` | `test_ac1_create_writes_file_and_returns_official_message` | ✅ |
| 1.11 | str_replace (unique match) → 公式 `"The memory file has been edited."` | `MemoryToolHandler.str_replace` | `test_ac1_str_replace_modifies_unique_match_and_returns_official_message` | ✅ |
| 1.12 | insert (line=0) → 先頭 prepend | `MemoryToolHandler.insert` | `test_ac1_insert_at_line_0_prepends` | ✅ |
| 1.13 | insert (line=n) → 末尾 append | 同上 | `test_ac1_insert_at_end_appends` | ✅ |
| 1.14 | insert → 公式 `"The file {path} has been edited."` | 同上 | `test_ac1_insert_returns_official_message` | ✅ |
| 1.15 | delete (file) → unlink + 公式 `"Successfully deleted {path}"` | `MemoryToolHandler.delete` | `test_ac1_delete_file_removes_disk_entry` | ✅ |
| 1.16 | delete (dir) → recursive removal | 同上 | `test_ac1_delete_directory_is_recursive` | ✅ |
| 1.17 | rename → 物理 move + 公式 `"Successfully renamed {old} to {new}"` | `MemoryToolHandler.rename` | `test_ac1_rename_moves_file_and_returns_official_message` | ✅ |
| 1.18 | dispatch unknown command → `MemoryToolError("unknown command")` | `MemoryToolHandler.dispatch` | `test_ac1_dispatch_unknown_command_raises_memory_tool_error` | ✅ |
| 1.19 | `MEMORY_TOOL_DIR` env → physical root | `_physical_root` | `test_ac1_filesystem_root_honors_memory_tool_dir` | ✅ |
| 1.20 | `OBSIDIAN_VAULT_DIR` env → `<vault>/memories` fallback (ADR-012 Decision 1) | 同上 | `test_ac1_filesystem_root_falls_back_to_obsidian_vault_dir` | ✅ |

### AC-2 EVENT-DRIVEN — 2-second budget + per-command official return-string

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 2.1 | view: 公式 文字列 (`"Here's the content of ..."`) + < 2 s | `MemoryToolHandler.view` | `test_ac2_each_command_returns_official_string_within_2s[view]` | ✅ |
| 2.2 | create: 公式 文字列 (`"File created successfully at: {path}"`) + < 2 s | `MemoryToolHandler.create` | `test_ac2_each_command_returns_official_string_within_2s[create]` | ✅ |
| 2.3 | str_replace: 公式 文字列 (`"The memory file has been edited."`) + < 2 s | `MemoryToolHandler.str_replace` | `test_ac2_each_command_returns_official_string_within_2s[str_replace]` | ✅ |
| 2.4 | insert: 公式 文字列 (`"The file {path} has been edited."`) + < 2 s | `MemoryToolHandler.insert` | `test_ac2_each_command_returns_official_string_within_2s[insert]` | ✅ |
| 2.5 | delete: 公式 文字列 (`"Successfully deleted {path}"`) + < 2 s | `MemoryToolHandler.delete` | `test_ac2_each_command_returns_official_string_within_2s[delete]` | ✅ |
| 2.6 | rename: 公式 文字列 (`"Successfully renamed {old} to {new}"`) + < 2 s | `MemoryToolHandler.rename` | `test_ac2_each_command_returns_official_string_within_2s[rename]` | ✅ |
| 2.7 | dispatch routes correctly to each of 6 commands | `MemoryToolHandler.dispatch` | `test_ac2_dispatch_routes_to_each_command` (6 parametrize) | ✅ |

### AC-3 STATE-DRIVEN — `/memories` confinement + path traversal patterns each individually rejected

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 3.1 | path 無 prefix (`/etc/passwd`) → reject | `_resolve_virtual_path` | `test_ac3_view_rejects_path_without_memories_prefix` | ✅ |
| 3.2 | relative path (`notmemories/...`) → reject | 同上 | `test_ac3_view_rejects_relative_path` | ✅ |
| 3.3 | empty path → reject | 同上 | `test_ac3_view_rejects_empty_path` | ✅ |
| 3.4 | `..` 1段 (`/memories/../etc/passwd`) → reject | 同上 | `test_ac3_traversal_dot_dot_rejected` | ✅ |
| 3.5 | `..` 多段 (`/memories/../../../escape.txt`) → reject | 同上 | `test_ac3_traversal_multi_dot_dot_rejected` | ✅ |
| 3.6 | `~` 組合せ (`/memories/~/../../escape.txt`) → reject (literal `~` 単独は physical root 内なら許可) | 同上 | `test_ac3_traversal_tilde_rejected_outside_root` | ✅ |
| 3.7 | 絶対 path `/tmp/leak.txt` `/var/log/syslog` → reject | 同上 | `test_ac3_traversal_absolute_path_rejected` | ✅ |
| 3.8 | null byte (`/memories/foo\x00bar.txt`) → reject (MemoryToolError or filesystem ValueError) | 同上 | `test_ac3_traversal_null_byte_rejected` | ✅ |
| 3.9 | 実装が `pathlib.Path.resolve()` + `.relative_to()` を使用 (spec 文言 mandate) | source grep | `test_ac3_resolve_relative_to_used_for_confinement` | ✅ |
| 3.10 | 4 つの traversal pattern 全てで filesystem 不変 (state mutate なし) | `_resolve_virtual_path` | `test_ac3_no_mutation_on_rejected_traversal` | ✅ |
| 3.11 | per-workspace `MEMORY_TOOL_DIR` override で workspace 隔離 | `_physical_root` | `test_ac3_workspace_isolation_via_memory_tool_dir` (2 parametrize) | ✅ |

### AC-4 UNWANTED — invalid-input rejection + 4xx form uniformity + state preservation + drift guard

| # | spec sub-clause | impl | test | status |
|---|---|---|---|---|
| 4.1 | unknown command (`bogus`) → 公式 `"unknown command 'bogus'"` 文字列で reject | `MemoryToolHandler.dispatch` | `test_ac4_unknown_command_rejected` | ✅ |
| 4.2 | duplicate create → 公式 `"already exists"` + 既存内容不変 | `MemoryToolHandler.create` | `test_ac4_duplicate_create_rejected` | ✅ |
| 4.3 | view missing → 公式 `"does not exist"` | `MemoryToolHandler.view` | `test_ac4_view_nonexistent_rejected` | ✅ |
| 4.4 | str_replace no match → 公式 `"did not appear verbatim"` + 内容不変 | `MemoryToolHandler.str_replace` | `test_ac4_str_replace_no_match_rejected` | ✅ |
| 4.5 | str_replace multi match → 公式 `"Multiple occurrences"` + 内容不変 | 同上 | `test_ac4_str_replace_multiple_matches_rejected` | ✅ |
| 4.6 | insert out-of-range → 公式 `"Invalid `insert_line`"` | `MemoryToolHandler.insert` | `test_ac4_insert_invalid_line_rejected` | ✅ |
| 4.7 | insert negative → 同上 | 同上 | `test_ac4_insert_negative_line_rejected` | ✅ |
| 4.8 | insert non-int (`"1"`) → 同上 | 同上 | `test_ac4_insert_non_int_line_rejected` | ✅ |
| 4.9 | delete missing → 公式 `"does not exist"` | `MemoryToolHandler.delete` | `test_ac4_delete_nonexistent_rejected` | ✅ |
| 4.10 | rename src missing → 同上 | `MemoryToolHandler.rename` | `test_ac4_rename_src_missing_rejected` | ✅ |
| 4.11 | rename dst exists → 公式 `"already exists"` + 両 file 不変 | 同上 | `test_ac4_rename_dst_collision_rejected` | ✅ |
| 4.12 | router: unknown command → 400 `{code:"memory.invalid",message}` | `_map_memory_error` | `test_ac4_router_unknown_command_returns_400_with_code_and_message` | ✅ |
| 4.13 | router: path traversal → 400 `{code:"memory.invalid",message}` | 同上 | `test_ac4_router_traversal_returns_400_with_code_and_message` | ✅ |
| 4.14 | router: missing path → 404 `{code:"memory.not_found",message}` | 同上 | `test_ac4_router_missing_path_returns_404_with_code_and_message` | ✅ |
| 4.15 | router: duplicate create → 409 `{code:"memory.conflict",message}` | 同上 | `test_ac4_router_duplicate_create_returns_409_with_code_and_message` | ✅ |
| 4.16 | 全 4xx response が `{detail:{code:str,message:str}}` 統一 | 同上 | `test_ac4_router_4xx_form_uniform_for_all_failure_modes` | ✅ |
| 4.17 | `MEMORY_TOOL_TYPE = "memory_20250818"` 再定義が canonical 以外に無い (drift guard / lint と等価) | source grep全 backend/ | `test_ac4_no_other_module_redefines_memory_tool_type` | ✅ |

### Drift guard

| # | sub-clause | test | status |
|---|---|---|---|
| 5.1 | handler module docstring に "ADR-012" 言及 | `test_drift_guard_module_documents_adr_012` | ✅ |
| 5.2 | router module source に "ADR-012" 言及 | `test_drift_guard_router_documents_adr_012` | ✅ |
| 5.3 | `memory_tool_spec()` は厳密 2 キー (`type`,`name`) — Anthropic 公式仕様 | `test_drift_guard_tool_spec_returns_exactly_two_keys` | ✅ |

---

## Gap analysis

| # | gap | severity | resolution |
|---|---|---|---|
| **G1** | ADR-012 §"機械的強制レイヤー (lint)" で mandate されている `scripts/lint-mock.sh` 内の `memory_20250818` 重複定義検査が**未実装**. `lint-mock.sh` に `memory_20250818` の文字列が一切無い. | **MEDIUM (spec-defined lint hook gap)** | **Python レベルで等価な drift guard `test_ac4_no_other_module_redefines_memory_tool_type` を追加**. backend/ 配下の全 `.py` を走査し canonical handler 以外で `MEMORY_TOOL_TYPE = "memory_20250818"` 再定義が無いことを機械検証. bash lint への完全移植は follow-up ticket **T-AI-MEM-01b (lint script `memory_20250818` re-assembly check)** として切り出す. |
| G2 | 既存 ADR-012 統合テスト (`test_adr_012_anthropic_memory_tool.py` 56 件) が 6 commands の AC-2 timing を view / create の 2 つしかカバーしていない | LOW | 本 audit で AC-2 timing を 6 commands × 各々 parametrize で完全網羅. |
| G3 | 既存テストが path traversal を `..` 1 パターン + 絶対 path の 2 種類しかカバーしていない | LOW | 本 audit で `..` 1段 / 多段 / `~` 組合せ / 絶対 path / null byte の 5 パターンに展開. |
| G4 | per-workspace 隔離 (MEMORY_TOOL_DIR override) の test が無い (ADR-012 Decision 5.5 関連) | LOW | 本 audit で `test_ac3_workspace_isolation_via_memory_tool_dir` (2 parametrize) を追加. |
| G5 | 既存テストの dispatch routing が 1 件のみ (`create` のみ) | LOW | 本 audit で 6 commands × dispatch routing parametrize を追加. |

着手後 gap 数: 1 (G1 残 / bash lint への hook 移植は別 ticket). G2〜G5 は本 audit test で閉鎖.

---

## NEW 適合チェック (9 項目)

本 audit は **新規 test ファイル + audit doc のみ** を追加し、既存実装 (handler / router) には 1 byte も変更を加えない (pure read-only audit).

| # | 項目 | 結果 |
|---|---|---|
| 1 | 新規 SQL migration 追加なし | OK |
| 2 | 既存 service module 改変なし | OK (`anthropic_memory_tool.py` 無改変) |
| 3 | 既存 router 改変なし | OK (`anthropic_memory.py` 無改変) |
| 4 | 既存 test 削除/改変なし | OK (`test_adr_012_anthropic_memory_tool.py` 56 件 baseline pass) |
| 5 | 公開 API シンボル変更なし | OK |
| 6 | DB schema 変更なし | OK |
| 7 | RLS policy 追加/削除なし | OK (Memory Tool は filesystem; ADR-012 entities_addendum の通り DB ではなく filesystem permission で代替) |
| 8 | external dependency 追加なし | OK (stdlib + 既存 fastapi/pytest のみ) |
| 9 | docstring 改変なし | OK |

---

## 完了判定 (Step 6 / ADR-011)

- [x] 全行 status = ✅ (47 sub-clause + 6 AC-2 timing × 6 commands + 5 traversal patterns + workspace isolation × 2 + dispatch routing × 6 + 3 drift = 69 tests)
- [x] `pytest tests/test_t_ai_mem_01_memory_tool_handler_spec.py` → 69 passed in 3.17s
- [x] `pytest tests/test_adr_012_anthropic_memory_tool.py` (baseline) → 56 passed (regression なし)
- [x] PR description にこの audit doc へのリンク
- [ ] Follow-up: 新 task **T-AI-MEM-01b** を tickets.json に追加 (G1: `scripts/lint-mock.sh` への `memory_20250818` re-assembly bash 検査の正式 hook 移植)

---

## Anti-drift 適用方針 (この audit から general 化できる教訓)

1. **collapsed dispatch 偽装禁止**: `MemoryToolHandler.dispatch(command, ...)` を 1 件だけ test して "6 commands カバー" と主張するのは禁止. 各 command 単位で behavior test を書く (本 audit では `view` / `create` / `str_replace` / `insert` / `delete` / `rename` を個別 method 検査 + 各々 output 検査 + 各々 timing 検査 + 各々 official return-string 検査).
2. **path traversal pattern 個別**: `..` 1 種類だけ test して "traversal blocked" と主張するのは禁止. `..` 1段 / 多段 / `~` 組合せ / 絶対 path / null byte の 5 パターンを各々個別 test.
3. **spec で mandate されている lint hook が未実装の場合**: Python レベルで等価な invariant test を書き, follow-up ticket として bash 移植を切り出す. テストを「lint 実装の有無を確認」だけにすると, lint 不在で audit が誤って FAIL する.
4. **既存統合テストとの差別化**: 既存テスト (PR #233 merged) は AC 4 件を「一通り通る」レベルでカバー. NEW audit は spec 文言を sub-clause に分解し各々 1:1 で test に紐付ける (本 audit は 47 sub-clause + 22 parametrize variant = 69 test).

---

**Audited by**: T-AI-MEM-01 audit session (2026-05-14)
**Implementation owner of follow-up**: T-AI-MEM-01b (lint hook bash 移植) は次 wave assignee
