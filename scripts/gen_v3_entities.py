#!/usr/bin/env python3
"""Generate docs/functional-breakdown/2026-05-16_v3/entities.json (v3 schema).

- Pulls v1 entities (43 件) from docs/functional-breakdown/2026-05-09_v1/entities.json
- Adds v3 fields: table_name, tenant_isolation, access_control_policies[], legacy_drift_notes
- Detects drift between v1 entity spec and Supabase migration impl
- Adds new entities discovered in migrations but absent from v1

Run: python3 scripts/gen_v3_entities.py
"""
from __future__ import annotations
import json
import re
from pathlib import Path

WORKTREE = Path(__file__).resolve().parents[1]
V1_PATH = WORKTREE / "docs/functional-breakdown/2026-05-09_v1/entities.json"
MIG_DIR = WORKTREE / "supabase/migrations"
OUT_DIR = WORKTREE / "docs/functional-breakdown/2026-05-16_v3"
OUT_PATH = OUT_DIR / "entities.json"


def load_migration_tables() -> dict[str, str]:
    """Return {table_name: source_migration_filename}."""
    table_to_file: dict[str, str] = {}
    pat = re.compile(r"^CREATE TABLE IF NOT EXISTS ([a-z_0-9]+)\s*\(", re.MULTILINE)
    for sql in sorted(MIG_DIR.glob("*.sql")):
        text = sql.read_text()
        for m in pat.finditer(text):
            t = m.group(1)
            # 最初に出現した migration を出典として記録
            table_to_file.setdefault(t, sql.name)
    return table_to_file


def count_policies_per_table() -> dict[str, int]:
    """Count CREATE POLICY ... ON <table> per table across all migrations."""
    counts: dict[str, int] = {}
    pat = re.compile(r"CREATE POLICY\s+\S+\s+ON\s+([a-z_0-9]+)", re.IGNORECASE)
    for sql in sorted(MIG_DIR.glob("*.sql")):
        text = sql.read_text()
        for m in pat.finditer(text):
            t = m.group(1).lower()
            counts[t] = counts.get(t, 0) + 1
    return counts


# ────────────────────────────────────────────────────────────────────
# Mapping table: v1 entity name → actual impl table name (drift map)
# 'spec' = v1 spec が想定した table, 'impl' = migration での実テーブル
# ────────────────────────────────────────────────────────────────────
ENTITY_TABLE_MAP: dict[str, dict] = {
    # E-001 User : spec "users" / impl "users" — match (auth migration)
    "User": {
        "spec": "users", "impl": "users",
        "tenant": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts"},
        "drift": {
            "severity": "low",
            "note": "FK to accounts via account_members M:N; users.id type is UUID in impl (auth-aligned), legacy bf_ tables use TEXT user_id (auth.uid()::text). 軽微 (型ブリッジを require)",
        },
    },
    "Account": {
        "spec": "accounts", "impl": "accounts",
        "tenant": {"type": "none", "column": None, "fk_table": None},
        "drift": {
            "severity": "high",
            "note": "spec は uuid PK / soft_delete / plan enum 想定. impl は BIGSERIAL PK / soft_delete カラム無し / status TEXT (DEFAULT 'active', plan enum 無し). 大きな型ギャップ",
        },
    },
    "AccountMember": {
        "spec": "account_members", "impl": "account_members",
        "tenant": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts"},
        "drift": {
            "severity": "medium",
            "note": "spec は uuid FK / role enum. impl は BIGINT account_id + TEXT user_id (auth.uid()::text) / role TEXT (no enum). user_id polymorphism がスペックと一致せず",
        },
    },
    "Workspace": {
        "spec": "workspaces", "impl": "workspaces",
        "tenant": {"type": "workspace_scoped", "column": "id", "fk_table": "workspaces"},
        "drift": {
            "severity": "high",
            "note": "spec uuid PK / slug / is_confidential bool / token_limit_amount. impl は BIGSERIAL PK / slug カラム無し / is_confidential 無し / project_meta + client_visibility + design_system_ref / preferred_provider_enum (20260513100000 で追加). Slug は project_meta JSONB に押し込まれている疑い",
        },
    },
    "WorkspaceMember": {
        "spec": "workspace_members", "impl": "workspace_members",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "spec uuid user_id / role enum + custom_permissions jsonb + visible_tabs jsonb. impl は BIGINT + TEXT user_id / role TEXT / custom_permissions + visible_tabs columns confirmed",
        },
    },
    "WorkspaceInvitation": {
        "spec": "workspace_invitations", "impl": "workspace_invitations",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "low",
            "note": "token / expires_at / accepted_at column 揃い確認済. PK 型のみ BIGSERIAL に差し替え",
        },
    },
    "AIEmployee": {
        "spec": "ai_employees", "impl": "ai_employees",
        "tenant": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts"},
        "drift": {
            "severity": "medium",
            "note": "spec name 'AIEmployee' → 旧 ai_employee_config と新 ai_employees (20260512200000_ai_hierarchy_clone_tables.sql) の 2 系統並存. 新規 ai_employees + ai_hierarchies (E-NEW) + ai_clones (E-NEW) が正系統. 旧 ai_employee_config は ARCHIVE 候補",
        },
    },
    "Skill": {
        "spec": "skills", "impl": "skill_definitions",
        "tenant": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts"},
        "drift": {
            "severity": "high",
            "note": "spec table_name 'skills' に対し impl は 'skill_definitions'. リネーム drift",
        },
    },
    "SkillExecution": {
        "spec": "skill_executions", "impl": None,
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "critical",
            "note": "spec 'skill_executions' に対応する impl 無し. execution_log (legacy single-user table) が代替か? 確認要 → 新規 migration 必要",
        },
    },
    "UserKnowledgeNamespace": {
        "spec": "user_knowledge_namespaces", "impl": None,
        "tenant": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "drift": {
            "severity": "high",
            "note": "knowledge_base table に scope column で表現されているが、専用 user_knowledge_namespaces table は実装無し",
        },
    },
    "UserInteractionLog": {
        "spec": "user_interaction_log", "impl": "user_interaction_log",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "low",
            "note": "20260512200000_ai_hierarchy_clone_tables.sql で実装確認. opt-in trigger 仕様も spec 通り",
        },
    },
    "Phase": {
        "spec": "phases", "impl": "bf_phases",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "high",
            "note": "spec 'phases' に対し impl は 'bf_phases' (bf_ prefix). profile.md で bf_ prefix 禁止と宣言されているが既存実装は bf_ 付き. リネーム or profile 例外化のいずれか",
        },
    },
    "PhaseGate": {
        "spec": "phase_gates", "impl": None,
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "high",
            "note": "PhaseGate table は impl 無し. bf_phases に status column で類似機能あるが、phase_gates 別 table としては未実装",
        },
    },
    "Task": {
        "spec": "tasks", "impl": "bf_tasks",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "critical",
            "note": "spec 'tasks' に対し legacy 'tasks' (single-user) と modern 'bf_tasks' の **二重実装** が並存. v3 では bf_tasks が正で legacy tasks は ARCHIVE 推奨. T-V3-DRIFT-E-014 で legacy tasks 削除を計画",
        },
    },
    "TaskDependency": {
        "spec": "task_dependencies", "impl": "bf_task_dependencies",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "spec 'task_dependencies' に対し impl は 'bf_task_dependencies'. bf_ prefix drift",
        },
    },
    "AcceptanceCriterion": {
        "spec": "acceptance_criteria", "impl": "bf_acceptance_criteria",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "spec 'acceptance_criteria' に対し impl は 'bf_acceptance_criteria'. bf_ prefix drift",
        },
    },
    "Constitution": {
        "spec": "constitutions", "impl": "bf_constitutions",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "spec 'constitutions' に対し impl は 'bf_constitutions'. version 管理は bf_constitution_revisions が担当 (E-NEW)",
        },
    },
    "RedLine": {
        "spec": "red_lines", "impl": "red_lines",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "low",
            "note": "20260512000000 で table 作成 + 20260514000000 で 5 default categories seed. spec と一致",
        },
    },
    "RedLineViolation": {
        "spec": "red_line_violations", "impl": "red_line_violations",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "Artifact": {
        "spec": "artifacts", "impl": "artifacts",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "spec の type enum (spec/mock_screen/...) が impl で TEXT か CHECK で表現されているか確認要. embedding vector(1536) は実装あり",
        },
    },
    "ArtifactVersion": {
        "spec": "artifact_versions", "impl": "artifact_events",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "high",
            "note": "spec 'artifact_versions' に対し impl は 'artifact_events' (イベントログ的). リネーム + 概念差異あり (version → event log)",
        },
    },
    "Screen": {
        "spec": "screens", "impl": None,
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "critical",
            "note": "Screen table は impl 無し. bf_mocks (E-NEW) で代替されているが Screen 単独 table としては未実装. functional-breakdown spec が Screen / Mock を分離している点と齟齬",
        },
    },
    "Component": {
        "spec": "components", "impl": None,
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "high",
            "note": "Component table は impl 無し. design system → frontend component の関係は frontend repo の static 構造で管理されており DB 化されていない",
        },
    },
    "ScreenComponent": {
        "spec": "screen_components", "impl": None,
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "high",
            "note": "Screen と Component の junction table 未実装. 上記 2 entity が無いため必然的に未実装",
        },
    },
    "Session": {
        "spec": "sessions", "impl": "sessions",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "spec uuid PK / status enum 細粒度 (starting/running/paused/...). impl BIGSERIAL + status TEXT CHECK で 5 値. enum 数値が一致せず (spec 7 / impl 5)",
        },
    },
    "SessionLog": {
        "spec": "session_logs", "impl": "session_logs",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致 (retention 30d 含む)"},
    },
    "PR": {
        "spec": "prs", "impl": "prs",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "20260512000000 で prs と pull_requests (legacy single-user) の 2 表並存. 新は prs, ARCHIVE 候補は pull_requests",
        },
    },
    "PRReview": {
        "spec": "pr_reviews", "impl": "pr_reviews",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "LLMProvider": {
        "spec": "llm_providers", "impl": "llm_providers",
        "tenant": {"type": "none", "column": None, "fk_table": None},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "APIKey": {
        "spec": "api_keys", "impl": "api_keys",
        "tenant": {"type": "account_scoped", "column": "owner_id", "fk_table": "accounts"},
        "drift": {
            "severity": "low",
            "note": "polymorphic owner_type/owner_id 実装確認. encrypted_secrets table 経由で実暗号化",
        },
    },
    "SlackWebhook": {
        "spec": "slack_webhooks", "impl": "slack_webhooks",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "GithubRepo": {
        "spec": "github_repos", "impl": "github_repos",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "github_repos (modern) と repos (legacy) の 2 表並存. repos は ARCHIVE 候補",
        },
    },
    "ObsidianVault": {
        "spec": "obsidian_vaults", "impl": "obsidian_vaults",
        "tenant": {"type": "account_scoped", "column": "owner_id", "fk_table": "accounts"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "Notification": {
        "spec": "notifications", "impl": "notifications",
        "tenant": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "CostLog": {
        "spec": "cost_logs", "impl": "cost_logs",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "TokenLimit": {
        "spec": "token_limits", "impl": "token_limits",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "AuditLog": {
        "spec": "audit_logs", "impl": "audit_logs",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {
            "severity": "medium",
            "note": "audit_logs (impl) と auth_audit_log (impl) が並存. auth-specific 系は別 table. spec の 1 table 想定と差異",
        },
    },
    "Backup": {
        "spec": "backups", "impl": "backups",
        "tenant": {"type": "none", "column": None, "fk_table": None},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "UserSetting": {
        "spec": "user_settings", "impl": "user_settings",
        "tenant": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "WorkspaceSetting": {
        "spec": "workspace_settings", "impl": "workspace_settings",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "ChatThread": {
        "spec": "chat_threads", "impl": "chat_threads",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
    "ChatMessage": {
        "spec": "chat_messages", "impl": "chat_messages",
        "tenant": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "drift": {"severity": "low", "note": "spec 一致 (vector(1536) 含む)"},
    },
    "Template": {
        "spec": "templates", "impl": "templates",
        "tenant": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts"},
        "drift": {"severity": "low", "note": "spec 一致"},
    },
}


# ────────────────────────────────────────────────────────────────────
# 新規 entity (migration only / v1 entities.json に無い)
# ────────────────────────────────────────────────────────────────────
NEW_ENTITIES: list[dict] = [
    {
        "id": "E-044",
        "name": "AIClone",
        "table_name": "ai_clones",
        "source_migration": "20260512200000_ai_hierarchy_clone_tables.sql",
        "purpose": "ユーザーの personal clone 保持 (user_clone_opt_in と関連) — clone behavior / system prompt / approval history を持つ",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "user_id", "type": "text", "nullable": False, "fk": "auth.users.id"},
            {"name": "workspace_id", "type": "bigint", "nullable": True, "fk": "workspaces.id"},
            {"name": "clone_name", "type": "text", "nullable": False},
            {"name": "system_prompt", "type": "text", "nullable": False},
            {"name": "is_active", "type": "boolean", "default": "true"},
            {"name": "metadata", "type": "jsonb", "default": "'{}'::jsonb"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
            {"name": "updated_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
        "indexes": ["idx_ai_clones_user", "idx_ai_clones_workspace"],
    },
    {
        "id": "E-045",
        "name": "AIHierarchy",
        "table_name": "ai_hierarchies",
        "source_migration": "20260512200000_ai_hierarchy_clone_tables.sql",
        "purpose": "AI employee の親子関係 (csuite / lead / member) を materialize したリンクテーブル. cycle prevention trigger (20260512300000) で循環防止",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "parent_id", "type": "bigint", "nullable": True, "fk": "ai_employees.id"},
            {"name": "child_id", "type": "bigint", "nullable": False, "fk": "ai_employees.id"},
            {"name": "depth", "type": "integer", "default": "0"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "parent", "type": "belongs_to", "target": "AIEmployee", "fk_column": "parent_id"}],
        "tenant_isolation": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts", "via": "ai_employees"},
        "constraints": ["no_circular_parent (trigger from 20260512300000)"],
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-046",
        "name": "AIPersona",
        "table_name": "ai_personas",
        "source_migration": "20260512200000_ai_hierarchy_clone_tables.sql",
        "purpose": "BMAD 10 ペルソナの seed table (mary / preston / winston / sally / devon / quinn / reviewer / brand / mockup / logan). 20260512400000_bmad_personas_seed.sql で seed",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "persona_key", "type": "text", "nullable": False, "unique": True},
            {"name": "display_name", "type": "text", "nullable": False},
            {"name": "role", "type": "text", "nullable": False},
            {"name": "system_prompt", "type": "text"},
            {"name": "skill_ids", "type": "uuid[]", "default": "'{}'::uuid[]"},
            {"name": "is_active", "type": "boolean", "default": "true"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [],
        "tenant_isolation": {"type": "none", "column": None, "fk_table": None},
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-047",
        "name": "UserCloneOptin",
        "table_name": "user_clone_optin",
        "source_migration": "20260511000000_bf_user_profile_lifecycle_rls.sql",
        "purpose": "ユーザーが clone 化に opt-in した時刻と consent を別 table で audit-friendly に管理 (BF spec の user_clone_opt_in bool を独立 table に昇格)",
        "fields": [
            {"name": "user_id", "type": "text", "primary_key": True, "fk": "auth.users.id"},
            {"name": "opted_in_at", "type": "timestamptz", "default": "now()"},
            {"name": "consent_version", "type": "text"},
            {"name": "opted_out_at", "type": "timestamptz", "nullable": True},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["opted_in_at"],
    },
    {
        "id": "E-048",
        "name": "UserDeletionRequest",
        "table_name": "user_deletion_requests",
        "source_migration": "20260511000000_bf_user_profile_lifecycle_rls.sql",
        "purpose": "GDPR 削除要求 (right-to-be-forgotten) を非同期処理する queue",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "user_id", "type": "text", "nullable": False, "fk": "auth.users.id"},
            {"name": "requested_at", "type": "timestamptz", "default": "now()"},
            {"name": "scheduled_for", "type": "timestamptz", "nullable": False},
            {"name": "status", "type": "text", "default": "'pending'", "check": "status IN ('pending','processing','completed','cancelled')"},
            {"name": "completed_at", "type": "timestamptz", "nullable": True},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["requested_at", "completed_at"],
    },
    {
        "id": "E-049",
        "name": "UserProfile",
        "table_name": "user_profiles",
        "source_migration": "20260511000000_bf_user_profile_lifecycle_rls.sql",
        "purpose": "v1 User entity の補足 profile (display_name / avatar / timezone 等). users (auth) と 1:1",
        "fields": [
            {"name": "user_id", "type": "text", "primary_key": True, "fk": "auth.users.id"},
            {"name": "display_name", "type": "text"},
            {"name": "avatar_url", "type": "text"},
            {"name": "timezone", "type": "text", "default": "'UTC'"},
            {"name": "language", "type": "text", "default": "'ja'"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
            {"name": "updated_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-050",
        "name": "EncryptedSecret",
        "table_name": "encrypted_secrets",
        "source_migration": "20260511000001_encrypted_secrets.sql",
        "purpose": "pgsodium で暗号化された secret 値の汎用 vault. APIKey / SlackWebhook / GithubRepo の暗号化 column が参照",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "owner_type", "type": "text", "check": "owner_type IN ('user','workspace','account')"},
            {"name": "owner_id", "type": "text", "nullable": False},
            {"name": "key_hint", "type": "text"},
            {"name": "encrypted_value", "type": "bytea", "nullable": False},
            {"name": "nonce", "type": "bytea", "nullable": False},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
            {"name": "updated_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [],
        "tenant_isolation": {"type": "account_scoped", "column": "owner_id", "fk_table": "accounts", "via": "polymorphic owner"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-051",
        "name": "AuthSession",
        "table_name": "auth_sessions",
        "source_migration": "20260510000000_auth_tables.sql",
        "purpose": "Supabase Auth と並行運用する application-side session table (refresh_token / device / ip / 2FA 状態)",
        "fields": [
            {"name": "id", "type": "uuid", "primary_key": True, "default": "gen_random_uuid()"},
            {"name": "user_id", "type": "uuid", "nullable": False, "fk": "users.id"},
            {"name": "refresh_token_hash", "type": "text", "nullable": False, "unique": True},
            {"name": "device_info", "type": "jsonb"},
            {"name": "ip_address", "type": "inet"},
            {"name": "expires_at", "type": "timestamptz", "nullable": False},
            {"name": "revoked_at", "type": "timestamptz", "nullable": True},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-052",
        "name": "OAuthConnection",
        "table_name": "oauth_connections",
        "source_migration": "20260510000000_auth_tables.sql",
        "purpose": "OAuth 連携 (Anthropic / Slack / GitHub) の token 保管 (encrypted)",
        "fields": [
            {"name": "id", "type": "uuid", "primary_key": True, "default": "gen_random_uuid()"},
            {"name": "user_id", "type": "uuid", "nullable": False, "fk": "users.id"},
            {"name": "provider", "type": "text", "nullable": False, "check": "provider IN ('anthropic','slack','github','google','openai','gemini')"},
            {"name": "provider_user_id", "type": "text"},
            {"name": "access_token_encrypted", "type": "bytea"},
            {"name": "refresh_token_encrypted", "type": "bytea"},
            {"name": "expires_at", "type": "timestamptz"},
            {"name": "scopes", "type": "text[]"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
            {"name": "updated_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-053",
        "name": "User2FASecret",
        "table_name": "user_2fa_secrets",
        "source_migration": "20260510000000_auth_tables.sql",
        "purpose": "TOTP secret + 有効化状態を管理 (recovery codes は別 table)",
        "fields": [
            {"name": "user_id", "type": "uuid", "primary_key": True, "fk": "users.id"},
            {"name": "secret_encrypted", "type": "bytea", "nullable": False},
            {"name": "is_enabled", "type": "boolean", "default": "false"},
            {"name": "enabled_at", "type": "timestamptz"},
            {"name": "last_used_at", "type": "timestamptz"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": [],
    },
    {
        "id": "E-054",
        "name": "User2FARecoveryCode",
        "table_name": "user_2fa_recovery_codes",
        "source_migration": "20260510000000_auth_tables.sql",
        "purpose": "TOTP 紛失時の recovery code (10 個 hash 化保存 / 使い切り)",
        "fields": [
            {"name": "id", "type": "uuid", "primary_key": True, "default": "gen_random_uuid()"},
            {"name": "user_id", "type": "uuid", "nullable": False, "fk": "users.id"},
            {"name": "code_hash", "type": "text", "nullable": False, "unique": True},
            {"name": "used_at", "type": "timestamptz"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-055",
        "name": "AuthAuditLog",
        "table_name": "auth_audit_log",
        "source_migration": "20260510000000_auth_tables.sql",
        "purpose": "auth 専用の audit (login / logout / 2FA enable / password change). 汎用 audit_logs と別 table",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "user_id", "type": "uuid", "fk": "users.id"},
            {"name": "event_type", "type": "text", "nullable": False},
            {"name": "ip_address", "type": "inet"},
            {"name": "user_agent", "type": "text"},
            {"name": "success", "type": "boolean"},
            {"name": "metadata", "type": "jsonb"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "user", "type": "belongs_to", "target": "User", "fk_column": "user_id"}],
        "tenant_isolation": {"type": "user_scoped", "column": "user_id", "fk_table": "users"},
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-056",
        "name": "BFProject",
        "table_name": "bf_projects",
        "source_migration": "20260510000001_bf_project_tables.sql",
        "purpose": "Build-Factory が回す案件 (workspace 配下 1:N). hearing → delivery の phase 進行を持つ. v1 spec では Workspace = 案件と想定されていたが impl では workspace > project の 2 階層構成",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "workspace_id", "type": "bigint", "nullable": False, "fk": "workspaces.id"},
            {"name": "name", "type": "text", "nullable": False},
            {"name": "slug", "type": "text", "nullable": False},
            {"name": "client_name", "type": "text"},
            {"name": "description", "type": "text"},
            {"name": "status", "type": "text", "default": "'planning'", "check": "13 値 enum"},
            {"name": "deadline", "type": "date"},
            {"name": "started_at", "type": "timestamptz"},
            {"name": "delivered_at", "type": "timestamptz"},
            {"name": "metadata", "type": "jsonb", "default": "'{}'::jsonb"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
            {"name": "updated_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [
            {"name": "workspace", "type": "belongs_to", "target": "Workspace", "fk_column": "workspace_id"},
            {"name": "phases", "type": "has_many", "target": "Phase (bf_phases)", "fk_column": "project_id"},
            {"name": "tasks", "type": "has_many", "target": "Task (bf_tasks)", "fk_column": "project_id"},
        ],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
        "indexes": ["uq_bf_project_slug (workspace_id, slug)"],
    },
    {
        "id": "E-057",
        "name": "BFFeature",
        "table_name": "bf_features",
        "source_migration": "20260510000001_bf_project_tables.sql",
        "purpose": "F-XXX (functional-breakdown 由来の feature). v1 では Feature entity 自体が無く screens / tasks に分散していたが impl では独立 table 化",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "project_id", "type": "bigint", "nullable": False, "fk": "bf_projects.id"},
            {"name": "feature_code", "type": "text", "nullable": False},
            {"name": "name", "type": "text", "nullable": False},
            {"name": "description", "type": "text"},
            {"name": "category", "type": "text"},
            {"name": "status", "type": "text", "default": "'planned'"},
            {"name": "metadata", "type": "jsonb"},
        ],
        "relations": [{"name": "project", "type": "belongs_to", "target": "BFProject", "fk_column": "project_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces", "via": "bf_projects"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-058",
        "name": "BFMock",
        "table_name": "bf_mocks",
        "source_migration": "20260510000001_bf_project_tables.sql",
        "purpose": "UI モック S-XXX. v1 spec の Screen entity が impl では bf_mocks に統合されている",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "project_id", "type": "bigint", "nullable": False, "fk": "bf_projects.id"},
            {"name": "screen_code", "type": "text", "nullable": False},
            {"name": "name", "type": "text", "nullable": False},
            {"name": "mock_path", "type": "text"},
            {"name": "html_content", "type": "text"},
            {"name": "meta_tags", "type": "jsonb"},
            {"name": "status", "type": "text", "default": "'draft'"},
        ],
        "relations": [{"name": "project", "type": "belongs_to", "target": "BFProject", "fk_column": "project_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces", "via": "bf_projects"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-059",
        "name": "BFDelivery",
        "table_name": "bf_deliveries",
        "source_migration": "20260510000001_bf_project_tables.sql",
        "purpose": "納品レコード (artifact 一式 + checksum + 検収日). v1 spec では Artifact に type=delivery で表現していたが impl で独立 table 化",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "project_id", "type": "bigint", "nullable": False, "fk": "bf_projects.id"},
            {"name": "version", "type": "text", "nullable": False},
            {"name": "delivered_at", "type": "timestamptz"},
            {"name": "checksum", "type": "text"},
            {"name": "manifest", "type": "jsonb"},
        ],
        "relations": [{"name": "project", "type": "belongs_to", "target": "BFProject", "fk_column": "project_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces", "via": "bf_projects"},
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-060",
        "name": "BFConstitutionRevision",
        "table_name": "bf_constitution_revisions",
        "source_migration": "20260510000001_bf_project_tables.sql",
        "purpose": "Constitution の改訂履歴 (audit). v1 spec では Constitution.version で表現していたが impl で別 table 化",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "constitution_id", "type": "bigint", "nullable": False, "fk": "bf_constitutions.id"},
            {"name": "version", "type": "integer", "nullable": False},
            {"name": "content", "type": "text", "nullable": False},
            {"name": "changed_by", "type": "text"},
            {"name": "changed_at", "type": "timestamptz", "default": "now()"},
            {"name": "diff_summary", "type": "text"},
        ],
        "relations": [{"name": "constitution", "type": "belongs_to", "target": "Constitution (bf_constitutions)", "fk_column": "constitution_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces", "via": "bf_constitutions"},
        "soft_delete": False,
        "timestamps": ["changed_at"],
    },
    {
        "id": "E-061",
        "name": "SessionArtifact",
        "table_name": "session_artifacts",
        "source_migration": "20260512000000_impl_integration_ops_tables.sql",
        "purpose": "Session と Artifact の M:N junction (v1 spec で session_artifacts と記述されていたが entity 化されていなかった)",
        "fields": [
            {"name": "session_id", "type": "bigint", "nullable": False, "fk": "sessions.id"},
            {"name": "artifact_id", "type": "bigint", "nullable": False, "fk": "artifacts.id"},
            {"name": "role", "type": "text", "default": "'output'"},
            {"name": "created_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [
            {"name": "session", "type": "belongs_to", "target": "Session", "fk_column": "session_id"},
            {"name": "artifact", "type": "belongs_to", "target": "Artifact", "fk_column": "artifact_id"},
        ],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces", "via": "sessions"},
        "soft_delete": False,
        "timestamps": ["created_at"],
        "indexes": ["PRIMARY KEY (session_id, artifact_id)"],
    },
    {
        "id": "E-062",
        "name": "DesignFrame",
        "table_name": "design_frames",
        "source_migration": "20260501230000_design_frames.sql",
        "purpose": "Penpot/GrapesJS の design frame (canvas 上の矩形領域 / コンポーネント配置情報)",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "workspace_id", "type": "bigint", "nullable": False, "fk": "workspaces.id"},
            {"name": "name", "type": "text", "nullable": False},
            {"name": "x", "type": "integer"},
            {"name": "y", "type": "integer"},
            {"name": "width", "type": "integer"},
            {"name": "height", "type": "integer"},
            {"name": "content", "type": "jsonb"},
        ],
        "relations": [{"name": "workspace", "type": "belongs_to", "target": "Workspace", "fk_column": "workspace_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-063",
        "name": "DesignCanvasState",
        "table_name": "design_canvas_state",
        "source_migration": "20260501230000_design_frames.sql",
        "purpose": "Design editor の canvas 全体の状態 (zoom / pan / selected frames 等)",
        "fields": [
            {"name": "workspace_id", "type": "bigint", "primary_key": True, "fk": "workspaces.id"},
            {"name": "state", "type": "jsonb", "default": "'{}'::jsonb"},
            {"name": "updated_at", "type": "timestamptz", "default": "now()"},
        ],
        "relations": [{"name": "workspace", "type": "belongs_to", "target": "Workspace", "fk_column": "workspace_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "soft_delete": False,
        "timestamps": ["updated_at"],
    },
    {
        "id": "E-064",
        "name": "DesignMock",
        "table_name": "design_mocks",
        "source_migration": "20260502000000_design_mocks.sql",
        "purpose": "GrapesJS 流の HTML エディタが生成する mock 中間表現 (design_frames とは別 namespace / S-023 GUI/AI/HTML 3 mode 編集)",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "workspace_id", "type": "bigint", "nullable": False, "fk": "workspaces.id"},
            {"name": "name", "type": "text", "nullable": False},
            {"name": "html", "type": "text"},
            {"name": "css", "type": "text"},
            {"name": "components", "type": "jsonb"},
        ],
        "relations": [{"name": "workspace", "type": "belongs_to", "target": "Workspace", "fk_column": "workspace_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
    },
    {
        "id": "E-065",
        "name": "ApprovalQueue",
        "table_name": "approval_queue",
        "source_migration": "20260501220000_initial_schema.sql",
        "purpose": "Red line 検出時の human-in-the-loop approval queue (PR merge / deploy / destructive op の承認待ち)",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "workspace_id", "type": "bigint", "fk": "workspaces.id"},
            {"name": "request_type", "type": "text", "nullable": False},
            {"name": "payload", "type": "jsonb"},
            {"name": "status", "type": "text", "default": "'pending'", "check": "status IN ('pending','approved','rejected','expired')"},
            {"name": "approved_by", "type": "text"},
            {"name": "decided_at", "type": "timestamptz"},
        ],
        "relations": [{"name": "workspace", "type": "belongs_to", "target": "Workspace", "fk_column": "workspace_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"},
        "soft_delete": False,
        "timestamps": ["created_at", "decided_at"],
    },
    {
        "id": "E-066",
        "name": "Checkpoint",
        "table_name": "checkpoints",
        "source_migration": "20260501220000_initial_schema.sql",
        "purpose": "claude-agent-sdk session の checkpoint (resume 時に from_checkpoint で再開). sessions.resume_choice='from_checkpoint' で参照",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "session_id", "type": "bigint", "nullable": False, "fk": "sessions.id"},
            {"name": "checkpoint_id", "type": "text", "nullable": False, "unique": True},
            {"name": "context_snapshot", "type": "jsonb"},
            {"name": "tool_state", "type": "jsonb"},
        ],
        "relations": [{"name": "session", "type": "belongs_to", "target": "Session", "fk_column": "session_id"}],
        "tenant_isolation": {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces", "via": "sessions"},
        "soft_delete": False,
        "timestamps": ["created_at"],
    },
    {
        "id": "E-067",
        "name": "SchemaVersion",
        "table_name": "schema_versions",
        "source_migration": "20260512000000_impl_integration_ops_tables.sql",
        "purpose": "Build-Factory 自身の schema migration バージョン管理 (alembic とは別 ops 用)",
        "fields": [
            {"name": "version", "type": "text", "primary_key": True},
            {"name": "applied_at", "type": "timestamptz", "default": "now()"},
            {"name": "checksum", "type": "text"},
        ],
        "relations": [],
        "tenant_isolation": {"type": "none", "column": None, "fk_table": None},
        "soft_delete": False,
        "timestamps": ["applied_at"],
    },
    {
        "id": "E-068",
        "name": "KnowledgeBase",
        "table_name": "knowledge_base",
        "source_migration": "20260501220000_initial_schema.sql",
        "purpose": "汎用 RAG knowledge store (private/account_shared/public/ai_only 4 scope). pgvector + pg_trgm hybrid search",
        "fields": [
            {"name": "id", "type": "bigserial", "primary_key": True},
            {"name": "account_id", "type": "bigint", "fk": "accounts.id"},
            {"name": "scope", "type": "text", "check": "scope IN ('private','account_shared','public','ai_only')"},
            {"name": "title", "type": "text"},
            {"name": "content", "type": "text"},
            {"name": "embedding", "type": "vector(1536)"},
            {"name": "tsv", "type": "tsvector", "generated": True},
            {"name": "metadata", "type": "jsonb"},
        ],
        "relations": [{"name": "account", "type": "belongs_to", "target": "Account", "fk_column": "account_id"}],
        "tenant_isolation": {"type": "account_scoped", "column": "account_id", "fk_table": "accounts"},
        "soft_delete": False,
        "timestamps": ["created_at", "updated_at"],
        "indexes": ["ivfflat(embedding)", "GIN(tsv)"],
    },
]


def gen_policies_for_entity(name: str, impl_table: str | None, tenant: dict, policy_count: int) -> list[dict]:
    """Generate 2-4 representative access_control_policies based on tenant scope."""
    if impl_table is None:
        return []
    policies: list[dict] = [
        {
            "name": f"{impl_table}_service_role_all",
            "operation": "ALL",
            "role": "service_role",
            "predicate": "true",
            "rationale": "backend service は全 record にアクセス可 (RLS bypass 相当)",
        }
    ]
    t = tenant.get("type", "none")
    if t == "workspace_scoped":
        policies.append({
            "name": f"{impl_table}_workspace_member_select",
            "operation": "SELECT",
            "role": "authenticated",
            "predicate": "bf_can_access_workspace(workspace_id)",
            "rationale": "workspace_members に参加していれば SELECT 可",
        })
        policies.append({
            "name": f"{impl_table}_workspace_member_write",
            "operation": "ALL",
            "role": "authenticated",
            "predicate": "bf_can_access_workspace(workspace_id) AND bf_can_write_workspace(workspace_id)",
            "rationale": "contributor 以上の workspace_member は書き込み可",
        })
    elif t == "account_scoped":
        col = tenant.get("column", "account_id")
        policies.append({
            "name": f"{impl_table}_account_member_select",
            "operation": "SELECT",
            "role": "authenticated",
            "predicate": f"{col} IN (SELECT account_id FROM account_members WHERE user_id = auth.uid()::text)",
            "rationale": "account_members に参加していれば SELECT 可",
        })
        policies.append({
            "name": f"{impl_table}_account_owner_write",
            "operation": "ALL",
            "role": "authenticated",
            "predicate": f"{col} IN (SELECT account_id FROM account_members WHERE user_id = auth.uid()::text AND role = 'account_owner')",
            "rationale": "account_owner のみ書き込み可",
        })
    elif t == "user_scoped":
        col = tenant.get("column", "user_id")
        policies.append({
            "name": f"{impl_table}_self_select",
            "operation": "SELECT",
            "role": "authenticated",
            "predicate": f"{col} = auth.uid()::text",
            "rationale": "ユーザーは自分の record のみ参照可",
        })
        policies.append({
            "name": f"{impl_table}_self_write",
            "operation": "ALL",
            "role": "authenticated",
            "predicate": f"{col} = auth.uid()::text",
            "rationale": "ユーザーは自分の record のみ書き込み可",
        })
    # 注: policy_count は migration 実測値 (drift hint 用 metadata に格納)
    return policies


def build_entity_from_v1(v1_ent: dict, table_map: dict[str, str], policy_counts: dict[str, int]) -> dict:
    name = v1_ent["name"]
    info = ENTITY_TABLE_MAP.get(name)
    if info is None:
        # 未マップ entity (想定外) — fallback
        impl_table = None
        spec_table = name.lower() + "s"
        tenant = {"type": "workspace_scoped", "column": "workspace_id", "fk_table": "workspaces"}
        drift = {"severity": "unknown", "note": f"v1 entity '{name}' に対する mapping 未定義"}
    else:
        impl_table = info["impl"]
        spec_table = info["spec"]
        tenant = info["tenant"]
        drift = info.get("drift", {"severity": "low", "note": ""})

    # impl table が実在するか確認
    table_exists_in_migration = impl_table in table_map if impl_table else False
    if impl_table and not table_exists_in_migration:
        # impl 名が migration に無い → critical drift
        drift = {**drift, "table_missing": True}

    policy_count_actual = policy_counts.get(impl_table, 0) if impl_table else 0
    policies = gen_policies_for_entity(name, impl_table, tenant, policy_count_actual)

    legacy_drift_notes = None
    if drift.get("severity") not in (None, "low"):
        legacy_drift_notes = {
            "spec_table": spec_table,
            "impl_table": impl_table if impl_table else "(missing)",
            "diff_severity": drift.get("severity"),
            "recommendation": drift.get("note", ""),
            "task_id": f"T-V3-DRIFT-{v1_ent['id']}",
            "policy_count_actual": policy_count_actual,
            "source_migration": table_map.get(impl_table) if impl_table else None,
        }
    elif impl_table and table_exists_in_migration:
        legacy_drift_notes = None  # 一致
    else:
        legacy_drift_notes = {
            "spec_table": spec_table,
            "impl_table": None,
            "diff_severity": "critical",
            "recommendation": f"spec entity '{name}' に対応する table が migration に存在せず. 実装 or spec 修正のいずれか",
            "task_id": f"T-V3-DRIFT-{v1_ent['id']}",
            "policy_count_actual": 0,
            "source_migration": None,
        }

    # v1 fields を整形 (string array → object array)
    raw_fields = v1_ent.get("fields", [])
    fields_objs = []
    for f in raw_fields:
        if isinstance(f, str):
            # 簡易 parse: "name (...)"
            fname = f.split(" ", 1)[0].split("(", 1)[0].strip()
            ftype = f[len(fname):].strip() if len(f) > len(fname) else ""
            fields_objs.append({"name": fname, "raw_v1_descriptor": f.strip()})
        elif isinstance(f, dict):
            fields_objs.append(f)

    entity = {
        "id": v1_ent["id"],
        "name": name,
        "table_name": impl_table if impl_table else spec_table,
        "spec_table_name": spec_table,
        "fields": fields_objs,
        "relations": [{"raw_v1_descriptor": r} if isinstance(r, str) else r for r in v1_ent.get("relations", [])],
        "soft_delete": v1_ent.get("soft_delete", False),
        "timestamps": ["created_at", "updated_at", "deleted_at"] if v1_ent.get("soft_delete") else ["created_at", "updated_at"],
        "indexes": v1_ent.get("indexes", []),
        "tenant_isolation": tenant,
        "access_control_policies": policies,
        "status": v1_ent.get("status", "decided"),
        "legacy_drift_notes": legacy_drift_notes,
        "policy_count_in_migration": policy_count_actual,
    }
    # 追加 metadata
    if v1_ent.get("constraints"):
        entity["constraints"] = v1_ent["constraints"]
    if v1_ent.get("rls"):
        entity["rls_spec_note"] = v1_ent["rls"]
    if v1_ent.get("partition_strategy"):
        entity["partition_strategy"] = v1_ent["partition_strategy"]
    if v1_ent.get("retention_days"):
        entity["retention_days"] = v1_ent["retention_days"]
    if v1_ent.get("retention_years"):
        entity["retention_years"] = v1_ent["retention_years"]
    if v1_ent.get("purpose"):
        entity["purpose"] = v1_ent["purpose"]

    return entity


def build_entity_from_new(new_ent: dict, table_map: dict[str, str], policy_counts: dict[str, int]) -> dict:
    name = new_ent["name"]
    impl_table = new_ent["table_name"]
    tenant = new_ent["tenant_isolation"]
    policy_count_actual = policy_counts.get(impl_table, 0)
    policies = gen_policies_for_entity(name, impl_table, tenant, policy_count_actual)

    entity = {
        "id": new_ent["id"],
        "name": name,
        "table_name": impl_table,
        "spec_table_name": impl_table,  # 新規なので spec=impl 一致
        "fields": new_ent.get("fields", []),
        "relations": new_ent.get("relations", []),
        "soft_delete": new_ent.get("soft_delete", False),
        "timestamps": new_ent.get("timestamps", []),
        "indexes": new_ent.get("indexes", []),
        "tenant_isolation": tenant,
        "access_control_policies": policies,
        "status": "discovered_in_migration",
        "legacy_drift_notes": {
            "spec_table": None,
            "impl_table": impl_table,
            "diff_severity": "new",
            "recommendation": "v1 entities.json に未掲載. v3 で正式 entity 化",
            "task_id": f"T-V3-DRIFT-{new_ent['id']}",
            "policy_count_actual": policy_count_actual,
            "source_migration": new_ent.get("source_migration"),
        },
        "policy_count_in_migration": policy_count_actual,
        "purpose": new_ent.get("purpose"),
        "constraints": new_ent.get("constraints"),
    }
    return entity


def main():
    v1 = json.loads(V1_PATH.read_text())
    table_map = load_migration_tables()
    policy_counts = count_policies_per_table()

    print(f"[info] migration tables found: {len(table_map)}")
    print(f"[info] tables with RLS policies: {len(policy_counts)}")
    print(f"[info] v1 entities: {len(v1['entities'])}")

    out_entities: list[dict] = []
    for v1_ent in v1["entities"]:
        out_entities.append(build_entity_from_v1(v1_ent, table_map, policy_counts))
    for new_ent in NEW_ENTITIES:
        out_entities.append(build_entity_from_new(new_ent, table_map, policy_counts))

    # drift summary
    drift_high = [e for e in out_entities if e.get("legacy_drift_notes") and e["legacy_drift_notes"].get("diff_severity") in ("high", "critical")]
    drift_medium = [e for e in out_entities if e.get("legacy_drift_notes") and e["legacy_drift_notes"].get("diff_severity") == "medium"]
    drift_new = [e for e in out_entities if e.get("legacy_drift_notes") and e["legacy_drift_notes"].get("diff_severity") == "new"]

    output = {
        "version": "v3",
        "project": "Build-Factory",
        "created_at": "2026-05-16",
        "drift_detection_mode": True,
        "predecessor": "docs/functional-breakdown/2026-05-09_v1/entities.json",
        "profile": "skills/functional-breakdown/references/profiles/build-factory.md",
        "schema_doc": "skills/functional-breakdown/references/v3-core.md",
        "stats": {
            "v1_entity_count": len(v1["entities"]),
            "new_entity_count": len(NEW_ENTITIES),
            "total_entity_count": len(out_entities),
            "migration_table_count": len(table_map),
            "drift_high_critical_count": len(drift_high),
            "drift_medium_count": len(drift_medium),
            "drift_new_count": len(drift_new),
        },
        "common_fields": v1.get("common_fields"),
        "extensions_required": v1.get("extensions_required"),
        "entities": out_entities,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n")
    print(f"[ok] wrote {OUT_PATH}")
    print(f"[stats] total={len(out_entities)} v1={len(v1['entities'])} new={len(NEW_ENTITIES)} drift_high+critical={len(drift_high)} drift_medium={len(drift_medium)} drift_new={len(drift_new)}")

    # validate: 各 entity の table_name が migration に存在するか
    missing = []
    for e in out_entities:
        if e["table_name"] not in table_map:
            missing.append((e["id"], e["name"], e["table_name"]))
    if missing:
        print("[warn] entities pointing to non-existent tables:")
        for mid, mname, mtable in missing:
            print(f"  - {mid} {mname} -> {mtable}")

    return output, missing


if __name__ == "__main__":
    main()
