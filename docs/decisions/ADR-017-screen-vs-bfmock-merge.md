# ADR-017: Screen (E-022) merge into BFMock (E-058)

- **Status**: Accepted
- **Date**: 2026-05-17
- **Deciders**: 高本まさと (proxy: claude session T-V3-D-13)
- **Trigger**: v3 functional-breakdown entity-drift-summary.md (2026-05-16) で E-022 Screen が `critical drift` と判定された。 spec_table=`screens` に対し impl_table が `(missing)` で、実体は `bf_mocks` (E-058) が UI 画面 S-XXX の sole-source-of-truth として既に運用中。 **T-V3-D-13 (Wave 4 / Group D / 4h boxed)** で「Screen entity を BFMock に merge する方針」を確定する。
- **Related**:
  - `docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md` §2 critical drift / §6 推奨対応
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` (T-V3-D-13)
  - `supabase/migrations/20260510000001_bf_project_tables.sql` (bf_mocks DDL)
  - `supabase/migrations/20260516200000_components_screen_components.sql` (本 task で追加)
  - `docs/decisions/ADR-014-bf-prefix-decision.md` (bf_ prefix を canonical とする前例)
  - `docs/decisions/ADR-015-legacy-twin-table-archive.md` (entity merge 前例)

## Context

v1 entities.json は UI 画面の表現として 3 entity を別立てしていた:

| entity_id | name | spec_table | impl_table | drift |
|---|---|---|---|---|
| E-022 | Screen | `screens` | (missing) | critical (entity 自体が無い) |
| E-023 | Component | `components` | (missing) | high (design-system 管理) |
| E-024 | ScreenComponent | `screen_components` | (missing) | high (join 未実装) |

一方 impl 側は `bf_mocks` (E-058 BFMock) を 2026-05-10 から運用している。 `bf_mocks` の columns は:

```
id BIGSERIAL PRIMARY KEY,
project_id BIGINT NOT NULL REFERENCES bf_projects(id),
screen_code TEXT NOT NULL,   -- S-XXX (v1 Screen.id / route 同等)
name TEXT NOT NULL,          -- Screen.name と同一意味
mock_path TEXT,
html_content TEXT,
meta_tags JSONB,
status TEXT DEFAULT 'draft',
created_at, updated_at
```

`bf_mocks.screen_code` (S-XXX) + `bf_mocks.name` は v1 Screen entity の `name` / `route_pattern` / `spec_link` を実質的に内包しており、 別 table を作る meaningful な spec differential は存在しない。 `bf_mocks` には 4 RLS policy (service_role × 2 + workspace_member × 2) が T-V3-D-07 で canonical 化済 (`bf_mocks_workspace_member_select` 等)。

選択肢は 2 つあった:

1. **Screen を独立 table として新規作成し、 BFMock と二段階分離する**: spec の純度は保たれるが、 既存運用 (frontend / mock viewer / S-023 編集モード) が `bf_mocks` を直接参照しているため広範な refactor が発生し、 Wave 4 の 4h boxed scope を逸脱。 また 2 table 同期 (Screen ↔ BFMock 1:1) の整合性維持コストが恒久的に残る。
2. **Screen entity を BFMock に merge し、 spec 側で deprecation + pointer を残す**: 既存運用に影響なし。 spec 側は entities.json E-022 を `status="deprecated_merged_into_e058"` + `replaced_by="E-058"` で deprecate し、 後続 spec consumer (mock-impl drift verifier / OpenAPI generator / frontend type generator) が E-058 を参照すれば一意に解決する。

issue text の指示 「**spec 統合 (entity merge)** を採用」 を採用する。

## Decision

### 1. **E-022 Screen entity を E-058 BFMock に merge する** (canonical = bf_mocks)

- v3 entities.json の E-022 は **deprecated** に降格する:
  - `status = "deprecated_merged_into_e058"`
  - `replaced_by = "E-058"`
  - `table_name = "bf_mocks"` / `spec_table_name = "bf_mocks"` (lint check #17 整合)
  - `legacy_drift_notes.recommendation` を 「ADR-017 で BFMock に merge 済」 へ更新
- 新規 `screens` table は **作成しない**。 E-022 のためだけの migration は無い。
- 下流 consumer (api-design / screen-API match lint / frontend type generator) は E-058 BFMock を screen entity として参照する。

### 2. **E-023 Component / E-024 ScreenComponent は正式 entity として新 table 化する**

- `components` (E-023): workspace_scoped, BIGSERIAL PK, UNIQUE (workspace_id, name, version)
- `screen_components` (E-024): junction table, workspace_scoped (denormalized), screen_id BIGINT FK → **bf_mocks(id)** per 本 ADR.
- RLS は `<table>_service_role_all` + `<table>_workspace_member_select` の canonical pair (T-V3-D-06/07/08 と同形)。

### 3. **screen_components.screen_id は bf_mocks(id) を FK 参照する**

- v1 spec の意味 (Screen ← 1:N → ScreenComponent → N:1 → Component) は完全に保たれる。
- FK target を `bf_mocks(id)` に固定することで、 将来 `screens` table を separate 化する必要が生じた場合は ADR 改訂 + migration (`ALTER TABLE screen_components ALTER COLUMN screen_id REFERENCES screens(id)`) で対応する。

### 4. **entities.json の更新範囲** (T-V3-D-13 scope)

- E-022 Screen: status=deprecated + pointer + table 名整合 (上記 1)
- E-023 Component: `legacy_drift_notes.impl_table` を `"components"` に更新 + `policy_count_actual=2` + `source_migration="20260516200000_components_screen_components.sql"` + `status="formal"`
- E-024 ScreenComponent: `legacy_drift_notes.impl_table` を `"screen_components"` に更新 + `policy_count_actual=2` + `source_migration="20260516200000_components_screen_components.sql"` + `status="formal"`
- 他 entity (E-058 BFMock 等) は **変更しない** (本 task は merge "decision" の記録であって BFMock spec の改訂は scope 外)。

## Consequences

### 受容するリスク

- `bf_mocks.screen_code` (TEXT) と `screen_components.screen_id` (BIGINT FK) の 2 系統で screen identity が表現されてしまう。 application 層では screen_code (S-XXX) を public-facing identifier に、 screen_id (BIGINT) を internal FK に使い分ける必要がある。
- v1 spec を読んで来る新規開発者は entities.json E-022 を見て「あれ、screens table はどこ?」と一度迷う。 これは `replaced_by` pointer + ADR-017 reference で誘導する。

### 機械的検証

- `python3 scripts/verify-rls-coverage.py` で `components` / `screen_components` 2 table の RLS coverage を保証 (policy_count >= 2 each)。
- `bash scripts/lint-mock.sh` 17/17 で entity-table-naming drift (#17) が E-022 についても `table_name == spec_table_name == "bf_mocks"` で整合する (deprecated entity も lint pass)。
- `pytest backend/tests/integration/test_components_screen_components.py -v` で migration 構文 / RLS / FK / UNIQUE constraint を静的検証。
- `bash scripts/audit-md-check.sh T-V3-D-13` で audit MD の 3-tier 完整性を保証。

### 後続タスク (queue 起票候補)

- (将来) frontend が S-024 (Component Library) / S-023 (Screen Editor) で `components` / `screen_components` を活用する UI を実装する場合は、 本 ADR を参照した上で REST endpoint を追加 (Phase 1.5 候補)。
- (将来) Screen を独立 table 化する必要が生じた場合は、 本 ADR を改訂 (Status: Superseded) + `screens` table を追加する migration + `screen_components.screen_id` を新 table に REFERENCE 変更する migration を発行する。

## References

- ADR-014 (bf_ prefix decision) — 既存 impl prefix を canonical 化する前例
- ADR-015 (legacy twin table archive) — entity merge / 整理の前例
- `docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md` §2 / §6
- v3 entities.json#E-022 / E-023 / E-024 / E-058
