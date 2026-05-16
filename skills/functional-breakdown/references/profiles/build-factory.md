# Build-Factory Profile (functional-breakdown)

> このファイルは v3 functional-breakdown スキルを **Build-Factory** プロジェクトに適用するための profile 例。
> 他プロジェクトは独自 profile (`references/profiles/<project>.md`) を作成する。
> この profile は「**例**」であり、SKILL.md / v3-core.md の内容を強制するものではない。

## script path (機械検証 runner)

| 役割 | path |
|---|---|
| mock-impl-diff lint | `scripts/lint-mock.sh` (rule_id: `mock-impl-diff`, 旧 lint #17) |
| screens-API lint | `scripts/lint-mock.sh` (rule_id: `screens-API`, 旧 lint #18) |
| entity-table-naming lint | `scripts/lint-mock.sh` (rule_id: `entity-table-naming`, 旧 lint #19) |
| access-control verifier | `scripts/verify-rls-coverage.py` |
| EARS validator | `scripts/validate-ears-ac.py` |
| ticket validator | `scripts/validate-tickets.py` |

## meta タグ schema (mock HTML 用)

`meta_tags` field は Build-Factory で `bf_meta` と呼ばれる schema を採用:

```html
<meta name="bf-screen-id" content="S-001">
<meta name="bf-screen-name" content="login">
<meta name="bf-category" content="auth">
<meta name="bf-status" content="wip">
<meta name="bf-version" content="v3">
```

screens.json の `meta_tags` field とこの 5 tag が完全一致するか lint で検証。

## technology stack (前提)

| layer | 採用技術 |
|---|---|
| access control | Supabase RLS (PostgreSQL Row Level Security) |
| vector DB | pgvector |
| full-text search | pg_trgm |
| auth | Supabase Auth (GoTrue) + 2FA (TOTP) |
| backend | FastAPI (modular monolith) + SQLAlchemy 2.0 async |
| frontend | Next.js 15 (App Router) + shadcn/ui + Tailwind 4 |
| hosting | Vercel + Oracle Cloud Free Tier + Supabase Free |
| mock format | static HTML + Lucide Icons (絵文字禁止) |

## predicate 言語

`access_control_policies[].predicate` と `access_predicate_expr` は **PostgreSQL RLS の SQL 表現** を採用 (USING / WITH CHECK 句):

```sql
auth.uid() = id
account_id = (SELECT account_id FROM account_members WHERE user_id = auth.uid())
```

## naming 規約

- **entity name**: PascalCase (例: `User`, `AccountMember`, `WorkspaceInvitation`)
- **table_name**: snake_case (例: `users`, `account_members`, `workspace_invitations`)
- **禁止 prefix**: `bf_` prefix (v1 で `bf_features`, `bf_mocks` 等が混入したが v3 で全廃)
- **複数形**: 基本 plural、ただし PostgreSQL 予約語の場合は singular でも可

## mock_path 規約

```
docs/mocks/<date>_v3/<category>/S-XXX-<slug>.html
```

例: `docs/mocks/2026-05-15_v3/auth/S-001-login.html`

## 数値例 (実プロジェクトで採用された値)

| 項目 | 値 |
|---|---|
| screens 件数 | 43 |
| features 件数 | 30 |
| roles 件数 | 6 |
| entities 件数 | 43 |
| tasks (task-decomposition で展開) | 187 |
| backend test 件数 | 8000 |

## drift 検知モードでの比較対象

| 層 | spec | impl |
|---|---|---|
| entity ↔ DB schema | entities.table_name | `data/migrations/*.sql` (Supabase migrations) |
| API ↔ backend router | features.api_endpoints (method+path) | `backend/routers/*.py` (FastAPI router) |
| screen ↔ frontend component | screens.h1_text / kpi_labels / section_h2_texts / mock_path | `frontend/app/**/page.tsx` |

## 下流連携 task group (drift)

drift が検出された場合の task-decomposition 側の流し込み先:

| drift 種別 | 流し込み先 group |
|---|---|
| entity drift (table_name mismatch / column drift) | Group D (Drift fix) |
| API drift (endpoint missing) | Group B-1 (Vertical Slice / Backend) |
| API drift (signature mismatch) | Group D (Drift fix) |
| screen drift (h1 / KPI / section mismatch) | Group D (Drift fix) |

## 固有名詞

- project name: Build-Factory
- company: ENGINE BASE (株式会社 ENGINE BASE)
- responsible person: 高本まさと (masato@engine-base.com)

## design token (ui-mockup 連携)

- primary color: ENGINE BASE green `#1a6648` (Tailwind: `eb-500`)
- icon library: Lucide Icons (絵文字禁止)
- font: Noto Sans JP + JetBrains Mono

## v3 出力先 directory

- `docs/functional-breakdown/2026-05-15_v3/` (v3 新規)
- `docs/functional-breakdown/2026-05-09_v1/` (v1 freeze)

## 関連 ADR

| ADR | 内容 |
|---|---|
| ADR-011 | 完了判定ゲート (pre-commit-check.sh が単一ゲート) |
| ADR-012 | Anthropic 公式 Memory 機能採用 (ADR-010 amend) |
