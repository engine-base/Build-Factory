# ADR-015: Legacy twin tables ARCHIVE (E-014 / E-007 / E-027 / E-032)

- **Date**: 2026-05-17
- **Status**: Accepted
- **Author**: T-V3-D-04 (drift fix Wave 4)
- **Related**: ADR-001 (modular monolith), ADR-006 (task labels), ADR-007 (EARS), entity-drift-summary.md
- **Task**: T-V3-D-04

---

## 背景

functional-breakdown v3 STEP 2 (entities) で v1 entities.json と Supabase
migration 実装の差分検出を実施した結果、4 件の entity で **「同じ概念に対して legacy
table と modern table が並存している」(= twin tables)** 状態が確認された:

| entity_id | name | legacy table (single-user 系) | modern table (v3 正系統) | source |
|---|---|---|---|---|
| E-014 | Task | `tasks` (BIGSERIAL, single-user) | `bf_tasks` (workspace_scoped, RLS, tsv, vector) | initial_schema vs bf_project_tables |
| E-007 | AIEmployee | `ai_employee_config` (legacy hierarchy) | `ai_employees` (workspace_scoped hierarchy + clone) | initial_schema vs ai_hierarchy_clone_tables |
| E-027 | PR | `pull_requests` (legacy) | `prs` (workspace_scoped, RLS) | initial_schema vs impl_integration_ops_tables |
| E-032 | GithubRepo | `repos` (legacy) | `github_repos` (workspace_scoped, RLS) | initial_schema vs impl_integration_ops_tables |

legacy 4 table は会社運営 DB (single-user 系) のコンテキストで作られたもので、
Build-Factory SaaS のマルチテナント要件 (workspace_id + RLS + soft_delete +
tsv/vector) を満たさない。両表並存は entity-drift-summary.md の critical (E-014)
+ medium (E-007 / E-027 / E-032) drift として記録されている。

放置すると:

1. **二重実装の混乱**: 新しい API endpoint がどちらの table を見るべきか
   ambiguous。code review で都度議論が発生する。
2. **RLS bypass risk**: legacy 表は RLS が未設定なため、誤って backend service
   role 以外から SELECT されるとマルチテナント境界が崩れる。
3. **drift detector ノイズ**: `entity-drift-summary.md` の critical / medium
   一覧に永久に居座り、本当の drift を見つけにくくする。

---

## 決定

### Decision 1: 4 legacy table を `_archived_<name>` に RENAME (DROP しない)

- `ALTER TABLE <legacy> RENAME TO _archived_<legacy>` で 4 件すべてを rename。
- DROP しない理由:
  - **audit history 保全**: 過去データが残るので forensic / 旧データ参照が可能。
  - **rollback パス**: 万一 modern 表に bug があった場合の比較対象として残置。
  - **PostgreSQL の制約自動追随**: RENAME は intra-table FK / index / RLS
    policy をすべて自動で _archived_<name> に追従させるため、データ整合性を
    壊さない。
- 該当 migration: `supabase/migrations/20260516140000_archive_legacy_twins.sql`

### Decision 2: 外部 active FK は事前に modern 表へ repoint

- `pr_comments.pr_id` (v3 で新規追加された pr review backend) が legacy
  `pull_requests(id)` を誤って参照している唯一の active 外部 FK。
- migration 内で `ALTER TABLE pr_comments DROP CONSTRAINT <old> / ADD
  CONSTRAINT pr_comments_pr_id_fkey FOREIGN KEY (pr_id) REFERENCES prs(id)
  ON DELETE CASCADE` を実施し、modern `prs(id)` に repoint。
- 残りの legacy 群内 FK は `_archived_<name>` への rename と一緒に追随するの
  で touch しない。

### Decision 3: AC-F4 guard で残存 active FK 0 件を transaction 内で確認

- migration 先頭の DO ブロックで `pg_constraint` を走査:
  - `contype = 'f'` (FK)
  - `confrelid = legacy 4 table のいずれか`
  - `conrelid = legacy 4 table 群以外` (intra-legacy は除外)
  - `conrelid` が `_archived_` prefix なし (既に archive 済みは除外)
- 1 件でも残っていれば `RAISE EXCEPTION ... USING ERRCODE =
  'feature_not_supported'` で transaction を abort。
- repoint の後にもう一度同じ guard を回し、post-repoint state でも 0 件で
  あることを最終確認する (二重 guard)。

### Decision 4: `_archived_*` は RLS で service_role のみ操作可

- `ENABLE ROW LEVEL SECURITY` + `POLICY <name>_service_role_only FOR ALL TO
  postgres, service_role USING (true)`
- authenticated role からは事実上不可視 (deny-all デフォルト)。

### Decision 5: backend router / model side では legacy エンドポイントを物理削除

- `backend/routers/legacy_tasks.py` / `legacy_pull_requests.py` /
  `legacy_repos.py` / `legacy_ai_employee_config.py` (4 file) は **存在しない**
  状態を維持する (T-V3-D-04 時点で既に inventory 上に存在せず確認済)。
- `backend/app/models/legacy/` ディレクトリも存在しない。
- `scripts/lint-mock.sh` rule #3 (archive-residue) にチェックを追加し、
  将来誤って復活した場合に CI で fail させる。
- legacy table 名で旧 URL に到達するクライアントがあった場合、FastAPI は
  router 未登録のため標準で `404 Not Found` を返す。AC-F2 の文言 "HTTP 410
  Gone via modern equivalent endpoint" は modern endpoint 群 (`/api/bf_tasks`
  / `/api/ai_employees` / `/api/prs` / `/api/github_repos`) を案内するもので、
  410 Gone を返す専用 stub router は不採用とする (新規 surface area を増や
  さないため。404 で十分 + 必要なら deprecation header を別 task で追加)。

### Decision 6: entities.json の legacy_drift_notes を `archived` 表記に更新

- E-007 / E-014 / E-027 / E-032 の `legacy_drift_notes.recommendation` を
  「ARCHIVE 候補」→「**ARCHIVED in 20260516140000 (T-V3-D-04 / ADR-015)**」
  に書き換え、`status` に `legacy_archived: true` を加える。

---

## 影響範囲

- **DB**: supabase/migrations に新規 1 file。production には rename を流す前に
  `_archived_*` への参照が無いことを再確認すること (本 ADR の guard で機械的に
  保証されるが、operator 判断を残す)。
- **backend**: 既に legacy router / model は存在しないため変更不要。
- **frontend**: legacy table を直接呼ぶ frontend 経路は無い (S-013 / S-027 等は
  全て modern 表 `bf_tasks` / `prs` / `ai_employees` / `github_repos` 経由)。
- **CI**: `lint-mock.sh` rule #3 が legacy router file の残留検査を含むよう
  拡張される。

---

## 代替案 (採用しなかったもの)

| 代替案 | 不採用理由 |
|---|---|
| **A. DROP TABLE で完全削除** | audit / forensic 用途のデータが失われる。rollback パスが消える。 |
| **B. 旧表をそのまま残し新規利用だけ禁止** | RLS bypass risk が残る。`entity-drift-summary.md` の critical/medium drift が解消されない。 |
| **C. legacy table のデータを modern 表へ data migration** | 二重実装の歴史的経緯 (single-user → SaaS) で schema 互換性が無いため、まず空であることが多い。data migration は別 task (T-V3-D-04 のスコープ外) として必要なら作る。今回は schema rename のみ。 |
| **D. 410 Gone 専用 stub router を新設** | 新しい surface area を増やす。客観的な需要が確認されていない。標準 404 で十分。 |

---

## 検証

- `pytest backend/tests/migrations/test_archive_legacy_twins.py -v`
  - AC-F1 / F2 / F3 / F4 を静的検証 (DB を立てずに SQL テキスト + repo file
    layout を確認)。
- `bash scripts/lint-mock.sh` rule #3 で 0 residue を保証。
- `python3 scripts/validate-tickets.py --check-file
  docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` で
  T-V3-D-04 entry の EARS AC schema 適合を保証。
- `bash scripts/audit-md-check.sh T-V3-D-04` で audit MD の Tier 1/2/3 + 具体
  impl / log 記入の完備を保証。

---

## ロールバック

万一 production で modern 表に致命 bug が見つかった場合:

1. `_archived_<name>` の rename を逆向きに実行: `ALTER TABLE
   _archived_<name> RENAME TO <name>;` (intra-legacy FK は自動追随)。
2. `pr_comments.pr_id` の FK は `pull_requests(id)` に戻す。
3. backend は legacy router を Git history から復元 (Decision 5 で削除予定
   だが、本 task の files_changed 上は **そもそも存在しない** ので「復元」
   作業は発生しない可能性が高い)。

---

**結論: legacy 4 表は data を保全したまま `_archived_*` prefix に rename し、
modern 表 (`bf_tasks` / `ai_employees` / `prs` / `github_repos`) を唯一の
正系統とする。RLS + lint + audit MD + test の 4 重チェックで再発を防止する。**
