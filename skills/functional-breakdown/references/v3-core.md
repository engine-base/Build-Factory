# v3 Core Concepts — functional-breakdown

> functional-breakdown の v3 で導入した汎用 (project-agnostic) 概念。
> ここで定義する v3 拡張フィールドは、下流 task-decomposition / architecture-design / api-design / lint runner / access-control verifier / EARS validator の入力として消費される。
> プロジェクト固有値の適用例は `references/profiles/build-factory.md` を参照。他プロジェクトは独自 profile を作る。

## なぜ v3 拡張が必要か (汎用)

v1 / v2 では:
- screens に `related_apis` はあったが、backend にそれが実在するかは検証不能
- entities に `tenant_field` はあったが、access-control policy の宣言数 / 実装数で乖離が起きやすい
- features の AC は自然文のみ、EARS 形式の規範がなく後段で書き直し

v3 では下流ツールチェーン (lint runner / access-control verifier / EARS validator) が機能するよう、**spec 側で必要情報を明示** する。

## 詳細化順序 (Foundation → Backend → UI 汎用)

functional-breakdown は **entity (data) → service (feature) → API → screen (UI)** の順で詳細化する。

| layer | このスキルで対応する軸 | なぜ先に決める必要があるか |
|---|---|---|
| **Foundation / Data** | entities | DB schema / access control の前提。後段すべての contract を縛る |
| **Backend / Service** | features (incl. api_endpoints) | entity の上で動く業務 logic。UI より先に固まらないと API 契約が決まらない |
| **Cross-cutting** | roles | entity と feature の両方を横断する access control |
| **UI** | screens | entity / feature / role が決まってから UI の表示項目・操作を決める |

drift 検知モードもこの 3 層を対象にする (entity↔DB schema / API↔backend router / screen↔frontend component)。

## 3-tier AC との連携 (汎用)

functional-breakdown の出力は task-decomposition の **3-tier AC** (structural / functional / regression) を埋めるための source となる:

| 3-tier AC | source となる v3 フィールド |
|---|---|
| **structural** (mock / spec 一致) | screens.h1_text / screens.kpi_labels / screens.section_h2_texts / screens.mock_path / screens.meta_tags |
| **functional** (EARS API / access control) | features.api_endpoints / features.ears_ac_seed / entities.access_control_policies |
| **regression** (test / lint / coverage) | 下流の test-verification / CI gate config が消費 |

## entities 拡張

各 entity item に以下を追加:

```json
{
  "id": "E-001",
  "name": "User",
  ...既存フィールド...,

  // v3 拡張
  "table_name": "users",
  "access_control_policies": [
    {
      "name": "users_self_select",
      "operation": "SELECT",
      "role": "authenticated",
      "predicate": "<user_id_column> = <current_user_id_expr>",
      "rationale": "ユーザーは自分の record のみ閲覧可"
    },
    {
      "name": "users_self_update",
      "operation": "UPDATE",
      "role": "authenticated",
      "predicate": "<user_id_column> = <current_user_id_expr>",
      "rationale": "ユーザーは自分の record のみ更新可"
    },
    {
      "name": "users_admin_all",
      "operation": "ALL",
      "role": "service",
      "predicate": "true",
      "rationale": "backend service は全 record にアクセス可"
    }
  ],
  "tenant_isolation": {
    "type": "account_scoped",
    "column": "account_id",
    "fk_table": "accounts"
  },
  "legacy_drift_notes": null
}
```

### 各フィールドの用途

| フィールド | 用途 / 検証 |
|---|---|
| `table_name` | entity-table-naming lint: PascalCase entity name → snake_case table name の対応を明示。プロジェクト固有 prefix は profile で定義 (default は禁止) |
| `access_control_policies[]` | access-control verifier: 各 entity に対する row-level access policy 配列 (RLS / RBAC, if adopted)。0 件の場合 (= access control なし) は明示的に `[]` で書く (null 禁止) |
| `access_control_policies[].name` | `<table>:<policy_name>` の形で task-decomposition の `access_control_required` にコピーされる |
| `access_control_policies[].operation` | `SELECT` / `INSERT` / `UPDATE` / `DELETE` / `ALL` (project-defined operation set) |
| `access_control_policies[].predicate` | policy expression (e.g., PostgreSQL RLS の USING / WITH CHECK 句で使う SQL、Casbin / Cedar 等の policy DSL) |
| `tenant_isolation` | multi-tenancy のスコープ。`account_scoped` / `workspace_scoped` / `user_scoped` / `none` |
| `legacy_drift_notes` | 既存実装ありの場合のみ。spec ↔ DB schema の差分メモ (drift モード出力) |

### naming 規約 (汎用 base)

- **entity name**: PascalCase (例: `User`, `AccountMember`, `WorkspaceInvitation`)
- **table_name**: snake_case (例: `users`, `account_members`, `workspace_invitations`)
- **複数形**: 基本 plural、ただし予約語の場合は singular でも可
- **prefix 禁止 / 必須**: project-defined (profile に定義)

## features 拡張

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
  ],
  "legacy_drift_notes": null
}
```

### 各フィールドの用途

| フィールド | 用途 / 検証 |
|---|---|
| `api_endpoints[]` | screens-API lint: backend に実在する router と method+path が 1:1 一致を検証 / task-decomposition の `related_apis` の source |
| `api_endpoints[].auth` | `public` / `authenticated` / `<role>` (e.g., `account_owner`) — auth middleware 要否を明示 |
| `api_endpoints[].outputs_4xx` | エラーレスポンス仕様 — task-decomposition の Tier 2 UNWANTED AC の source |
| `api_endpoints[].rate_limit` | rate-limit middleware 設定 |
| `ears_ac_seed[]` | EARS 5 形式 (UBIQUITOUS / EVENT-DRIVEN / STATE-DRIVEN / OPTIONAL / UNWANTED) で書く Tier 2 functional AC のドラフト。task-decomposition が各タスクの `acceptance_criteria.functional` に組み込む |
| `legacy_drift_notes` | 既存実装ありの場合のみ。spec ↔ backend router の差分メモ |

`ears_ac_seed` は **5 形式のいずれか** で書く (EARS validator が形式を検証):
- **UBIQUITOUS** : The system **shall** ...
- **EVENT-DRIVEN** : When [event], the system **shall** ...
- **STATE-DRIVEN** : While [state], the system **shall** ...
- **OPTIONAL** : Where [feature is enabled], the system **shall** ...
- **UNWANTED** : If [unwanted condition], the system **shall not** ...

## roles 拡張

各 `object_constraint` に `access_predicate_expr` を追加:

```json
{
  "object_constraints": [
    {
      "role": "R-002",
      "entity": "E-003 Order",
      "constraint": "owned_by_self",
      "description": "自分の注文のみ閲覧可",
      "access_predicate_expr": "user_id = <current_user_id_expr>"
    },
    {
      "role": "R-002",
      "entity": "E-006 OrganizationMember",
      "constraint": "owned_by_organization",
      "description": "同一組織内のみ",
      "access_predicate_expr": "organization_id = (SELECT organization_id FROM organization_members WHERE user_id = <current_user_id_expr>)"
    }
  ]
}
```

### 各フィールドの用途

| フィールド | 用途 |
|---|---|
| `access_predicate_expr` | entities の `access_control_policies[].predicate` の source となる expression。constraint type を抽象から具体 policy expression に降ろす (project-defined: SQL / Casbin / Cedar 等) |

## screens 拡張

各 screen item に以下を追加:

```json
{
  "id": "S-001",
  "name": "login",
  ...既存フィールド...,

  // v3 拡張
  "mock_path": "<project_mock_dir>/auth/S-001-login.html",
  "meta_tags": {
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
| `mock_path` | mock-impl-diff lint の対象パス特定 |
| `meta_tags` | mock HTML の machine-readable meta (project-defined schema, e.g., `<meta name="...">` 群) と完全一致を検証。tag 名 prefix は project-defined |
| `h1_text` | structural Tier 1 AC の正準 h1 文字列 (lint で実装 `<h1>` と diff) |
| `kpi_labels` | Hero KPI セクションのラベル配列 (lint で実装の KPI コンポーネントと diff)。Dashboard 系画面のみ必須 |
| `section_h2_texts` | 主要セクション見出し配列 (lint で `<section><h2>` 集合一致を検証) |
| `responsive_breakpoints` | mock の responsive 設計 (e.g., mobile drawer 有無) を明示 |
| `legacy_drift_notes` | 既存実装ありの場合のみ。spec ↔ frontend component の差分メモ |

## 任意: addendum.json

spec の事後修正 (decision record (ADR) 起票後の差分など) は addendum.json として別出力する。
ファイル命名: `<date>-<adr-id>-addendum.json` (例: `2026-05-13-adr-012-addendum.json`)

```json
{
  "meta": {
    "date": "2026-05-13",
    "adr_id": "ADR-XXX",
    "title": "<決定の題目>",
    "amends": "ADR-YYY"
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

## drift 検知モード (3 層 / STEP 1 オプション)

既存実装が存在するプロジェクト (リファクタリング / 受託継続案件) では、STEP 1 で **drift 検知モード** を起動できる。
v3 では **3 層 drift** をカバー:

1. **entity ↔ DB schema** (entities.table_name と migration ファイル)
2. **API ↔ backend router** (features.api_endpoints と実装 endpoint)
3. **screen ↔ frontend component** (screens.h1_text / kpi_labels / section_h2_texts と実装 page)

### 起動フロー

1. ユーザーが「既存実装あり」を STEP 1 で明示
2. AI が以下を比較:
   - entity 層: entities.table_name ↔ migration ファイル / DB schema dump
   - API 層: features.api_endpoints (method+path) ↔ backend router 配下の実装 endpoint
   - screen 層: screens.meta_tags ↔ 実装 page のヘッダ / screens.h1_text ↔ 実装 `<h1>` / screens.section_h2_texts ↔ 実装の sections
3. drift を `legacy_drift_notes` フィールドに記録:

```json
{
  "id": "S-006",
  "name": "account_dashboard",
  "h1_text": "案件 俯瞰",
  ...
  "legacy_drift_notes": {
    "detected_at": "2026-05-15",
    "layer": "screen",
    "mock_h1": "案件 俯瞰",
    "impl_h1": "ダッシュボード",
    "diff_severity": "high",
    "recommendation": "実装を mock h1 に統一",
    "task_id": "T-V3-DRIFT-01"
  }
}
```

これが task-decomposition の drift 修正 group の task source となる。

## 連携先一覧 (汎用)

| 下流 | このスキルが供給する情報 |
|---|---|
| **task-decomposition** | screens.meta_tags / entities.access_control_policies / features.api_endpoints / features.ears_ac_seed |
| **architecture-design** | features.api_endpoints (API 設計の元) / entities (DB 設計の元) / roles.matrix (RBAC 設計) |
| **api-design** | features.api_endpoints を OpenAPI 仕様に展開 |
| **mock-impl-diff lint (project-defined runner)** | screens.h1_text / kpi_labels / section_h2_texts / mock_path |
| **screens-API lint (project-defined runner)** | features.api_endpoints の method+path |
| **entity-table-naming lint (project-defined runner)** | entities.table_name (PascalCase → snake_case) |
| **access-control verifier (project-defined runner)** | entities.access_control_policies の存在 + role/operation/predicate |
| **EARS validator (project-defined runner)** | features.ears_ac_seed の EARS 5 形式準拠 |

各 lint runner / verifier の具体 path は profile に定義する (e.g., `references/profiles/<project>.md`)。

## v1 / v2 出力との互換性

- v1 / v2: 既存出力は **freeze** (修正禁止)。v3 拡張フィールドは持たない
- v3: 新規出力先。v3 拡張フィールド込みで書く
- ローダー (architecture-design / task-decomposition) は v3 を優先 / v1 は legacy_task_id 経由の参照のみ
