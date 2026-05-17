# ADR-018: AuditLog 二重実装統合 (audit_logs + auth_audit_log → audit_logs + source 列)

- **Status**: Accepted
- **Date**: 2026-05-17
- **Deciders**: 高本まさと (proxy: claude session T-V3-D-14)
- **Trigger**: v3 functional-breakdown entity-drift-summary.md §4 medium-drift と
  E-037 AuditLog の `legacy_drift_notes` で「audit_logs (汎用) と auth_audit_log
  (auth 専用) の二重実装。spec の 1 table 想定と差異」と判定された。
  **T-V3-D-14 (Wave 4 / Group D / 3h boxed)** で監査 trail を単一 table 単一
  意味論にまとめる。
- **Related**:
  - `docs/functional-breakdown/2026-05-16_v3/entity-drift-summary.md#4-medium-drift-11-件`
  - `docs/functional-breakdown/2026-05-16_v3/entities.json#E-037` / `#E-055`
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json#T-V3-D-14`
  - `supabase/migrations/20260516210000_audit_log_unification.sql` (本 ADR 実装)
  - `docs/decisions/ADR-015-legacy-twin-table-archive.md` (drift 解消 ADR の前例)
  - `docs/decisions/ADR-016-api-method-alignment.md` (drift 解消 ADR の前例)

## Context

Build-Factory には 2 つの監査ログ table が並存していた:

| Table | 由来 migration | Purpose | Tenant | Field shape |
|---|---|---|---|---|
| `audit_logs` (E-037) | `20260510000001_bf_project_tables.sql` | workspace 横断の汎用 audit (task / constitution 等) | workspace_scoped (workspace_id BIGINT) | id BIGSERIAL / action TEXT / payload JSONB / actor_user_id TEXT |
| `auth_audit_log` (E-055) | `20260510000000_auth_tables.sql` | auth 専用 (login / 2FA / OAuth) | user_scoped (user_id UUID) | id UUID / event_type TEXT / metadata JSONB / ip_address INET |

v3 spec (entities.json E-037) は「監査 trail は 1 entity (AuditLog)」と
想定しているため、impl 側の 2 table 並存は「medium drift」と分類された。
T-V3-D-14 の 3h boxed scope で次のいずれかを選択する必要があった:

1. **2 table のまま spec を修正して E-055 AuthAuditLog を正式 entity 化する**
   (現状の追認)
2. **audit_logs に統合し source 列で分類する** (spec に impl を寄せる)
3. **2 table を共通 super-table + 2 sub-table の継承構造に再構成する** (overkill)

issue text と access_policies_required の制約 (T-V3-D-14 ticket は
`audit_logs:audit_logs_service_role_all` + `audit_logs:audit_logs_account_member_select`
の 2 policy を gate にしている) より **(2) を採用** する。理由:

- 監査運用上 1 テーブルに集約すると **横断検索 / partition / retention** が
  単純になる (`pg_partman` Phase 2 で月次パーティション 1 系統で済む)。
- auth event は全 system 中の audit subset。source 列でフィルタすれば
  「直近 24h で login 失敗が多い workspace」のような cross-cut クエリが
  単一 table で書ける。
- 既存 read service (`backend/services/audit_logs.py` T-V3-B-24) を
  そのまま流用でき、新規 read endpoint を作る必要がない。
- backward compatibility は VIEW で確保できる (PostgreSQL の rule-based
  view は SELECT に対して透過)。

## Decision

### 1. **`audit_logs.source` 列を追加し enum で分類する**

- 列: `source TEXT NOT NULL DEFAULT 'generic'`
- CHECK 制約: `source IN ('generic', 'auth', 'workspace', 'system', 'cost', 'red_line')`
- INDEX: `(source, created_at DESC)` — source 別時系列検索を加速
- 既存 row は `DEFAULT 'generic'` で自動分類される。

source 値の意味:

| source | 用途 |
|---|---|
| `generic` | デフォルト (未分類 / 旧 audit_logs 由来) |
| `auth` | login / 2FA / OAuth event (旧 auth_audit_log 由来) |
| `workspace` | workspace member 追加削除 / setting 変更 |
| `system` | background job / migration / cron / system bootstrap |
| `cost` | cost tracking / billing event (T-AI-05 連携) |
| `red_line` | red_line violation event (T-V3-RED-LINE 連携) |

### 2. **`auth_audit_log` を backward-compat VIEW に置換する**

- 既存 table を `_archived_auth_audit_log` に RENAME (history 保全 + 万一の
  rollback パス確保)。
- 同名で `auth_audit_log` を VIEW として再定義 (`SECURITY BARRIER`):

  ```sql
  CREATE OR REPLACE VIEW auth_audit_log AS
  SELECT
      COALESCE(payload->>'legacy_auth_audit_log_id', synth_uuid)::uuid AS id,
      actor_user_id::uuid                                              AS user_id,
      action                                                           AS event_type,
      success                                                          AS success,
      (payload->>'ip_address')::inet                                   AS ip_address,
      payload->>'user_agent'                                           AS user_agent,
      payload - 'legacy_auth_audit_log_id'
              - 'ip_address'
              - 'user_agent'                                           AS metadata,
      created_at                                                       AS created_at
  FROM audit_logs
  WHERE source = 'auth';
  ```

- 旧 SELECT クエリは透過。INSERT/UPDATE は VIEW 経由不可 (RLS bypass 防止)。
  新規 write は `backend/services/audit_service.py::emit_auth_event` で
  `audit_logs(source='auth')` に直接書く。
- VIEW は 1 release cycle (Phase 1 完了まで) 維持。Phase 2 で 410 Gone
  deprecate → 物理削除する (follow-up task)。

### 3. **canonical RLS policies を追加 (workspace member scope)**

ticket `access_policies_required` の宣言に従い:

- `audit_logs_service_role_all`         : `FOR ALL TO service_role USING (true)`
- `audit_logs_account_member_select`    : `FOR SELECT TO authenticated USING (workspace_id IS NOT NULL AND bf_can_access_workspace(workspace_id))`

既存 policy (`audit_service_role` / `audit_member_read`) は backward-compat
で温存 (cumulative OR 結合)。Phase 2 で deprecate。

`source='auth'` row の `workspace_id` は NULL (auth event は workspace に
属さない) のため、`authenticated` user は service_role 経由でないと auth
event を SELECT できない。これは旧 `auth_audit_log.audit_self_read`
(本人のみ SELECT 可) より厳しいが、auth 専用 SOC 業務は service_role 側で
専用 API を介すべき (audit は不正アクセス検知の source であり、生 row を
非 admin に開放すべきでない)。

### 4. **Python 側で type-safe writer を提供する**

- `backend/app/models/audit_log.py` : `AuditLogSource` enum + `AuditLogRow` dataclass
- `backend/services/audit_service.py` : `emit_audit_event(...)` / `emit_auth_event(...)`
  - `emit_audit_event` は汎用 emitter。`source` を enum で受け、CHECK 制約と
    Python 側型を二重 enforce する。
  - `emit_auth_event` は backward-compat wrapper。旧 `auth_audit_log` INSERT
    と同じ引数 shape を受け、内部で `source=AuditLogSource.AUTH` に固定する。
- 既存 read service `backend/services/audit_logs.py` (T-V3-B-24) は **無変更**
  で動く (`source` 列はクエリに現れず、SELECT * 経由でも下流影響なし)。

### 5. **migration は idempotent**

- `ADD COLUMN IF NOT EXISTS source` / `DROP CONSTRAINT IF EXISTS ... ADD CONSTRAINT`
- データ移行は `INSERT INTO ... SELECT ... WHERE NOT EXISTS` (dedupe key =
  `payload->>'legacy_auth_audit_log_id'`)
- VIEW 置換は `DO $$` block で `pg_class.relkind` を見て table のときのみ
  RENAME → 既に view なら NOTICE で skip
- `CREATE OR REPLACE VIEW` で view 再生成も安全

二度実行されても data migrate は 0 row、view 再生成、policy 再 CREATE で
副作用なし。

## Consequences

### 受容するリスク

- 旧 `auth_audit_log` table を物理 DROP しないので、`_archived_auth_audit_log`
  が一時的に残る (disk 使用量微増)。Phase 2 deprecate task で DROP する。
- VIEW 経由の SELECT は audit_logs の RLS を継承する (security_barrier=true)。
  旧 `auth_audit_log.audit_self_read` (本人のみ SELECT 可) との差異は §3 で
  説明済 (workspace member 同等 + auth row は service_role のみ可視)。
- `source` enum の追加 (e.g. 'integration') は migration を 1 つ書く必要が
  ある。enum 拡張は CHECK 制約の DROP/RE-ADD で対応可。

### 機械的検証

- `backend/tests/integration/test_audit_log_unification.py` で migration の
  static SQL invariant を検証 (CHECK 制約存在 / VIEW 存在 / canonical policy
  存在 / data-migrate SQL の idempotent 構造)。
- `python3 scripts/verify-rls-coverage.py` で audit_logs に最低 2 policy が
  declared されていることを保証 (AC-R3)。
- `bash scripts/lint-mock.sh` 17/17 OK を維持 (entity-table-naming drift は
  E-037 / E-055 共に `table_name == spec_table_name` を保証)。
- `python3 scripts/validate-tickets.py --check-file
  docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json`
  で T-V3-D-14 entry の schema 整合を保証。

### entities.json 更新

- E-037 AuditLog: `legacy_drift_notes.diff_severity` を
  `resolved_by_adr_018` に更新。`legacy_drift_notes.adr_ref = 'ADR-018'`。
  `fields[]` に `source` を追加 (enum 6 値)。
- E-055 AuthAuditLog: `status` を `archived_as_view` に変更。
  `legacy_drift_notes.diff_severity` を `resolved_by_adr_018` に。
  `legacy_drift_notes.adr_ref = 'ADR-018'`。`table_name` は変えない (view
  名として継続)。`access_control_policies` の comment に「VIEW 化により
  RLS は audit_logs 側で継承」を追記。

### 後続タスク (queue 起票)

- T-V3-D-14-FOLLOWUP-1: VIEW `auth_audit_log` を 410 Gone deprecate (Phase 2)
- T-V3-D-14-FOLLOWUP-2: `_archived_auth_audit_log` 物理 DROP (Phase 2 / 1 release cycle 後)
- T-V3-D-14-FOLLOWUP-3: 既存 policy `audit_service_role` / `audit_member_read` を
  canonical 名へ統一し旧名を DROP (Phase 2 / RLS naming consistency)

## References

- ADR-015: `docs/decisions/ADR-015-legacy-twin-table-archive.md` (RENAME with
  `_archived_` prefix pattern)
- ADR-014: `docs/decisions/ADR-014-bf-prefix-decision.md` (drift 解消 ADR
  の前例 / canonical naming)
- PostgreSQL doc: [security_barrier views](https://www.postgresql.org/docs/current/rules-privileges.html)
- PostgreSQL doc: [CHECK constraints](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-CHECK-CONSTRAINTS)
