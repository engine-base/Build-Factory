# v3 拡張フィールド — functional-breakdown 出力スキーマ

> 2026-05-15 v3 から、functional-breakdown の 4 種 JSON 出力に **下流の 3-tier AC を埋めるための紐付け情報** を追加した。
> ここで定義する v3 拡張フィールドは、task-decomposition / architecture-design / lint #17-19 / verify-rls-coverage の入力として消費される。

## なぜ v3 拡張が必要か

v1 / v2 では:
- screens.json に `related_apis` はあったが、backend にそれが実在するかは検証不能
- entities.json に `tenant_field` はあったが、RLS policy が宣言数 / 実装数で乖離 (43 宣言 → 15 実装)
- features.json の AC は自然文のみ、EARS 形式の規範がなく後段で書き直し

v3 では下流ツールチェーン (`lint-mock-impl-diff.sh #17` / `lint-screens-api.py #18` / `lint-entity-table-naming.py #19` / `verify-rls-coverage.py` / `validate-ears-ac.py`) が機能するよう、**spec 側で必要情報を明示** する。

## screens.json 拡張

各 screen item に以下を追加:

```json
{
  "id": "S-001",
  "name": "login",
  ...既存フィールド...,

  // v3 拡張
  "mock_path": "docs/mocks/2026-05-15_v3/auth/S-001-login.html",
  "bf_meta": {
    "screen_id": "S-001",
    "screen_name": "login",
    "category": "auth",
    "status": "wip" | "decided",
    "version": "v3"
  },
  "h1_text": "ログイン",
  "kpi_labels": [],
  "section_h2_texts": ["メールアドレスでログイン", "ソーシャルログイン"],
  "responsive_breakpoints": ["mobile", "tablet", "desktop"],
  "legacy_drift_notes": null
}
```

### 各フィールドの用途

| フィールド | 用途 / 検証 |
|---|---|
| `mock_path` | lint #17 mock-impl-diff の対象パス特定 |
| `bf_meta` | mock HTML の `<meta name="bf-screen-id" / "bf-screen-name" / "bf-category" / "bf-status" / "bf-version">` と完全一致を検証 |
| `h1_text` | structural Tier 1 AC の正準 h1 文字列 (lint #17 で実装 `<h1>` と diff) |
| `kpi_labels` | Hero KPI セクションのラベル配列 (lint #17 で `<KpiCard label="...">` と diff)。Dashboard 系画面のみ必須 |
| `section_h2_texts` | 主要セクション見出し配列 (lint #17 で `<section><h2>` 集合一致を検証) |
| `responsive_breakpoints` | mock の responsive 設計 (e.g., mobile drawer 有無) を明示 |
| `legacy_drift_notes` | 既存実装ありの場合のみ。spec ↔ 実装の差分メモ (STEP 1 drift モード出力) |

## features.json 拡張

各 feature item に以下を追加:

```json
{
  "id": "F-001",
  "name": "メール認証ログイン",
  "category": "auth",
  ...既存フィールド (happy_path, error_paths, policies, auth_specific 等)...,

  // v3 拡張
  "api_endpoints": [
    {
      "method": "POST",
      "path": "/api/auth/login",
      "auth": "public",
      "inputs": {"email": "string", "password": "string", "mfa_code": "string?"},
      "outputs_2xx": {"access_token": "string", "refresh_token": "string", "user_id": "uuid"},
      "outputs_4xx": [{"code": 401, "body": "{error: 'invalid_credentials'}"}, {"code": 429, "body": "{error: 'rate_limited'}"}],
      "rate_limit": "5/min/ip",
      "related_entities": ["E-001 User", "E-038 AuthSession"]
    },
    {
      "method": "POST",
      "path": "/api/auth/logout",
      "auth": "authenticated",
      "inputs": {},
      "outputs_2xx": {"status": "ok"}
    }
  ],
  "ears_ac_seed": [
    "EVENT-DRIVEN: When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.",
    "UNWANTED: If credentials are invalid, the system shall return 401 with generic message (no user enumeration).",
    "EVENT-DRIVEN: When 5 failed login attempts occur within 15 min for the same IP, the system shall return 429 (rate-limited).",
    "STATE-DRIVEN: While a refresh_token is valid, the system shall allow access_token regeneration."
  ]
}
```

### 各フィールドの用途

| フィールド | 用途 / 検証 |
|---|---|
| `api_endpoints[]` | lint #18 screens-API: backend に実在する FastAPI router と method+path が 1:1 一致を検証 / task-decomposition の `related_apis` の source |
| `api_endpoints[].auth` | `public` / `authenticated` / `<role>` (e.g., `account_owner`) — auth middleware 要否を明示 |
| `api_endpoints[].outputs_4xx` | エラーレスポンス仕様 — task-decomposition の Tier 2 UNWANTED AC の source |
| `api_endpoints[].rate_limit` | rate-limit middleware 設定 |
| `ears_ac_seed[]` | EARS 5 形式 (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED) で書く Tier 2 functional AC のドラフト。task-decomposition が各タスクの `acceptance_criteria.functional` に組み込む |

`ears_ac_seed` は **5 形式のいずれか** で書く (`validate-ears-ac.py` が形式を検証):
- **UBIQUITOUS** : The system **shall** ...
- **EVENT-DRIVEN** : When [event], the system **shall** ...
- **STATE-DRIVEN** : While [state], the system **shall** ...
- **OPTIONAL** : Where [feature is enabled], the system **shall** ...
- **UNWANTED** : If [unwanted condition], the system **shall not** ...

## entities.json 拡張

各 entity item に以下を追加:

```json
{
  "id": "E-001",
  "name": "User",
  ...既存フィールド...,

  // v3 拡張
  "table_name": "users",
  "rls_policies": [
    {
      "name": "users_self_select",
      "operation": "SELECT",
      "role": "authenticated",
      "predicate": "auth.uid() = id",
      "rationale": "ユーザーは自分の record のみ閲覧可"
    },
    {
      "name": "users_self_update",
      "operation": "UPDATE",
      "role": "authenticated",
      "predicate": "auth.uid() = id",
      "rationale": "ユーザーは自分の record のみ更新可"
    },
    {
      "name": "users_admin_all",
      "operation": "ALL",
      "role": "service_role",
      "predicate": "true",
      "rationale": "backend service は全 record にアクセス可"
    }
  ],
  "tenant_isolation": {
    "type": "account_scoped",
    "column": "account_id",
    "fk_table": "accounts"
  }
}
```

### 各フィールドの用途

| フィールド | 用途 / 検証 |
|---|---|
| `table_name` | lint #19 entity-table-naming: PascalCase entity name → snake_case table name の対応を明示。`bf_` prefix は禁止 (v1 で混入) |
| `rls_policies[]` | verify-rls-coverage.py: 各 entity に対する RLS policy 配列。0 件の場合 (= RLS なし) は明示的に `[]` で書く (null 禁止) |
| `rls_policies[].name` | `<table>:<policy_name>` の形で task-decomposition の `rls_policies_required` にコピーされる |
| `rls_policies[].operation` | `SELECT` / `INSERT` / `UPDATE` / `DELETE` / `ALL` |
| `rls_policies[].predicate` | SQL 表現 (PostgreSQL RLS の USING / WITH CHECK 句で使う) |
| `tenant_isolation` | multi-tenancy のスコープ。`account_scoped` / `workspace_scoped` / `user_scoped` / `none` |

### naming 規約

- **entity name**: PascalCase (例: `User`, `AccountMember`, `WorkspaceInvitation`)
- **table_name**: snake_case (例: `users`, `account_members`, `workspace_invitations`)
- **禁止**: `bf_` prefix (v1 で `bf_features`, `bf_mocks` 等が混入したが v3 で全廃)
- **複数形**: table_name は基本 plural (例: `users`)、ただし PostgreSQL 予約語の場合は singular でも可

## roles.json 拡張

各 `object_constraint` に `rls_predicate_expr` を追加:

```json
{
  "object_constraints": [
    {
      "role": "R-002",
      "entity": "E-003 Order",
      "constraint": "owned_by_self",
      "description": "自分の注文のみ閲覧可",
      "rls_predicate_expr": "user_id = auth.uid()"
    },
    {
      "role": "R-002",
      "entity": "E-006 OrganizationMember",
      "constraint": "owned_by_organization",
      "description": "同一組織内のみ",
      "rls_predicate_expr": "organization_id = (SELECT organization_id FROM organization_members WHERE user_id = auth.uid())"
    }
  ]
}
```

### 各フィールドの用途

| フィールド | 用途 |
|---|---|
| `rls_predicate_expr` | entities.json の `rls_policies[].predicate` の source となる SQL 表現。constraint type を抽象から具体 SQL に降ろす |

## 任意: addendum.json

spec の事後修正 (ADR 起票後の差分など) は addendum.json として別出力する。
ファイル命名: `<date>-<adr-id>-addendum.json` (例: `2026-05-13-adr-012-addendum.json`)

```json
{
  "meta": {
    "date": "2026-05-13",
    "adr_id": "ADR-012",
    "title": "Anthropic 公式 Memory 機能採用",
    "amends": "ADR-010"
  },
  "screens_added": ["S-XXX"],
  "screens_modified": [{"id": "S-038", "changes": ["fields.skills のソース変更"]}],
  "features_added": ["F-XXX"],
  "features_modified": [],
  "entities_added": ["E-046 MemoryEntry"],
  "entities_modified": [{"id": "E-007 AIEmployee", "changes": ["+memory_provider field"]}],
  "roles_modified": [],
  "decision_rationale": "..."
}
```

これは architecture-design / task-decomposition が次回 sync するときに pull する補正情報。

## drift 検知モード (STEP 1 オプション)

既存実装が存在するプロジェクト (リファクタリング / 受託継続案件) では、STEP 1 で **drift 検知モード** を起動できる:

1. ユーザーが「既存実装あり」を STEP 1 で明示
2. AI が以下を比較:
   - mock HTML の `<meta name="bf-screen-id">` ↔ 実装 page.tsx のコメントヘッダ
   - mock HTML `<h1>` ↔ 実装 `<h1>`
   - mock HTML `<section><h2>` 集合 ↔ 実装の sections
   - screens.json `related_apis` ↔ backend router (file listing で endpoint 抽出)
3. drift を `legacy_drift_notes` フィールドに記録:

```json
{
  "id": "S-006",
  "name": "account_dashboard",
  "h1_text": "10 案件 俯瞰",
  ...
  "legacy_drift_notes": {
    "detected_at": "2026-05-15",
    "mock_h1": "10 案件 俯瞰",
    "impl_h1": "AI 社員ダッシュボード",
    "diff_severity": "high",
    "recommendation": "実装を mock h1 に統一 (T-V3-DRIFT-01 で改修)",
    "task_id": "T-V3-DRIFT-01"
  }
}
```

これが task-decomposition の Group D (重大 drift 修正) の task source となる。

## 連携先一覧

| 下流 | このスキルが供給する情報 |
|---|---|
| **task-decomposition** | screens.bf_meta / entities.rls_policies / features.api_endpoints / features.ears_ac_seed |
| **architecture-design** | features.api_endpoints (API 設計の元) / entities (DB 設計の元) / roles.matrix (RBAC 設計) |
| **api-design** | features.api_endpoints を OpenAPI 仕様に展開 |
| **lint #17 mock-impl-diff** | screens.h1_text / kpi_labels / section_h2_texts / mock_path |
| **lint #18 screens-API** | features.api_endpoints の method+path |
| **lint #19 entity-table-naming** | entities.table_name (PascalCase → snake_case) |
| **verify-rls-coverage.py** | entities.rls_policies の存在 + role/operation/predicate |
| **validate-ears-ac.py** | features.ears_ac_seed の EARS 5 形式準拠 |

## v1 / v2 出力との互換性

- v1 (`docs/functional-breakdown/2026-05-09_v1/`): 既存出力は **freeze** (修正禁止)。v3 拡張フィールドは持たない
- v3 (`docs/functional-breakdown/2026-05-15_v3/`): 新規出力先。v3 拡張フィールド込みで書く
- ローダー (architecture-design / task-decomposition) は v3 を優先 / v1 は legacy_task_id 経由の参照のみ
