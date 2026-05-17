# ADR-014: bf_ prefix entities (Task / TaskDependency / AcceptanceCriterion / Constitution) の最終命名決定

- **Status**: Accepted
- **Date**: 2026-05-17
- **Deciders**: 高本まさと (proxy: claude session T-V3-D-02)
- **Trigger**: v3 functional-breakdown entity-drift-summary.md (2026-05-16) で E-014/15/16/17 が `spec_table_name` (prefix なし) と `impl_table` (`bf_` prefix) で drift していると判定された。`lint-mock.sh` rule #19 (entity-table-naming, 整備予定) が当該 4 entity を drift として fail させる前に、ADR で canonical naming を決定する必要がある。
- **Related**:
  - `docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md` §4 Medium drift
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` (T-V3-D-02)
  - `supabase/migrations/20260510000001_bf_project_tables.sql` (impl 元)
  - `skills/task-decomposition/references/profiles/build-factory.md` (lint #19 entity-table-naming)
  - `docs/decisions/ADR-009-project-bootstrap-enforcement.md` (テンプレ命名)

## Context

v1 entities.json (2026-05-09) は当該 4 entity を `tasks` / `task_dependencies` / `acceptance_criteria` / `constitutions` という prefix 無しの table 名で spec していた。一方、2026-05-10 に enact された Build-Factory bootstrap migration (`20260510000001_bf_project_tables.sql`) は **「Build-Factory が他案件 (multi-tenant) を回す側の DB であるため、Build-Factory 内部 entity を `bf_` で名前空間として分離する」** という設計判断のもと、`bf_tasks` / `bf_task_dependencies` / `bf_acceptance_criteria` / `bf_constitutions` という命名で作成された。

Phase 9 実装 (187 task / 8000 backend test pass) は **すべて impl 側 (`bf_*` prefix) を前提に書かれており**、関連する router / service / model / RLS policy / FK 制約 / migration 履歴は impl 命名で安定している:

- `backend/app/models/task.py` → `__tablename__ = "bf_tasks"`
- `backend/app/models/task_dependency.py` → `bf_task_dependencies`
- `backend/app/models/acceptance_criterion.py` → `bf_acceptance_criteria`
- `backend/app/models/constitution.py` → `bf_constitutions`
- RLS policy 名も `bf_tasks_service_role_all` 等で 8 policy が migration 内に存在
- 関連 view (`bf_constitution_revisions` 等) も同じ prefix で連続している

ここで **「spec 側を impl に合わせる」(keep bf_ prefix)** か **「impl 側を spec に合わせる」(strip bf_ prefix)** の 2 択がある。後者は migration / FK 連鎖 / RLS policy 一斉 rename が必要で、Phase 1 末尾の drift fix Wave (5h boxed) では非現実的かつ、稼働中の dogfood DB へのリスクが大きい。

また skills/task-decomposition profile (build-factory.md) に「`bf_ prefix` は profile.md で禁止」と一時期記述された経緯があるが、これは v3 設計時の **Workspace 跨ぎ tenant table への過剰一般化** であり、Build-Factory 内部 entity に対しては逆に「同居している顧客案件 table と名前衝突を避ける」という重要な役割を果たしている。

## Decision

### 1. **`bf_` prefix を Build-Factory 内部 entity の正式命名として採用する** (= keep bf_ prefix as final)

E-014 Task / E-015 TaskDependency / E-016 AcceptanceCriterion / E-017 Constitution の **canonical table 名は `bf_*`** とする。spec 側 (`entities.json`) を impl に合わせて更新する。

### 2. 適用範囲 (allow-list)

`bf_` prefix を許可する entity は **Build-Factory bootstrap migration が定義した内部 control-plane 用 table** に限定する。具体的には以下の 4 entity:

| entity_id | name | canonical table name |
|---|---|---|
| E-014 | Task | `bf_tasks` |
| E-015 | TaskDependency | `bf_task_dependencies` |
| E-016 | AcceptanceCriterion | `bf_acceptance_criteria` |
| E-017 | Constitution | `bf_constitutions` |

それ以外の entity (例: E-012 Phase → `bf_phases`) は本 ADR のスコープ外であり、別途 T-V3-D-* drift fix task で個別判断する。

### 3. spec の更新

`docs/functional-breakdown/2026-05-16_v3/entities.json` の E-014/15/16/17 で:

- `spec_table_name` を `bf_*` (impl と同一) に揃える
- `legacy_drift_notes.diff_severity` を `medium` → `resolved_by_adr_014` に変更
- `legacy_drift_notes.recommendation` を「ADR-014 で keep bf_ prefix as canonical 決定」に更新

### 4. DB / 実装の変更

**変更しない**。DB rename / FK cascade / RLS policy rename は行わない。 Phase 9 で確定した impl が canonical である。

### 5. Lint rule #19 (entity-table-naming) との連動

`scripts/lint-mock.sh` rule #19 は以下のロジックで判定する:

- 各 entity の `table_name` が `entities.json` の `spec_table_name` と一致しているかを確認する
- 一致しない場合は通常 fail
- ただし **本 ADR で allow-list 化された 4 entity (E-014/15/16/17)** は、`bf_` prefix がついていても fail させない

### 6. UNWANTED (strip bf_ prefix) を選択する場合の手順

将来 `bf_` prefix を廃止する判断に転じた場合は、本 ADR を `Superseded` 化し、別 ADR で migration plan を起こす。Polish phase (Group J) の T-V3-J-* タスクとして:

1. supabase migration で `ALTER TABLE bf_tasks RENAME TO tasks` (4 件) + FK / RLS / sequence / index 連鎖
2. backend model `__tablename__` を一斉更新
3. router URL / OpenAPI schema / TS 型再生成
4. dogfood DB への適用前に staging で full integration test を実行

これは本 Phase 1 末尾 task のスコープ外である。

## Consequences

### Positive

- 既存 impl / migration / RLS / FK / test を一切いじらず drift 解消できる (5h boxed の範囲内に収まる)
- Build-Factory が今後他案件を回す際、自身の control-plane table が `bf_` namespace で識別可能になり、案件側 table (`accounts`, `workspaces` 等) との混同が機械的に防げる
- `lint-mock.sh` rule #19 (entity-table-naming) の運用が ADR-anchored で予測可能になる
- ADR 1 本で 4 entity の drift を一括解消する (D-1 group の効率化)

### Negative

- v1 entities.json (歴史的 spec) との command-Z (元に戻す) が不可能になる (= ADR が history を上書き)
- skills/task-decomposition の build-factory.md に「bf_ prefix は drift」と書かれていた箇所と意味的に矛盾する (本 ADR で profile 側の文言は後日修正余地あり)

### Neutral

- 他案件 (Build-Factory が回す顧客プロジェクト) では `bf_` prefix を使ってはならない (= Build-Factory 専用の namespace)
- 新規 control-plane entity を追加する際は本 ADR の allow-list を拡張する (= rule #19 の allow-list と同期)

## Rejected alternatives

### A. Strip bf_ prefix (impl 側を spec に合わせる)

- DB migration / FK cascade / RLS policy / sequence / index / view (`bf_constitution_revisions`) を一斉 rename
- Phase 9 で確定した 187 task の impl コードを model 単位で `__tablename__` 変更
- backend test 8000 件 + integration test の全 re-run
- staging → production rollout 計画が必要
- 5h boxed の Phase 1 末尾 drift fix task では物理的に不可能

→ **Reject** (将来 Polish phase で再検討余地はある)

### B. Mark drift as `wontfix` (entities.json を放置)

- lint rule #19 を実装しても allow-list で除外しないと回らない
- 「drift がある」状態を spec 上 acknowledged しないと audit MD validator / CI gate で繰り返し flag される
- 後続新人 (AI session 含む) がどっちが正かを spec で確認できない

→ **Reject** (本 ADR で明示的に keep 宣言する方が文書化として強い)

## Verification

本 ADR の適用は以下で機械的に検証する:

1. `bash scripts/lint-mock.sh` で rule #19 (entity-table-naming) が E-014/15/16/17 を OK 判定 (allow-list)
2. `pytest backend/tests/integration/test_bf_prefix_alignment.py -v` で entities.json の 4 entity が `bf_*` で揃っていることを確認
3. `bash scripts/tests/test-lint-mock-rule19.sh` で rule #19 自体が正しく drift を検出することを確認
4. `bash scripts/audit-md-check.sh T-V3-D-02` で audit MD が pass
