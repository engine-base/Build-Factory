# Entity Drift Summary (v3, 2026-05-16)

> functional-breakdown v3 STEP 2 (entities) で v1 entities.json と Supabase migration 実装の差分検出を実施した結果。
> 出典: [`entities.json`](./entities.json) / 比較対象: `supabase/migrations/*.sql` (20 件)
> 上位ドキュメント: [`README.md`](./README.md) (未生成) / 上流: v1 [`../2026-05-09_v1/entities.json`](../2026-05-09_v1/entities.json)

---

## 1. サマリー

| 項目 | 値 |
|---|---|
| v1 entity 件数 | 43 |
| migration から新規発見した entity | 25 |
| **v3 total entity 件数** | **68** |
| migration table 数 (CREATE TABLE) | 105 |
| RLS policy 有り table 数 | 71 |
| v3 entities.json 内 access_control_policies 合計 | 176 |
| drift detection: **critical** | 3 |
| drift detection: **high** | 9 |
| drift detection: **medium** | 11 |
| drift detection: **new (migration only)** | 25 |
| drift detection: **low or none** | 20 |

### tenant_isolation 分布

| type | 件数 |
|---|---|
| workspace_scoped | 41 |
| user_scoped | 12 |
| account_scoped | 10 |
| none | 5 |

---

## 2. Critical drift (3 件) — entity あり / impl table 無し

下流 task-decomposition で **新規 migration が必要**、または spec 側で entity 削除を判断する必要がある:

| entity_id | name | spec_table | 状況 | 推奨対応 | task_id |
|---|---|---|---|---|---|
| E-009 | SkillExecution | `skill_executions` | impl 無し. legacy `execution_log` が代替か? | 新規 migration `skill_executions` 追加 (workspace_id + skill_id + ai_employee_id + cost + tokens + status + langfuse_trace_id) | T-V3-DRIFT-E-009 |
| E-022 | Screen | `screens` | impl 無し. `bf_mocks` (E-058) で実質代替されている | spec 統合: Screen entity を BFMock にマージ or screens 専用 table を新規作成して bf_mocks と二段階分離 | T-V3-DRIFT-E-022 |
| E-014 | Task (legacy `tasks` と modern `bf_tasks` の **二重実装**) | `tasks` | legacy `tasks` (BIGSERIAL / single-user) が残存. 正系統は `bf_tasks` | legacy `tasks` を ARCHIVE / `bf_tasks` を v3 正系統とする (E-014 → bf_tasks へ正式リネーム) | T-V3-DRIFT-E-014 |

> 備考: 「twin tables」現象は他に `projects/bf_projects`, `pull_requests/prs`, `repos/github_repos`, `ai_employee_config/ai_employees` でも観測されている (medium severity に分類).

---

## 3. High drift (9 件) — リネーム or 概念差

下流 task-decomposition Group D (Drift fix) に流す候補:

| entity_id | name | spec_table → impl_table | 内容 | task_id |
|---|---|---|---|---|
| E-002 | Account | `accounts` → `accounts` (一致) | spec uuid PK / soft_delete / plan enum, impl BIGSERIAL / soft_delete 無し / status TEXT (no enum) | T-V3-DRIFT-E-002 |
| E-004 | Workspace | `workspaces` → `workspaces` (一致) | spec uuid / slug / is_confidential / token_limit_amount column 想定. impl BIGSERIAL / slug 無し / is_confidential 無し / project_meta + client_visibility + design_system_ref + preferred_provider_enum | T-V3-DRIFT-E-004 |
| E-008 | Skill | `skills` → `skill_definitions` | **table_name rename drift**. entity-table-naming lint で失敗する | T-V3-DRIFT-E-008 |
| E-010 | UserKnowledgeNamespace | `user_knowledge_namespaces` → 無し | knowledge_base.scope column で代替表現. 専用 table 未実装 | T-V3-DRIFT-E-010 |
| E-012 | Phase | `phases` → `bf_phases` | bf_ prefix drift (profile.md で禁止と宣言されているが既存実装は bf_ 付き) | T-V3-DRIFT-E-012 |
| E-013 | PhaseGate | `phase_gates` → 無し | 専用 table 未実装. bf_phases.status で類似機能 | T-V3-DRIFT-E-013 |
| E-021 | ArtifactVersion | `artifact_versions` → `artifact_events` | リネーム + 概念差 (version → event log) | T-V3-DRIFT-E-021 |
| E-023 | Component | `components` → 無し | frontend repo の static 構造で管理. DB 化されていない | T-V3-DRIFT-E-023 |
| E-024 | ScreenComponent | `screen_components` → 無し | E-022/E-023 が無いため必然的に未実装 | T-V3-DRIFT-E-024 |

---

## 4. Medium drift (11 件) — bf_ prefix / enum 差異 / 二重実装

| entity_id | name | 内容 |
|---|---|---|
| E-003 | AccountMember | uuid → BIGINT + TEXT user_id, role enum → TEXT |
| E-005 | WorkspaceMember | uuid → BIGINT + TEXT user_id, role enum → TEXT |
| E-007 | AIEmployee | `ai_employee_config` (legacy) と `ai_employees` (modern) の二重実装. 正系統は ai_employees |
| E-015 | TaskDependency | `task_dependencies` → `bf_task_dependencies` (bf_ prefix drift) |
| E-016 | AcceptanceCriterion | `acceptance_criteria` → `bf_acceptance_criteria` (bf_ prefix drift) |
| E-017 | Constitution | `constitutions` → `bf_constitutions` (bf_ prefix drift + version 管理は別 table 化) |
| E-020 | Artifact | type enum (spec/mock_screen/...) の impl 実装表現 (TEXT or CHECK) 確認要 |
| E-025 | Session | spec uuid / status enum 7 値. impl BIGSERIAL / status CHECK 5 値. enum 値の縮小 |
| E-027 | PR | `prs` (modern) と `pull_requests` (legacy) の二重実装 |
| E-032 | GithubRepo | `github_repos` (modern) と `repos` (legacy) の二重実装 |
| E-037 | AuditLog | `audit_logs` (汎用) と `auth_audit_log` (auth 専用) の 2 table 並存 |

---

## 5. New (migration only, 25 件) — v1 entities.json に未掲載

migration には実装されているが v1 entities.json に entity 化されていない table 群。v3 で正式 entity 化:

| entity_id | name | table_name | source migration |
|---|---|---|---|
| E-044 | AIClone | ai_clones | 20260512200000_ai_hierarchy_clone_tables.sql |
| E-045 | AIHierarchy | ai_hierarchies | 20260512200000_ai_hierarchy_clone_tables.sql |
| E-046 | AIPersona | ai_personas | 20260512200000_ai_hierarchy_clone_tables.sql |
| E-047 | UserCloneOptin | user_clone_optin | 20260511000000_bf_user_profile_lifecycle_rls.sql |
| E-048 | UserDeletionRequest | user_deletion_requests | 20260511000000_bf_user_profile_lifecycle_rls.sql |
| E-049 | UserProfile | user_profiles | 20260511000000_bf_user_profile_lifecycle_rls.sql |
| E-050 | EncryptedSecret | encrypted_secrets | 20260511000001_encrypted_secrets.sql |
| E-051 | AuthSession | auth_sessions | 20260510000000_auth_tables.sql |
| E-052 | OAuthConnection | oauth_connections | 20260510000000_auth_tables.sql |
| E-053 | User2FASecret | user_2fa_secrets | 20260510000000_auth_tables.sql |
| E-054 | User2FARecoveryCode | user_2fa_recovery_codes | 20260510000000_auth_tables.sql |
| E-055 | AuthAuditLog | auth_audit_log | 20260510000000_auth_tables.sql |
| E-056 | BFProject | bf_projects | 20260510000001_bf_project_tables.sql |
| E-057 | BFFeature | bf_features | 20260510000001_bf_project_tables.sql |
| E-058 | BFMock | bf_mocks | 20260510000001_bf_project_tables.sql |
| E-059 | BFDelivery | bf_deliveries | 20260510000001_bf_project_tables.sql |
| E-060 | BFConstitutionRevision | bf_constitution_revisions | 20260510000001_bf_project_tables.sql |
| E-061 | SessionArtifact | session_artifacts | 20260512000000_impl_integration_ops_tables.sql |
| E-062 | DesignFrame | design_frames | 20260501230000_design_frames.sql |
| E-063 | DesignCanvasState | design_canvas_state | 20260501230000_design_frames.sql |
| E-064 | DesignMock | design_mocks | 20260502000000_design_mocks.sql |
| E-065 | ApprovalQueue | approval_queue | 20260501220000_initial_schema.sql |
| E-066 | Checkpoint | checkpoints | 20260501220000_initial_schema.sql |
| E-067 | SchemaVersion | schema_versions | 20260512000000_impl_integration_ops_tables.sql |
| E-068 | KnowledgeBase | knowledge_base | 20260501220000_initial_schema.sql |

> なお、105 migration tables のうち 約 30 件は legacy single-user 系 (`expenses`, `invoices`, `kpi_records`, `okr`, `network`, `pipeline`, `cf_forecasts`, `pl_records`, `tools_inventory`, `monthly_reviews`, `weekly_reviews`, `seo_reports`, `sns_posts`, `outreach_log`, `outsource_jobs`, `cs_feedback`, `portfolio_items`, `contracts`, `contacts`, `brand_assets`, `browser_task_queue`, `slack_processed_messages`, `task_log`, `task_questions`, `task_schedule`, `communication_log`, `conversation_log`, `conversation_slots`, `workflow_runs`, `workflow_steps`, `writes`, `knowledge_transfer_log`) は **会社運営 DB 系** で Build-Factory SaaS のスコープ外。v3 では entity 化していない (T-V3-DRIFT-SCOPE-01 で legacy 切り離し方針を別途決定).

---

## 6. 推奨対応 (下流 task-decomposition への流し込み)

| group | 件数 | 流し込み先 |
|---|---|---|
| Group D (Drift fix / リネーム) | E-008 (Skill → skill_definitions), E-012 (Phase → bf_phases), E-015, E-016, E-017, E-021 = 6 件 | task-decomposition Group D |
| Group B (Vertical Slice / 新規 migration 必要) | E-009 SkillExecution, E-013 PhaseGate, E-010 UserKnowledgeNamespace, E-023 Component, E-024 ScreenComponent = 5 件 | task-decomposition Group B-Backend |
| spec 統合 (entity merge) | E-022 Screen → BFMock | spec 修正 (v3 entities.json で entity を merge / E-022 を deprecated 化) |
| 二重実装解消 (ARCHIVE) | E-014 (tasks legacy delete), E-007 (ai_employee_config), E-027 (pull_requests), E-032 (repos) = 4 件 | task-decomposition Group D + migration ARCHIVE |
| 型/enum 統一 | E-002, E-003, E-004, E-005, E-020, E-025 = 6 件 | task-decomposition Group D (型 migration) |
| 新規 entity の RLS 整備 | E-044〜E-068 のうち RLS policy 数 < 2 のもの | task-decomposition Group D (RLS 補完) |

---

## 7. 機械検証

- `python3 scripts/gen_v3_entities.py` で生成
- すべての entity は次の required field を持つ: `id`, `name`, `table_name`, `fields`, `tenant_isolation`, `access_control_policies`, `status`
- `tenant_isolation.type ∈ {account_scoped, workspace_scoped, user_scoped, none}` を充足
- `access_control_policies[]` は最低 1 件 (`<table>_service_role_all`) を含む (impl table がある場合)
- impl table 不在の 6 entity は `legacy_drift_notes.impl_table = null` でマーク済

---

**生成日: 2026-05-16** / **担当: functional-breakdown v3 STEP 2 (entities)** / **次工程: STEP 3 features.json (v3 拡張)**
