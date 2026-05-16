# v3 拡張 — architecture-design

> 2026-05-15 v3 から、architecture-design に **Phase 0 Foundation gate / RLS strategy / Vertical Slice 適合性 / 30-50 並列対応 / ADR 起票連携** を採用。
> アーキテクチャ判断の一部として CI gate と並列開発インフラを定義することで、後段の機能分解 / タスク分解 / 実装 / 監査が漏れなく回る土台を作る。

## なぜ v3 拡張が必要か

v1 / v2 では:
- アーキテクチャが「技術スタック」「DB 構造」「セキュリティ」までで止まり、CI gate (lint / validator) が後付けになった → Phase 0 整備前に着手 → 漏れ発生
- RLS 戦略が「multi-tenant」「tenant_id カラム」レベルで止まり、entity 単位の policy が描けず実装で乖離
- 並列開発対応が暗黙 (worktree / monorepo 戦略未定義) で 30-50 並列セッションが衝突
- ADR が散発的に起票され、Phase 0 で起票すべき ADR (AUTH 戦略 / 命名規約) が漏れる

v3 では:
- **Phase 0 Foundation gate** をアーキテクチャの一部として明示
- RLS を **per-entity policy** (operation / role / predicate) で設計
- **Vertical Slice 適合性** (1 機能 = 画面+API+test+RLS の 1 PR) を STEP 2 で検証
- **30-50 並列対応** (monorepo / worktree / branch 命名) を STEP 4 で必須項目化
- **ADR 起票プロトコル** を Phase 0 task 群として定義

---

## Phase 0 Foundation gate 要件

アーキテクチャ確定時に、以下 8 ゲートを **必ず CI に組み込む** ことを保証する:

| # | Gate | script | 検出する漏れ |
|---|---|---|---|
| 1 | mock lint (1-19) | `bash scripts/lint-mock.sh` | 絵文字 / AGPL / mock-impl diff (#17) / screens-API (#18) / entity-table naming (#19) |
| 2 | 3-tier AC validator | `python3 scripts/validate-ears-ac.py docs/task-decomposition/.../tickets.json` | AC が 3-tier 分割なし / EARS 違反 |
| 3 | audit MD validator | `python3 scripts/validate-audit-md.py docs/audit/.../<task_id>.md` | audit MD 不在 / generic 文言 / impl 行範囲未記入 |
| 4 | RLS coverage | `python3 scripts/verify-rls-coverage.py` | entities.json の entity に対する RLS policy 不在 |
| 5 | pytest + coverage | `pytest --cov --cov-fail-under=70` | unit test 失敗 / カバレッジ < 70% |
| 6 | pyright strict | `pyright --strict` | Python 型エラー |
| 7 | TypeScript strict | `cd frontend && tsc --noEmit && pnpm run lint` | TS 型エラー / ESLint 違反 |
| 8 | mock-impl diff | `bash scripts/lint-mock-impl-diff.sh ${SCREEN_IDS}` | mock h1 / KPI / section-h2 と impl の不一致 |

これらは architecture-design の出力 `phase_0_gates.json` に展開される。

### phase_0_gates.json schema

```json
{
  "version": "v3",
  "created_at": "YYYY-MM-DD",
  "merge_gates": [
    {
      "id": 1,
      "name": "mock lint",
      "script": "bash scripts/lint-mock.sh",
      "blocking": true,
      "owner_task": "T-V3-INFRA-02",
      "detects": ["絵文字", "AGPL", "mock-impl diff", "screens-API", "entity-table naming"],
      "depends_on": []
    },
    {
      "id": 2,
      "name": "3-tier AC validator",
      "script": "python3 scripts/validate-ears-ac.py docs/task-decomposition/2026-05-15_v3/tickets.json",
      "blocking": true,
      "owner_task": "T-V3-INFRA-06",
      "detects": ["AC 3-tier 分割なし", "EARS 違反"],
      "depends_on": []
    }
  ],
  "ci_workflow_path": ".github/workflows/v3-gate.yml",
  "retry_protocol": {
    "max_attempts": 3,
    "on_failure": "human_escalation",
    "escalation_to": "PM"
  }
}
```

### v3-gate.yml (GitHub Actions テンプレ)

```yaml
# .github/workflows/v3-gate.yml
name: v3 merge gate

on:
  pull_request:
    branches: [main]

jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python 3.13
        uses: actions/setup-python@v5
        with: { python-version: '3.13' }

      - name: Install Python deps
        run: uv sync

      - name: Setup Node 20
        uses: actions/setup-node@v4
        with: { node-version: '20' }

      - name: Install Node deps
        run: cd frontend && pnpm install --frozen-lockfile

      - name: Gate 1 — mock lint
        run: bash scripts/lint-mock.sh

      - name: Gate 2 — 3-tier AC validator
        run: python3 scripts/validate-ears-ac.py docs/task-decomposition/2026-05-15_v3/tickets.json

      - name: Gate 3 — audit MD validator
        run: |
          for f in docs/audit/2026-05-15_v3/T-V3-*.md; do
            python3 scripts/validate-audit-md.py "$f"
          done

      - name: Gate 4 — RLS coverage
        run: python3 scripts/verify-rls-coverage.py

      - name: Gate 5 — pytest + coverage
        run: pytest --cov --cov-fail-under=70

      - name: Gate 6 — pyright strict
        run: pyright --strict

      - name: Gate 7 — TS strict + ESLint
        run: cd frontend && tsc --noEmit && pnpm run lint

      - name: Gate 8 — mock-impl diff
        if: contains(github.event.pull_request.labels.*.name, 'has-frontend')
        run: |
          # SCREEN_IDS は PR description or tickets.json から抽出
          bash scripts/lint-mock-impl-diff.sh ${SCREEN_IDS}
```

---

## RLS strategy (v3 必須)

STEP 3 で entities.json の各 entity に対する RLS policy 戦略を決める。

### 設計テンプレ (per-entity)

```json
{
  "rls_strategy": {
    "default_enable": true,
    "auth_provider": "Supabase Auth",
    "tenant_isolation_pattern": "account_scoped",
    "policy_naming_convention": "<table>_<actor>_<operation>",
    "predicates_lib": {
      "self_only": "auth.uid() = id",
      "owner_only": "auth.uid() = user_id",
      "account_member": "EXISTS (SELECT 1 FROM account_members WHERE account_id = ${table}.account_id AND user_id = auth.uid())",
      "workspace_member": "EXISTS (SELECT 1 FROM workspace_members WHERE workspace_id = ${table}.workspace_id AND user_id = auth.uid())"
    },
    "service_role_bypass": true
  },
  "table_naming": {
    "entity_case": "PascalCase",
    "table_case": "snake_case_plural",
    "forbidden_prefixes": ["bf_", "tmp_", "old_"],
    "reserved_words_strategy": "use_singular_when_conflict"
  }
}
```

### entity 単位の policy 配列 (entities.json から pull)

```json
{
  "id": "E-001",
  "name": "User",
  "table_name": "users",
  "rls_policies": [
    {"name": "users_self_select", "operation": "SELECT", "role": "authenticated", "predicate": "auth.uid() = id"},
    {"name": "users_self_update", "operation": "UPDATE", "role": "authenticated", "predicate": "auth.uid() = id"},
    {"name": "users_admin_all", "operation": "ALL", "role": "service_role", "predicate": "true"}
  ]
}
```

### lint #19 entity-table-naming で検証する項目

- entity name が PascalCase
- table name が snake_case_plural
- forbidden_prefixes に該当しない
- 予約語衝突時は singular 使用 (例: `user` ではなく `users` だが `user_setting` は singular でも OK)

---

## Vertical Slice 適合性 (STEP 2 必須検証)

アーキテクチャが「1 機能 = 画面+API+test+RLS を 1 PR で完結する」を支えられるかを検証:

| 検証項目 | OK の条件 |
|---|---|
| ディレクトリ構造 | frontend/app/<screen>/ + backend/routers/<resource>.py + backend/tests/test_<task_id>.py + supabase/migrations/<n>_<entity>.sql が同 PR で扱える |
| ビルドツール | monorepo 構造で frontend/backend 同 commit でビルド可能 (pnpm workspaces / Turborepo / Nx) |
| 型同期 | API スキーマから TS 型を自動生成 (OpenAPI → openapi-typescript / FastAPI → pydantic-to-typescript) |
| RLS migration | supabase migrations が同 PR に含まれる場合、CI で適用順序保証 |
| test 一括実行 | 1 PR で backend pytest + frontend vitest + e2e Playwright が並列実行可能 |

NG パターン:
- frontend / backend が別リポ → Vertical Slice が 2 PR に分割 → AC 整合困難
- 型生成が手動 → spec ↔ impl drift の温床
- RLS migration がアプリ起動後に手動 → CI gate #4 で検知できない

---

## 30-50 並列開発対応 (STEP 4 必須項目)

Claude Code 並列セッション 30-50 を支える設計:

### git 戦略

```yaml
git_strategy:
  workflow: "trunk-based + worktree"
  branch_naming: "claude/<task_id>"  # 例: claude/T-V3-AUTH-01
  worktree_pattern: "$REPO_ROOT/../worktrees/<task_id>"
  merge_method: "squash + auto-merge (CI 全 gate pass 時)"
  conflict_resolution: "task-decomposition の files_changed で事前衝突回避"
  parallel_session_limit: 30  # or 50 / Claude Code on web のプラン上限
```

### monorepo 構造

```
build-factory/
├── frontend/          # Next.js 15 (App Router)
│   ├── app/<screen>/  # screen 単位
│   └── components/
├── backend/           # FastAPI モジュラーモノリス
│   ├── routers/       # endpoint 単位
│   ├── services/
│   └── tests/         # pytest
├── supabase/
│   └── migrations/    # PostgreSQL migration
├── docs/              # spec / mock / audit
├── scripts/           # lint / validator
└── .github/workflows/v3-gate.yml
```

ツール候補:
- **pnpm workspaces** (Node 系のみで十分な場合 / lightweight)
- **Turborepo** (build cache / 並列 task 実行が必要なら)
- **Nx** (TS + Python 混在で deep dependency graph 必要なら)

### 衝突回避プロトコル

1. task-decomposition で各 task の `files_changed` を明示
2. 同じファイルを修正する task を別 wave に配置 (DAG で順序保証)
3. それでも衝突したら squash 後に手動 rebase (max 1 round)

---

## ADR 起票プロトコル (v3)

architecture-design は STEP 5 で `adrs-to-create.json` を出力し、Phase 0 で起票すべき ADR を列挙する。

### adrs-to-create.json schema

```json
{
  "version": "v3",
  "phase_0_required_adrs": [
    {
      "id": "ADR-013",
      "title": "AUTH 戦略 (Supabase Auth + JWT + 2FA)",
      "category": "authentication",
      "supersedes": [],
      "task_id": "T-V3-INFRA-01",
      "rationale": "...",
      "alternatives_considered": ["Auth.js", "Clerk", "自前実装"]
    },
    {
      "id": "ADR-014",
      "title": "命名規約 (PascalCase entity → snake_case table / bf_ prefix 廃止)",
      "category": "naming",
      "supersedes": [],
      "task_id": "T-V3-INFRA-01",
      "rationale": "v1 で bf_ prefix 混入 / PascalCase と snake_case 混在を統一する",
      "alternatives_considered": ["camelCase 統一", "現状維持"]
    },
    {
      "id": "ADR-015",
      "title": "root画面方針 (account dashboard / dogfood vs SaaS)",
      "category": "ui",
      "supersedes": [],
      "task_id": "T-V3-INFRA-01",
      "rationale": "...",
      "alternatives_considered": []
    }
  ],
  "decision_record_skill_handoff": "decision-record スキルへ各 ADR の起票を委譲する"
}
```

連携: 各 ADR は **decision-record** スキルを起動して `docs/decisions/ADR-XXX.md` を生成する。

---

## STEP 4.5-D 拡張: CI/Lint ツール + monorepo

v3 では 4.5-D 開発環境ツール選定に **CI/Lint** と **monorepo tool** を追加:

| サブカテゴリ | 候補例 |
|---|---|
| Linter (Python) | ruff / Ruff format / Black + isort / Pylint |
| Linter (TS) | ESLint + Prettier / Biome (高速) |
| Type checker (Python) | pyright (strict) / mypy |
| Type checker (TS) | tsc strict |
| Test runner (Python) | pytest + pytest-cov / pytest-asyncio |
| Test runner (TS) | Vitest / Jest |
| E2E | Playwright / Cypress |
| coverage tool | pytest-cov / vitest c8 / nyc |
| **monorepo tool (v3 新規)** | **pnpm workspaces / Turborepo / Nx / Lerna (legacy)** |
| **shellcheck (v3 新規)** | shellcheck (lint shell scripts) |

選定後、各ツールが Phase 0 ゲートに組み込まれる:
- pyright → gate #6
- tsc + ESLint → gate #7
- pytest --cov-fail-under=70 → gate #5
- Playwright (UI task) → gate #8 補助

---

## 連携先一覧

| 下流 | このスキルが供給する情報 |
|---|---|
| **functional-breakdown** | tech_stack (DB type / Auth provider) → entities.json の rls_policies の predicate ライブラリ選択 |
| **feature-decomposition** | phase_0_gates.json → Group A の機能 (lint #17-19 / AC validator / pyright/coverage gate / ADR 起票) を生成 |
| **task-decomposition** | phase_0_gates.json + adrs-to-create.json → Group A の T-V3-INFRA-XX タスクを生成 |
| **distributed-dev** | git_strategy + monorepo 構造 → Claude Code 並列セッションの worktree / branch 命名 |
| **integration** | merge gate 8 + retry プロトコル → 統合フェーズの基準 |
| **decision-record** | adrs-to-create.json → 各 ADR の起票委譲 |

---

## 互換性

- v1 (`docs/architecture/2026-05-09_v1/`): freeze。基本構造は維持 (legacy 参照のみ)
- v3 (`docs/architecture/<date>_v3/`): 新規出力先。Phase 0 gate / RLS strategy / 30-50 並列対応 込み
- 既存 ADR (ADR-002 superseded / ADR-010-012): v3 で参照のみ、新規 ADR-013/014/015 が Phase 0 必須
