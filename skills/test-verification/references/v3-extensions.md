# v3 拡張 — test-verification

> 2026-05-15 v3 から、test-verification は **3-tier AC を test レベルに 1:1 マッピング** + **EARS AC から test 自動生成** + **8 CI gate 必須** + **RLS 4 ロール × OK/NG マトリクス** + **Schemathesis/Pact contract test** を組み込む。

## なぜ v3 拡張が必要か

v1 / v2 では:
- 「リスク高い箇所を重点的に」の方針で test 配分を決めるため、AC との対応が手作業
- EARS 形式 AC があっても test に翻訳する手順が定義されていない
- RLS policy が test 漏れ (4 ロール × CRUD × OK/NG マトリクスが網羅されない)
- mock ↔ 実装の drift が CI で検出されないため、Phase 1 中に drift が蓄積
- 「CI が green」と「8 gate 全 pass」の差分が言語化されていない

v3 では:
- **task-decomposition の 3-tier AC (structural/functional/regression) を test レベルに直接マッピング**
- **EARS AC から自動的に test case 生成** (EVENT-DRIVEN → 正常系 / UNWANTED → 異常系)
- **8 CI gate を明示的に設定** し、Auto-merge の判定基準を統一
- **verify-rls-coverage** で 4 ロール × OK/NG マトリクスを必ずカバー
- **Schemathesis (OpenAPI fuzz) + Pact** で frontend ↔ backend contract を回帰検証

## 入力 (上流出力 pull)

### task-decomposition 出力
- `tickets.json` — 全 task の 3-tier AC
  - `structural` (mock/spec 一致) → test レベル: lint #17 mock-impl-diff
  - `functional` (EARS API/RLS) → test レベル: unit + contract + integration
  - `regression` (test/lint/pyright/coverage) → test レベル: CI gate 自動化

### api-design 出力
- `openapi.yaml` — Schemathesis input
- `ears-ac-seed.json` — EARS AC → test case 変換ソース
- `lint-mapping.json` — lint #18 screens-API 検証対象

### functional-breakdown 出力
- `entities.json` — RLS policy 定義 (4 ロール × CRUD)
- `roles.json` — owner / admin / member / guest

## 3-tier AC ↔ test レベル 1:1 マッピング

| 3-tier AC | test レベル | tool | gate |
|---|---|---|---|
| **structural** (mock/spec 一致) | lint #17 mock-impl-diff | `scripts/lint-mock-impl-diff.py` | gate #8 |
| **functional.api** (EARS EVENT-DRIVEN / UNWANTED) | unit test + contract test (Schemathesis) | pytest / Schemathesis | gate #5 + #6 |
| **functional.rls** (4 ロール × CRUD × OK/NG) | RLS test (verify-rls-coverage) | pytest + supabase test | gate #3 |
| **functional.acceptance** (E2E ユーザーフロー) | E2E (Playwright) | Playwright | gate #5 |
| **regression.coverage** (pytest cov ≥70%) | coverage check | pytest-cov | gate #5 |
| **regression.lint** (lint #1-19 0 件) | mock-lint + AC validator | lint-mock.sh + validate-tickets.py | gate #1 + #2 |
| **regression.type** (pyright/tsc strict) | type check | pyright + tsc | gate #6 + #7 |
| **regression.audit** (audit MD existence) | audit MD lint | audit-md-check.sh | gate #4 |

## EARS AC → test case 自動生成

### 変換ルール

```
EVENT-DRIVEN: When [event], the system shall [expected].
  ↓
def test_<endpoint>_<event_short>():
    # Arrange: setup [event] preconditions
    # Act: trigger [event]
    response = client.<method>(<path>, ...)
    # Assert: [expected]
    assert response.status_code == <2xx>
    assert response.json() == <expected_body>
```

```
UNWANTED: If [condition], the system shall [reject].
  ↓
def test_<endpoint>_<condition_short>_rejected():
    # Arrange: setup [condition]
    # Act: trigger
    response = client.<method>(<path>, ...)
    # Assert: rejection
    assert response.status_code == <4xx>
    assert response.json()["error"] == "<code>"
```

```
STATE-DRIVEN: While [state], the system shall [behavior].
  ↓
@pytest.mark.parametrize("state", [True, False])
def test_<endpoint>_state_<state>():
    # Arrange: set state
    # Act + Assert: behavior differs by state
```

### 自動生成 script: `scripts/generate-tests-from-ears.py`

```bash
python3 scripts/generate-tests-from-ears.py \
  --ears-ac-seed docs/api-design/<date>_v3/ears-ac-seed.json \
  --output backend/tests/generated/ \
  --framework pytest
```

出力例:
```
backend/tests/generated/
├── test_auth_login.py
├── test_auth_logout.py
├── test_auth_signup.py
└── test_auth_mfa_verify.py
```

各 file に `ears_ac_id` コメントで AC 由来を記録 (lint #19 で逆引き検証)。

## verify-rls-coverage: 4 ロール × OK/NG マトリクス

### マトリクス定義 (Build-Factory 標準 4 ロール)

| ロール | SELECT own | SELECT others | INSERT | UPDATE own | UPDATE others | DELETE own | DELETE others |
|---|---|---|---|---|---|---|---|
| owner | OK | OK (admin) | OK | OK | OK | OK | OK |
| admin | OK | OK | OK | OK | OK | OK | OK |
| member | OK | NG | OK | OK | NG | OK | NG |
| guest | OK (assigned only) | NG | NG | NG | NG | NG | NG |

### テスト生成

各 entity (E-001 User / E-002 Workspace 等) × 4 ロール × 7 操作 = 28 test case (entity 1 件あたり)。

```python
@pytest.mark.parametrize("role,operation,expected", [
    ("owner", "select_own", "OK"),
    ("owner", "select_others", "OK"),
    ("member", "select_others", "NG"),
    ("member", "delete_others", "NG"),
    # ...
])
def test_rls_<entity>_role_matrix(role, operation, expected):
    # ...
```

### CI gate #3 (RLS coverage)

```bash
python3 scripts/verify-rls-coverage.py \
  --entities docs/functional-breakdown/<date>_v3/entities.json \
  --roles docs/functional-breakdown/<date>_v3/roles.json \
  --tests backend/tests/rls/
```

検証内容:
- entities.json の rls_policies が全 test に登場するか
- 4 ロール × 7 操作 マトリクスが全 entity でカバーされているか
- expected 値 (OK/NG) が roles.json の rls_predicate_expr と一致するか

## 8 CI gate 仕様

| Gate | 名前 | tool | 失敗条件 |
|---|---|---|---|
| #1 | lint-mock | `scripts/lint-mock.sh` | 19 check のいずれか violation |
| #2 | AC validator | `scripts/validate-tickets.py` | 3-tier AC schema 違反 or EARS 形式違反 |
| #3 | RLS coverage | `scripts/verify-rls-coverage.py` | 4 ロール × 7 操作 マトリクス未網羅 |
| #4 | audit MD existence | `scripts/audit-md-check.sh` | 該当 task の audit MD が存在しない |
| #5 | pytest cov | `pytest --cov` | カバレッジ <70% or test failure |
| #6 | pyright strict | `pyright` | type error |
| #7 | tsc strict | `tsc --noEmit` | type error |
| #8 | mock-impl-diff | `scripts/lint-mock-impl-diff.py` | mock の項目が backend response に存在しない |

### gate-config.yml (GitHub Actions)

```yaml
name: 8 CI Gate
on: [pull_request]

jobs:
  gate-1-lint-mock:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/lint-mock.sh

  gate-2-ac-validator:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 scripts/validate-tickets.py

  gate-3-rls-coverage:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
    steps:
      - uses: actions/checkout@v4
      - run: python3 scripts/verify-rls-coverage.py

  gate-4-audit-md:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: bash scripts/audit-md-check.sh

  gate-5-pytest-cov:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pytest --cov --cov-fail-under=70

  gate-6-pyright:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: pyright

  gate-7-tsc:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: tsc --noEmit

  gate-8-mock-impl-diff:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: python3 scripts/lint-mock-impl-diff.py

  auto-merge:
    needs: [gate-1-lint-mock, gate-2-ac-validator, gate-3-rls-coverage, gate-4-audit-md, gate-5-pytest-cov, gate-6-pyright, gate-7-tsc, gate-8-mock-impl-diff]
    runs-on: ubuntu-latest
    steps:
      - name: Auto-merge PR
        run: gh pr merge --auto --squash
```

## Contract test (Schemathesis + Pact)

### Schemathesis (OpenAPI → fuzz)

api-design 出力の `openapi.yaml` を入力に property-based test を自動生成:

```bash
schemathesis run openapi.yaml \
  --base-url http://localhost:8000 \
  --checks all \
  --hypothesis-database :memory:
```

### Pact (frontend ↔ backend contract)

- frontend が consumer pact を生成 → broker に push
- backend (provider) が pact verify CI で検証
- contract 違反は CI gate #5 で fail

## ears-test-mapping.json (v3 新規出力)

```json
{
  "version": "v3",
  "skill": "test-verification",
  "mappings": [
    {
      "ears_ac_id": "F-001-AC-01",
      "ears_form": "EVENT-DRIVEN",
      "ears_text": "When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.",
      "test_id": "TC-001",
      "test_file": "backend/tests/generated/test_auth_login.py",
      "test_function": "test_auth_login_valid_credentials",
      "test_level": "unit+contract",
      "gate": "gate-5-pytest-cov"
    },
    {
      "ears_ac_id": "F-001-AC-02",
      "ears_form": "UNWANTED",
      "ears_text": "If credentials are invalid, the system shall return 401 with generic message (no user enumeration).",
      "test_id": "TC-002",
      "test_file": "backend/tests/generated/test_auth_login.py",
      "test_function": "test_auth_login_invalid_credentials_rejected",
      "test_level": "unit+contract",
      "gate": "gate-5-pytest-cov"
    }
  ]
}
```

## connections (連携先)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **task-decomposition** | tickets.json (3-tier AC) |
| **api-design** | openapi.yaml / ears-ac-seed.json / lint-mapping.json |
| **functional-breakdown** | entities.json (RLS policy) / roles.json |
| **architecture-design** | phase_0_gates.json (8 gate 定義) |

| 下流 | このスキルが供給する情報 |
|---|---|
| **distributed-dev** | gate-config.yml → ブランチ実装パッケージに含める |
| **integration** | 8 CI gate auto-merge 仕様 |
| **CI runner (GitHub Actions)** | gate-config.yml をそのまま使用 |

## 互換性

- v1: freeze
- v3 (新出力): 3-tier AC マッピング + EARS 自動生成 + 8 CI gate + RLS マトリクス + Schemathesis/Pact 必須
