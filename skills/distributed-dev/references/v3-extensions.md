# v3 拡張 — distributed-dev

> 2026-05-15 v3 から、distributed-dev は **3-tier AC + 8 CI gate + work-package boundary (file mutex) + pre-flight audit MD + wave-schedule.json 連携** を CLAUDE.md に必須埋め込み。30-50 並列 Claude Code セッションの「工場の作業員」運用が前提。

## なぜ v3 拡張が必要か

v1 / v2 では:
- CLAUDE.md にスコープ境界だけが書かれ、3-tier AC が抽象化されて落ちる
- Done Criteria が「動く」レベルで止まり、8 CI gate に対応していない
- work-package boundary が「触らないファイル」リスト止まりで、並列セッションが同 file を edit して conflict 多発
- 事後監査 (audit MD を完了後に書く) で抜けが多発 → pre-flight (着手前) に切替
- wave-schedule.json から Wave ID / 起動順を継承する仕組みがない

v3 では:
- **tickets.json の 3-tier AC を CLAUDE.md に逐語コピー**
- **8 CI gate を Done Criteria に必須記載**
- **file-level mutex** で同一 file への並列 edit を機械的に防ぐ
- **pre-flight audit MD** を着手前に generate → 埋めてから実装開始
- **wave-schedule.json** から Wave ID + depends_on_waves + parallel_session_count を継承

## 入力 (上流出力 pull)

| 上流 | pull する内容 |
|---|---|
| task-decomposition | tickets.json の 1 task entry (3-tier AC + work_package_boundary + dependencies) |
| api-design | ears-ac-seed.json の該当 endpoint AC + openapi.yaml の該当 path |
| functional-breakdown | screens.json (mock_path / h1_text) + entities.json (rls_policies) |
| schedule-design | wave-schedule.json の該当 wave (wave_id / depends_on_waves / parallel_session_count_target) |
| test-verification | gate-config.yml + ears-test-mapping.json (test ID 対応) |

## CLAUDE.md v3 schema

```markdown
# 実装タスク: <task_id> - <title>

## 0. 上流出力 (この task の context を構成する path)
- task: docs/task-decomposition/<date>_v<N>/tickets.json (entry: <task_id>)
- mock: docs/mocks/<date>_v<N>/<screen_id>.html
- api: docs/api-design/<date>_v<N>/openapi.yaml (path: <method> <endpoint>)
- ears_ac_seed: docs/api-design/<date>_v<N>/ears-ac-seed.json (endpoint: <method> <endpoint>)
- entities: docs/functional-breakdown/<date>_v<N>/entities.json (entity: <entity_id>)
- wave: docs/schedule-design/<date>_v<N>/wave-schedule.json (wave_id: <wave_id>)
- pre_flight_audit: docs/audit/<date>_v<N>/<task_id>.md (着手前に埋める)

## 1. Wave / 起動情報
- wave_id: W<N>
- depends_on_waves: [W<N-1>, ...]
- parallel_session_count_target: <N>
- group: <A | B | C | D>

## 2. 実装する内容 (1〜2 文)

## 3. work-package boundary (file mutex)

### 触ってよいファイル (editable)
- backend/routers/auth.py
- backend/services/auth_service.py
- backend/tests/test_auth.py

### 同時編集禁止 (file mutex / Wave 内排他)
- backend/main.py  ← 他 task と共有 (Wave 内で同時 edit 禁止)
- frontend/src/types/api.ts  ← OpenAPI 自動生成、人手 edit 禁止

### 参照のみ (readonly)
- backend/models/user.py
- backend/services/base.py

### 絶対に触らない (forbidden)
- backend/migrations/  ← Phase 0 で確定済
- docs/  ← spec、変更は別 task

## 4. 実装仕様

### EARS AC (api-design ears-ac-seed.json から逐語コピー)
- EVENT-DRIVEN: When POST /api/auth/login is called with valid email+password, the system shall return 200 with { access_token, refresh_token, user_id }.
- UNWANTED: If credentials are invalid, the system shall return 401 with generic message.
- ...

### 型定義 (openapi.yaml から自動生成済)
```typescript
// frontend/src/api/types.ts (auto-generated, do not edit)
export type LoginRequest = { email: string; password: string; mfa_code?: string };
export type LoginResponse = { access_token: string; refresh_token: string; user_id: string; mfa_required: boolean };
```

### 処理フロー
1. ...
2. ...

### RLS policy (entities.json から)
- auth_sessions:user_own_select
- auth_sessions:user_own_insert

## 5. Done Criteria (3-tier AC + 8 CI gate)

### Tier 1: Structural (mock/spec 一致)
- [ ] mock_path (<screen_id>.html) の h1_text / kpi_labels / btn_labels が実装と一致
- [ ] lint #17 mock-impl-diff: 0 件

### Tier 2: Functional (EARS API + RLS)
- [ ] EARS AC seed 全件が test ファイル (ears-test-mapping.json) で実装され pass
- [ ] verify-rls-coverage: 4 ロール × 7 操作 マトリクス pass
- [ ] Schemathesis (OpenAPI fuzz) pass

### Tier 3: Regression (test / lint / type / coverage)
- [ ] pytest --cov --cov-fail-under=70 全 pass
- [ ] pyright strict: 0 error
- [ ] tsc --noEmit strict: 0 error
- [ ] lint-mock.sh: 19 check 全 pass
- [ ] validate-tickets.py: AC schema pass
- [ ] audit MD: pre_flight_audit が埋まり、commit に含まれる

### 8 CI gate auto-merge (v3 必須)
- 全 gate green で `gh pr merge --auto --squash`
- 連続 3 失敗で human エスカ (Slack / メール)

## 6. pre-flight audit MD (着手前に必ず実行)

```bash
# 1. template から audit MD を生成
cp docs/audit/<date>_v<N>/_template.md docs/audit/<date>_v<N>/<task_id>.md

# 2. audit MD を埋める (実装前):
#    - 既存実装を grep して把握
#    - 3-tier AC が現状でどの程度満たされているか記録
#    - 触る予定ファイル一覧と理由
#    - 既知の落とし穴

# 3. commit (pre-flight)
git add docs/audit/<date>_v<N>/<task_id>.md
git commit -m "audit(pre-flight): <task_id>"
```

## 7. 完了報告の形式

Done Criteria の全項目について `✅ 確認済み: <確認方法>` の形式で報告:

```
✅ Tier 1: lint #17 mock-impl-diff 0 件 (scripts/lint-mock-impl-diff.py で確認)
✅ Tier 2: ears-test-mapping.json 6/6 件 pass (pytest backend/tests/generated/)
✅ Tier 2: RLS 4×7 マトリクス pass (verify-rls-coverage)
✅ Tier 3: pytest cov 78% (target 70%)
✅ Tier 3: pyright 0 error / tsc 0 error
✅ Tier 3: audit MD 埋め込み済 (docs/audit/.../T-001-01.md)
```

## 8. 注意事項 (機械的 boundary)

- スコープ外のファイルを変更しない (CI gate で自動検出 → reject)
- 同時編集禁止 file への push は merge conflict 必至 → 先に Wave 内 mutex 取得
- 既存の関数の内部リファクタは forbidden (Phase 1.5 REFACTOR Wave で行う)
- 仕様にない機能の追加は禁止 (どんなに便利でも)
- スコープ外バグ発見時: 修正せず `// TODO(drift): <issue>` でコメント。Group D Wave に流す
```

## work-package boundary (file mutex) の仕組み

### tickets.json での記述

```json
{
  "task_id": "T-001-01",
  "work_package_boundary": {
    "editable": ["backend/routers/auth.py", "backend/services/auth_service.py", "backend/tests/test_auth.py"],
    "shared_no_concurrent_edit": ["backend/main.py", "frontend/src/types/api.ts"],
    "readonly": ["backend/models/user.py"],
    "forbidden": ["backend/migrations/"]
  }
}
```

### Wave 内 mutex 検出

`scripts/check-wave-mutex.py` が Wave 起動時に検出:
- Wave 内の全 task の `shared_no_concurrent_edit` を集約
- 同 file を `editable` に持つ task が複数あれば Wave 起動を block
- 順次実行に切り替え (Wave 分割) or task の boundary を絞り直すよう警告

### 違反検出 (CI gate #1)

`scripts/lint-mock.sh` の lint #16 work-package-boundary が:
- PR diff の変更 file が `editable` の subset であることを検証
- `forbidden` への変更があれば fail
- `shared_no_concurrent_edit` への変更は OK だが警告 (Wave mutex 取得済か確認)

## pre-flight audit MD template

`docs/audit/<date>_v<N>/_template.md`:

```markdown
# audit: <task_id>

## pre-flight (着手前)

### 既存実装の調査
- 関連 file: (grep 結果)
- 既存パターン: (どの file の何関数を参考にするか)
- 落とし穴: (既知の bug / 非互換)

### 3-tier AC の現状評価
- Tier 1 structural: 何% 満たされているか
- Tier 2 functional: 既存 endpoint で何件パスか
- Tier 3 regression: cov / lint / type の現状値

### 触る予定ファイル
| file | 理由 | 変更規模 |
|---|---|---|

### 実装方針
- alternatives: (検討した案)
- chosen: (選定理由)

## post-implementation (完了後 / 任意)

### 実装後の AC pass 状況
- Tier 1/2/3 の最終状態

### drift 発見
- スコープ外で見つけた drift: TODO(drift) として記録した item 一覧
```

## start-cmd.sh / done-cmd.sh

### start-cmd.sh (Wave 起動時に Claude Code が最初に実行)

```bash
#!/bin/bash
set -e

TASK_ID="$1"
DATE="<date>"
VERSION="v3"

# 1. branch を切る (idempotent)
git checkout main
git pull
git checkout -b "claude/${TASK_ID,,}" 2>/dev/null || git checkout "claude/${TASK_ID,,}"

# 2. pre-flight audit MD を生成 (まだ無ければ)
AUDIT_PATH="docs/audit/${DATE}_${VERSION}/${TASK_ID}.md"
if [ ! -f "$AUDIT_PATH" ]; then
  cp "docs/audit/${DATE}_${VERSION}/_template.md" "$AUDIT_PATH"
fi

# 3. Wave mutex check
python3 scripts/check-wave-mutex.py --task "$TASK_ID"

# 4. CLAUDE.md を表示 (Claude Code が読む)
cat ".claude/branches/${TASK_ID}.md"
```

### done-cmd.sh (Done Criteria を全て CI で検証)

```bash
#!/bin/bash
set -e

TASK_ID="$1"

# 1. all 8 gates
bash scripts/lint-mock.sh
python3 scripts/validate-tickets.py
python3 scripts/verify-rls-coverage.py
bash scripts/audit-md-check.sh
pytest --cov --cov-fail-under=70
pyright
tsc --noEmit
python3 scripts/lint-mock-impl-diff.py

# 2. work-package boundary check
python3 scripts/check-work-package-boundary.py --task "$TASK_ID"

# 3. push + create PR
git push -u origin HEAD
mcp__github__create_pull_request --base main --head "claude/${TASK_ID,,}" --title "feat(${TASK_ID}): ..."

# 4. auto-merge (gate 全 pass 後)
# (GitHub Actions が auto-merge)
```

## connections (連携先)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **task-decomposition** | tickets.json の 1 task entry (3-tier AC + work_package_boundary) |
| **api-design** | ears-ac-seed.json + openapi.yaml |
| **functional-breakdown** | screens.json + entities.json + roles.json |
| **schedule-design** | wave-schedule.json (Wave ID + depends_on_waves) |
| **test-verification** | gate-config.yml + ears-test-mapping.json |

| 下流 | このスキルが供給する情報 |
|---|---|
| **Claude Code セッション (1 task ごと)** | CLAUDE.md + start-cmd.sh + done-cmd.sh |
| **integration** | branch-package.json (どのブランチを統合するか) |
| **CI runner** | done-cmd.sh の 8 gate 実行プラン |

## 互換性

- v1: freeze
- v3 (新出力): 3-tier AC 埋め込み + 8 gate auto-merge + file-level mutex + pre-flight audit MD + Wave 連携
