# ADR-013: Entity table_name alignment — impl is the single source of truth

- **Date**: 2026-05-16
- **Status**: Accepted
- **Author**: T-V3-D-01 (Wave 4 / Group D Drift fix)
- **Supersedes**: なし
- **Related**: ADR-001 (modular monolith), ADR-009 (project-bootstrap enforcement), `docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md` §3

---

## 背景

v1 機能分解 (`docs/functional-breakdown/2026-05-09_v1/entities.json`) は 43 entity を「設計時の理想的な table 名」で記述していた。Bootstrap 段階で `backend/` と `supabase/migrations/` を import したところ、3 entity の table 名が impl と乖離 (drift) していることが判明:

| entity_id | spec (v1) | impl (supabase/migrations) | drift kind |
|---|---|---|---|
| E-008 Skill | `skills` | `skill_definitions` | rename drift |
| E-021 ArtifactVersion | `artifact_versions` | `artifact_events` | rename + 概念差 (version → event log) |
| E-012 Phase | `phases` | `bf_phases` | `bf_` prefix drift |

v3 entity-drift-summary.md §3 (High drift, 9 件) の rename 系 3 件として把握。Wave 4 Group D-1 で本 ADR + migration + test を batch 化する。

`bf_` prefix については `skills/task-decomposition/references/profiles/build-factory.md` の profile が「bf_ prefix を将来的に廃する」と宣言しているが、Phase 1 末尾時点で `bf_projects` / `bf_features` / `bf_tasks` / `bf_phases` 等が広く参照されており、ここで一括 strip するのは regression コストが非常に高い (cascade FK / RLS policy / 8000+ backend test の URL を一斉に書き換える必要)。

---

## 決定

### Decision 1: impl table name を canonical (single source of truth) とする

3 entity の正式 `table_name` を impl 側に合わせる:

- `E-008 Skill.table_name = "skill_definitions"`
- `E-021 ArtifactVersion.table_name = "artifact_events"`
- `E-012 Phase.table_name = "bf_phases"`

これらは既に v3 entities.json で `table_name` field として記録済み。本 ADR が確定するのは「impl が真であり spec は impl に合わせる」という方向性。

### Decision 2: spec_table_name field を canonical 名に揃える (本 task で実施)

v3 entities.json は drift 検出のため `table_name` (canonical/impl) と `spec_table_name` (v1 由来) を併記してきた。本 task で `spec_table_name` も canonical 名に揃える:

```diff
- "spec_table_name": "skills"
+ "spec_table_name": "skill_definitions"
- "spec_table_name": "artifact_versions"
+ "spec_table_name": "artifact_events"
- "spec_table_name": "phases"
+ "spec_table_name": "bf_phases"
```

この変更により `lint-mock.sh` 系の `rule_id=entity-table-naming` (現状未実装、`scripts/generate-drift-tickets.py` が想定するもの) が将来実装された際に該当 3 entity が drift として再検出されることを防ぐ。

### Decision 3: 歴史的な drift は `legacy_drift_notes` で保持する

`legacy_drift_notes.spec_table` は v1 由来の legacy 名 (`skills` / `artifact_versions` / `phases`) を保持し、`impl_table` は canonical 名を保持する。これにより:

- ADR 移行履歴の audit trail が消えない
- v1 から v3 への migration を読む operator が「なぜ rename が必要だったか」を追える
- 将来 `bf_` prefix を strip する判断 (separate ADR) が必要になったとき、過去の drift 記録が出発点になる

### Decision 4: idempotent rename migration を提供する

`supabase/migrations/20260516120000_entity_rename_alignment.sql` で、各 (legacy, canonical) ペアに対し:

1. legacy が存在 ∧ canonical が不在なら `ALTER TABLE legacy RENAME TO canonical` (data 保全)
2. 両方存在 → 例外 (operator が手動で merge 判断)
3. canonical のみ存在 → no-op (本 repository 上での実行はこのパス)
4. 最終 post-condition: 3 canonical table すべてが存在することを assertion

migration は DROP / TRUNCATE / DELETE を一切含まない (`test_migration_is_non_destructive`)。

### Decision 5: FK cascade rename は operator 責任

Postgres の `ALTER TABLE ... RENAME TO ...` は元 table を参照する FK constraint を自動で再リンクするが、テーブル名を文字列リテラルとして埋め込んだ trigger / function / view (RLS policy 含む) は自動 update されない。本 task の scope では 3 canonical table 自体が既に impl 上で正しい名前で構築されているため、FK cascade rename は不要。v1 → v3 path を辿る operator (= legacy 名で table を作っていた環境) は migration 適用後に individually FK rename を行う責任を持つ (AC-F4 UNWANTED で migration が失敗することを想定)。

---

## 影響

### Positive

- entities.json の `table_name` / `spec_table_name` が single value に収束 (drift 解消)
- 下流 task-decomposition / api-design / test-verification で "spec table って何?" 問題が無くなる
- `verify-rls-coverage.py` / `lint-mock.sh` の将来拡張で entity-table-naming rule を有効化しても 3 entity は green

### Negative

- v1 系の他 spec ドキュメント (architecture/2026-05-09_v1/ER 図など) は legacy 名のままの記述が残る (本 ADR の scope 外)
- v1 mockups (docs/mocks/2026-05-09_v1/) に `<meta name="entities" content="...skills,phases...">` のような legacy 名が残っている可能性 (rule_id=entity-table-naming 未実装のため検出されない)。Wave 5 以降で mock-impl-diff 拡張時に別 drift task で吸収

### Neutral

- `bf_` prefix の長期方針は別 ADR で決定する。Phase 1 末尾時点では `bf_phases` を canonical とする (この ADR で固定)

---

## 検証

本 ADR の実装は `T-V3-D-01` (audit MD: `docs/audit/2026-05-16_v3/T-V3-D-01.md`) で完了。テストは:

- `pytest backend/tests/migrations/test_entity_rename_alignment.py -v` (7 test)
- `python3 scripts/verify-rls-coverage.py` (3 canonical tables 全て RLS green)
- `python3 scripts/validate-tickets.py --check-file docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` (T-V3-D-01 entry green)
- `bash scripts/audit-md-check.sh T-V3-D-01` exit=0
- `bash scripts/lint-mock.sh` 16/16 OK (= 全 rules green; 将来の rule #19 entity-table-naming は未実装だが本 ADR で alignment 済みのため有効化時に green を維持する)

---

**最終更新: 2026-05-16** (T-V3-D-01 Wave 4 Group D-1 batch)
**責任者: T-V3-D-01 担当 session**
