# Build-Factory v3 Phase 1 — テスト計画書

- **対象**: Build-Factory Phase 1 (Backend / UI Vertical Slice / Drift fix)
- **作成日**: 2026-05-16
- **責任者**: 高本まさと (masato@engine-base.com)
- **プロファイル**: `skills/test-verification/references/profiles/build-factory.md`
- **上流入力**:
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-b-backend.json` (30 task)
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part1.json` (25 task)
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-c-ui-part2.json` (30 task)
  - `docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json` (15 task)
- **本フェーズ成果物**:
  - `ears-test-mapping.json` (主成果物 / 100 task × 平均 ~16 AC = **1576 test ID**)
  - `gate-config.yml` (8 必須 gate + 6 任意 gate)
  - `test-plan.md` (本書)
  - `decision-log.json`

---

## 1. テスト戦略 (3-tier AC マッピング思想)

v3 では task-decomposition の **3-tier AC** を test レベルに 1:1 でマッピングする。
これにより「実装した AC が必ず CI で機械検証される」状態を保証する。

| AC tier | 内容 | test レベル | 主 tool | gate (BF profile) |
|---|---|---|---|---|
| **structural** | mock / spec 一致 (data-screen-id / h1 text / data-feature-id) | mock-impl drift lint | `scripts/lint-mock-impl-diff.py --strict` | gate-8-mock-impl-diff (UI) |
| **functional.api** | EARS EVENT-DRIVEN / UNWANTED / STATE-DRIVEN / UBIQUITOUS | unit + contract | `pytest` + `schemathesis` (+ `vitest`) | gate-5-pytest-cov (Backend) |
| **functional.access_control** | role × operation policy | parametrize matrix | `pytest` + `verify-rls-coverage.py` | gate-3-rls-coverage (Backend) |
| **functional.migration** | DB rename / column align (Group D) | migration test | `pytest` + `alembic upgrade/downgrade` | gate-5-pytest-cov (Backend) |
| **regression** | lint / type / coverage / audit MD | CI gate 自動化 | 8 gate (下記) | gate-1..gate-8 |

### EARS form → test 種別 自動変換

`ears-test-mapping.json` 生成時に EARS form を判別し、test 種別を自動付与する:

| EARS form | test 種別 | 例 |
|---|---|---|
| **EVENT-DRIVEN** | 正常系 test | `test_login_valid_credentials_returns_200` |
| **UNWANTED** | 異常系 test | `test_login_invalid_credentials_returns_401` |
| **STATE-DRIVEN** | parametrize test | `@pytest.mark.parametrize("state", [...])` |
| **UBIQUITOUS** | property / invariant test | `@hypothesis.given(...)` (任意) |
| **OPTIONAL** | conditional test | `@pytest.mark.skipif(feature_disabled)` |

### test ID 命名規則

```
<TASK-ID>-<TIER>-<INDEX>
```

例:
- `T-V3-B-01-S1` = task T-V3-B-01 の structural AC #1
- `T-V3-B-01-F2` = task T-V3-B-01 の functional AC #2
- `T-V3-B-01-R3` = task T-V3-B-01 の regression AC #3

---

## 2. mapping 数値サマリ (ears-test-mapping.json から)

| 軸 | 件数 |
|---|---|
| total tasks | 100 |
| total test IDs | **1576** |
| structural | 134 |
| functional | 622 |
| regression | 820 |
| EVENT-DRIVEN | 276 |
| UNWANTED | 293 |
| STATE-DRIVEN | 129 |
| UBIQUITOUS | 874 |
| OPTIONAL | 4 |

> 注: 当初仮見積 (100 task × 8 AC = 800 test ID) に対し実際は ~1576 となった。
> Group B (backend) は task あたり functional 11 件 + regression 11 件と非常に密。
> Group D (drift) は migration / RLS 兼検証で同じく規模が大きい。
> AC を「省略せずに 1:1 mapping」した結果であり、二重カウントではない。

### gate 別 test 数

| gate | test 数 |
|---|---|
| gate-5-pytest-cov | 558 |
| gate-8-mock-impl-diff | 236 |
| gate-3-rls-coverage | 227 |
| gate-1-lint-mock | 217 |
| gate-4-audit-md | 130 |
| gate-2-ac-validator | 115 |
| gate-7-tsc-strict | 56 |
| gate-6-pyright | 37 |

---

## 3. Access control matrix test (6 role × 7 operation = 42 cell 拡張)

### 現状 (Phase 1) — 4 ロール × 7 操作 = 28 cell / entity

build-factory profile の現行マトリクス:

| ロール | SELECT own | SELECT others | INSERT | UPDATE own | UPDATE others | DELETE own | DELETE others |
|---|---|---|---|---|---|---|---|
| owner | OK | OK | OK | OK | OK | OK | OK |
| admin | OK | OK | OK | OK | OK | OK | OK |
| member | OK | NG | OK | OK | NG | OK | NG |
| guest | OK (assigned only) | NG | NG | NG | NG | NG | NG |

### Phase 1.5 拡張 — 6 ロール × 7 操作 = 42 cell / entity

`service_role` (Supabase service-role JWT) と `account_owner` (workspace 横断オーナー)
を追加する。

| ロール | SELECT own | SELECT others | INSERT | UPDATE own | UPDATE others | DELETE own | DELETE others |
|---|---|---|---|---|---|---|---|
| owner | OK | OK | OK | OK | OK | OK | OK |
| admin | OK | OK | OK | OK | OK | OK | OK |
| member | OK | NG | OK | OK | NG | OK | NG |
| guest | OK (assigned only) | NG | NG | NG | NG | NG | NG |
| **service_role** | OK | OK | OK | OK | OK | OK | OK |
| **account_owner** | OK | OK (own account) | OK | OK | OK (own account) | OK | OK (own account) |

entity 数 (43) × 6 × 7 = **1806 cell**。`scripts/verify-rls-coverage.py` で
matrix の網羅率を mechanical 検証する。

### 実装例

```python
@pytest.mark.parametrize(
    "role,operation,expected",
    [
        ("owner",         "select_own",     "OK"),
        ("owner",         "select_others",  "OK"),
        ("admin",         "select_own",     "OK"),
        ("admin",         "delete_others",  "OK"),
        ("member",        "select_others",  "NG"),
        ("member",        "delete_others",  "NG"),
        ("guest",         "insert",         "NG"),
        ("guest",         "select_others",  "NG"),
        ("service_role", "delete_others",   "OK"),
        ("account_owner","update_others",   "OK"),
        # ... 32 more cells per entity
    ],
)
def test_rls_matrix_user(role: str, operation: str, expected: str) -> None:
    ...
```

### gate-3-rls-coverage 実行

```bash
python3 scripts/verify-rls-coverage.py \
  --entities docs/functional-breakdown/2026-05-16_v3/entities.json \
  --roles    docs/functional-breakdown/2026-05-16_v3/roles.json \
  --tests    backend/tests/rls/
```

検証内容:
1. entities.json の policies が全 test に登場するか
2. role × operation matrix が全 entity でカバーされているか
3. expected (OK/NG) が roles.json と一致するか

---

## 4. Contract test (Schemathesis + Pact 採用判断)

### Phase 1A (現在) — 未導入 / 任意

- gate-config.yml で `required: false`
- 既存 backend が安定するまでは pytest unit + integration で代替
- `schemathesis` を CI に組み込むが、warning-only

### Phase 1B Wave 3 — Schemathesis 有効化

- `docs/api-design/2026-05-16_v3/openapi.yaml` を信頼源化
- `schemathesis run --checks all` を gate-backend-contract-schemathesis として
  `required: true` に昇格
- OpenAPI から TS 型を自動生成し、frontend ↔ backend の構造一致を保証

### Phase 1.5 — Pact (consumer/provider)

- frontend (Vitest + pact-js) が consumer pact を生成 → broker
- backend (FastAPI + pact-python) が provider verify
- contract 違反は Backend gate で fail
- broker は self-hosted (Oracle Cloud Free Tier 上) で運用

### 採用判断

| 観点 | Schemathesis | Pact |
|---|---|---|
| 信頼源 | OpenAPI spec | consumer 側の使い方 |
| coverage 種別 | 仕様カバレッジ (fuzz) | 実利用カバレッジ (consumer-driven) |
| Phase 1 採用 | 後半 | Phase 1.5 |
| 主目的 | spec 違反 fuzz 検出 | frontend ↔ backend lockstep |

両方併用がベスト (Schemathesis が "spec通り動くか"、Pact が "consumer が期待通り使えるか")。

---

## 5. Coverage 閾値 (Phase 1 = 70%)

| 区分 | 閾値 |
|---|---|
| 全体 (gate-5-pytest-cov) | **70%** |
| ビジネスロジック / 認証 / データ操作 | 80% 推奨 |
| ユーティリティ / 型変換 | 60% 推奨 |
| 自動生成 (codegen) コード | 除外 |

実行:

```bash
pytest backend/tests/ --cov --cov-fail-under=70
# = bash scripts/check-coverage.sh --gate
```

Phase 1.5 で **75%**、Phase 2 (SaaS 公開) で **80%** に引き上げる。

---

## 6. 失敗 retry プロトコル

```
gate fail
  -> 1st: rerun gate (transient flake 判定)
  -> 2nd: read gate log, patch minimal diff
  -> 3rd: rerun
  -> 連続 3 fail で escalate
       - PR に label `needs-human-review` を付与
       - Slack #engineering 通知
       - masato@engine-base.com にメール通知
```

### retry / merge 判定

- 全 required gate green → `gh pr merge --auto --squash` (auto-merge)
- 1 つでも fail → block (escalate threshold 未達なら retry)
- 連続 3 fail → human escalation

---

## 7. Foundation → Backend → UI → Polish gate 構成

```
gate-foundation
  ├─ gate-1-lint-mock           (required, block_downstream)
  ├─ gate-2-ac-validator        (required, block_downstream)
  ├─ gate-4-audit-md            (required, block_downstream)
  └─ gate-6-pyright             (warning-only Phase 1)
        ↓ pass
gate-backend
  ├─ gate-3-rls-coverage        (required, block_downstream)
  ├─ gate-5-pytest-cov >= 70%   (required, block_downstream)
  ├─ gate-backend-contract-schemathesis  (optional, Phase 1B Wave 3 で required)
  └─ gate-backend-contract-pact          (optional, Phase 1.5 で required)
        ↓ pass
gate-ui
  ├─ gate-7-tsc-strict          (required, block_downstream)
  ├─ gate-8-mock-impl-diff      (required, block_downstream)
  ├─ gate-ui-vitest             (required, block_downstream)
  └─ gate-ui-playwright-e2e     (optional, Phase 1B Wave 3 で required)
        ↓ pass
gate-polish
  ├─ check-phase-gate           (required, block_downstream)
  └─ gate-polish-security-scan  (optional, Phase 1.5 で required)
        ↓ pass
auto-merge: gh pr merge --auto --squash
```

`gate-foundation`/`gate-backend`/`gate-ui`/`gate-polish` の **passed=true** が
全段階で成立した場合のみ `auto-merge` job が起動する (`needs.<job>.outputs.passed == 'true'`)。

---

## 8. 既存実装との関係

- `.github/workflows/ci-v3.yml` を gate-config.yml の **canonical 実装** とする。
- 旧 `.github/workflows/ci.yml` (T-S0-02 期) は v1/v2 期からの保持で残置。Phase 2 で廃止予定。
- `auto-merge.yml` (別 workflow) は ci-v3.yml が完了したことを `workflow_run` で待ち、
  ラベル `auto-merge` 付き PR を squash-merge する。

---

## 9. EARS AC → test 自動生成 script

```bash
python3 scripts/generate-tests-from-ears.py \
  --mapping docs/test-verification/2026-05-16_v3_phase1/ears-test-mapping.json \
  --output  backend/tests/generated/ \
  --framework pytest
```

(Phase 1B で導入予定。Phase 1A は手動で `ears-test-mapping.json` を参照しつつ test を実装する。)

各 test file 冒頭に **`# EARS_AC_ID: T-V3-B-01-F2`** コメントを必須化し、
lint #19 で逆引き検証する。

---

## 10. 質問・判断保留

1. Schemathesis を Wave 3 で required にする際、openapi.yaml の整備工数 → Wave 3 Foundation phase で確保
2. Pact broker 運用 (self-hosted vs SaaS Free) → Phase 1.5 で決定
3. coverage 閾値 70 → 75 → 80 の段階引き上げタイミング → Phase 1.5 開始時に決定

---

## 11. 関連ファイル

- `docs/test-verification/2026-05-16_v3_phase1/ears-test-mapping.json` (1576 test ID mapping)
- `docs/test-verification/2026-05-16_v3_phase1/gate-config.yml` (14 gate)
- `docs/test-verification/2026-05-16_v3_phase1/decision-log.json` (本フェーズ判断ログ)
- `.github/workflows/ci-v3.yml` (実装)
- `skills/test-verification/references/v3-core.md` (skill core)
- `skills/test-verification/references/profiles/build-factory.md` (project profile)
- `docs/decisions/ADR-011-completion-gate.md` (完了判定ゲート)
