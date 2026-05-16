# v3 Task Object スキーマ

> task-decomposition スキルが生成する各タスクの JSON object 必須/任意フィールド
> source of truth: `docs/task-decomposition/2026-05-15_v3/ACCEPTANCE_CRITERIA_SCHEMA.md` + `tickets.json` 実例

## 必須フィールド

```json
{
  "id": "T-V3-AUTH-01",
  "title": "POST /api/auth/login endpoint",
  "category": "backend",
  "label": "NEW",
  "feature_id": "F-001",
  "screen_ids": ["S-001"],
  "entity_ids": ["E-001 User", "E-038 AuthSession"],
  "legacy_task_id": "T-001-XX",
  "phase": 1,
  "wave": 1,
  "group": "B",
  "estimate_hours": 6,
  "estimate_sessions": 1,
  "depends_on": ["T-V3-INFRA-01"],
  "files_changed": ["backend/routers/auth.py (new)", "backend/services/auth_service.py (new)"],
  "acceptance_criteria": {
    "structural": [],
    "functional": ["EVENT-DRIVEN: ...", "UNWANTED: ..."],
    "regression": ["pytest test_T-V3-AUTH-01.py PASS", "pyright strict 0 errors", "coverage >= 70%"]
  },
  "rls_policies_required": ["accounts:account_owner_select"],
  "spec_links": ["docs/decisions/ADR-013-auth-strategy.md"],
  "audit_md_path": "docs/audit/2026-05-15_v3/T-V3-AUTH-01.md"
}
```

## フィールド定義

### id (string, 必須)
パターン: `T-V3-<GROUP_CODE>-<NN>` (例: `T-V3-AUTH-01`, `T-V3-RLS-12`, `T-V3-DRIFT-03`, `T-V3-FIX-04`)

### title (string, 必須)
タスクの何をする/何ができれば終わるかを動詞+目的語で。
- 良: `POST /api/auth/login endpoint`
- 悪: `auth 関連の実装`

### category (string, 必須)
列挙値: `backend` | `frontend` | `db` | `test` | `infra` | `cleanup`

### label (string, 必須)
列挙値:
- `NEW`: 既存実装なし、ゼロから書く
- `REFACTOR`: 既存実装あり、v3 規約 (3-tier AC / RLS / strict 型) に書き直す
- `REUSE`: 既存実装そのまま流用 (verify のみ)
- `ARCHIVE`: 削除予定
- `FIX`: v1 で確定 gap として判定済

### feature_id (string, 必須)
`functional-breakdown/features.json` の feature ID と一致。

### screen_ids (string[], 必須 if frontend)
`functional-breakdown/screens.json` の screen ID 配列。

### entity_ids (string[], 任意)
`functional-breakdown/entities.json` の entity ID + 名前のペア。

### legacy_task_id (string | null, 必須)
v1 (`docs/task-decomposition/2026-05-09_v1/tickets.json`) の対応 ID。新規なら `null`。

### phase (int, 必須)
- `0`: Infrastructure (gate 整備)
- `1`: Phase 1 dogfood 必須
- `2`: 公開前完成

### wave (int, 必須)
依存 DAG ベースの実行 wave (0 から)。

### group (string, 必須)
Group code (A〜J, 後述)。

### estimate_hours (number, 必須)
1 タスクで完了する時間。**目安: 2〜8 時間** (これより大きい場合は分割を検討)。

### estimate_sessions (int, 必須)
Claude Code セッション換算 (= ceil(estimate_hours / 4))。

### depends_on (string[], 必須)
このタスクが着手可能になる前に完了が必要な task id 配列。空配列 `[]` も許可。

### files_changed (string[], 必須)
作成/変更/削除予定のファイル。サフィックスで明示:
- `(new)`: 新規作成
- `(modify)`: 既存改修
- `(delete)`: 削除

### acceptance_criteria (object, 必須)
3-tier AC (`references/3-tier-ac-schema.md` 参照)。

### rls_policies_required (string[], 必須 if entity_ids あり)
パターン: `<table>:<policy_name>` (例: `accounts:account_owner_select`)

### spec_links (string[], 必須)
ADR / 仕様書 / mock のパス配列。最低 1 件必須。

### audit_md_path (string, 必須)
`docs/audit/<date>_v<N>/<task_id>.md` を **着手前に template から生成**。

## Group コード (A〜J)

| Code | 内容 | Phase |
|---|---|:---:|
| **A** | Infrastructure (lint #17-19 / AC validator / pyright / coverage gate / ADR 起票) | 0 |
| **B** | AUTH 完全実装 (API + middleware + frontend + tests) | 1 |
| **C** | DB schema 完成 + RLS policy 全実装 | 1 |
| **D** | 重大 drift 修正 (root画面 / KPI/h1 統一 / 不在 API 実装) | 1 |
| **E** | 未実装画面 (Vertical Slice = 画面+API+test を 1 タスク) | 1 |
| **F** | 既存画面 REFACTOR (R-1〜R-4 適用) | 1.5 |
| **G** | 確定 gap 修正 | 1 |
| **H** | v1 freeze 宣言 / audit retrofit | 2 |
| **I** | 余剰整理 (dead table / dead router) | 2 |
| **J** | 命名 migration (bf_ prefix 廃止) | 2 |

新規プロジェクトで Group A-J を再利用する場合は **Group code を保持し、内容は対象プロジェクトに置き換える** こと (例: AUTH を使わないプロジェクトでも Group B 枠を確保し、Group A の Infrastructure を必ず先行させる)。

## サンプル (Group 別)

### Group A (Infrastructure)
```json
{
  "id": "T-V3-INFRA-03",
  "title": "lint-mock-impl-diff.sh (lint #17) 実装",
  "category": "infra",
  "label": "NEW",
  "phase": 0,
  "wave": 0,
  "group": "A",
  "estimate_hours": 4,
  "depends_on": [],
  "files_changed": ["scripts/lint-mock-impl-diff.sh (new)"],
  "acceptance_criteria": {
    "structural": [],
    "functional": [
      "EVENT-DRIVEN: When lint-mock-impl-diff.sh is run with a screen_id argument, the system shall compare mock HTML h1/KPI/section-h2 with impl page.tsx and exit 0 on full match, 1 on any diff.",
      "UNWANTED: If the mock h1 text does not appear in impl page.tsx, the system shall print a diff line and exit 1."
    ],
    "regression": [
      "The system shall pass bats tests for: 3 fixtures of matched mock-impl, 3 fixtures of intentional drift.",
      "shellcheck PASS on lint-mock-impl-diff.sh."
    ]
  },
  "spec_links": ["docs/task-decomposition/2026-05-15_v3/ACCEPTANCE_CRITERIA_SCHEMA.md#tier-1-structural"],
  "audit_md_path": "docs/audit/2026-05-15_v3/T-V3-INFRA-03.md"
}
```

### Group B (AUTH backend + frontend = Vertical Slice)
```json
{
  "id": "T-V3-AUTH-01",
  "title": "POST /api/auth/login endpoint + S-001 login page",
  "category": "backend",
  "label": "NEW",
  "feature_id": "F-001",
  "screen_ids": ["S-001"],
  "entity_ids": ["E-001 User", "E-038 AuthSession"],
  "phase": 1,
  "wave": 1,
  "group": "B",
  "estimate_hours": 6,
  "depends_on": ["T-V3-INFRA-01", "T-V3-INFRA-06"],
  "files_changed": [
    "backend/routers/auth.py (new)",
    "backend/services/auth_service.py (new)",
    "frontend/app/login/page.tsx (new)",
    "backend/tests/test_T-V3-AUTH-01.py (new)"
  ],
  "acceptance_criteria": {
    "structural": [
      "STATE-DRIVEN: While /login is rendered, the system shall display an h1 with exact text matching docs/mocks/2026-05-15_v3/auth/S-001-login.html h1."
    ],
    "functional": [
      "EVENT-DRIVEN: When POST /api/auth/login is called with valid email+password, the system shall return 200 with JSON containing { access_token, refresh_token, user_id }.",
      "UNWANTED: If credentials are invalid, the system shall return 401 with generic message (no user enumeration).",
      "EVENT-DRIVEN: When 5 failed login attempts occur within 15 min for the same IP, the system shall return 429 (rate-limited)."
    ],
    "regression": [
      "pytest backend/tests/test_T-V3-AUTH-01.py shall pass >= 8 test cases.",
      "pyright strict 0 errors on backend/routers/auth.py + services/auth_service.py.",
      "coverage >= 70% on touched files."
    ]
  },
  "rls_policies_required": ["auth_sessions:user_own_select"],
  "spec_links": ["docs/decisions/ADR-013-auth-strategy.md"],
  "audit_md_path": "docs/audit/2026-05-15_v3/T-V3-AUTH-01.md"
}
```
