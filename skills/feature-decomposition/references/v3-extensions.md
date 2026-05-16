# v3 拡張 — feature-decomposition

> 2026-05-15 v3 から、feature-decomposition の機能オブジェクトと Sprint 構成に **Foundation 先行 / Vertical Slice / Group A-J 命名 / 50 並列 Wave / CI gate 連携 / functional-breakdown pull** を採用。
> ここで定義する内容は、上流の functional-breakdown の 4 JSON を input とし、下流の task-decomposition で tickets に細分化される。

## なぜ v3 拡張が必要か

v1 / v2 では:
- Sprint 構成が汎用的 (Sprint 1-N) で Foundation (lint/CI gate) を後回しにできた → 実装着手後に gate を作る = ザル
- 機能オブジェクトに spec 紐付けが無く、task-decomposition が re-derive する必要があった (情報重複 + drift)
- 並列度が暗黙で「グループ A/B」のような無命名分類 → task-decomposition の Group A-J と整合せず
- 既存実装 drift の入力経路がなく、drift 修正タスクが Sprint に組み込まれなかった

v3 では:
- **Sprint 0 = Foundation = Group A** を必ず最初に固定
- functional-breakdown の 4 JSON を pull して各機能に紐付け
- Group A-J を task-decomposition と共通の語彙で使う
- functional-breakdown の `legacy_drift_notes` を Group D 機能として分離

## Group A-J 分類 (task-decomposition と共通)

| Code | 内容 | Sprint / Wave / Phase |
|---|---|---|
| **A** | Infrastructure (lint #17-19 / 3-tier AC validator / pyright/coverage gate / ADR 起票) | Sprint 0 / Wave 0 / Phase 0 |
| **B** | AUTH 完全実装 (API + middleware + frontend + tests) | Sprint 1 / Wave 1-2 / Phase 1 |
| **C** | DB schema 完成 + RLS policy 全実装 | Sprint 1 / Wave 1 / Phase 1 |
| **D** | 重大 drift 修正 (root画面 / KPI/h1 統一 / 不在 API 実装) | Sprint 1 / Wave 2 / Phase 1 |
| **E** | 未実装画面 (Vertical Slice = 画面+API+test を 1 機能) | Sprint 1-2 / Wave 2 / Phase 1 |
| **F** | 既存画面 REFACTOR (R-1〜R-4 適用) | Sprint 2 / Wave 4 / Phase 1.5 |
| **G** | 確定 gap 修正 | Sprint 1 / Wave 1 / Phase 1 |
| **H** | v1 freeze 宣言 / audit retrofit | Sprint 3 / Wave 5 / Phase 2 |
| **I** | 余剰整理 (dead table / dead router) | Sprint 3 / Wave 6 / Phase 2 |
| **J** | 命名 migration (bf_ prefix 廃止) | Sprint 3 / Wave 6 / Phase 2 |

新規プロジェクトで Group A-J を再利用する場合:
- **Group A (Foundation) は必須** = Sprint 0 で必ず最初に完成
- B-J は対象プロジェクトに合わせて内容を置き換え可 (例: AUTH を使わないプロジェクトでも Group B 枠を確保し別の中核機能を入れる)
- 不要 Group は空にして良いが、code は埋める (連番が崩れない方が下流 task-decomposition で扱いやすい)

## Sprint ↔ Wave ↔ Phase 対応

```
Phase 0 (Infrastructure) ─ Sprint 0 ─ Wave 0 ─ Group A
                                        ↓ (gate 整備完了 → 後続解禁)
Phase 1 (dogfood 必須) ──── Sprint 1 ─ Wave 1 ─ Group C / B-1 / G
                                      Wave 2 ─ Group B-2 / D / E
                                      Wave 3 ─ (validation only)
Phase 1.5 (REFACTOR) ────── Sprint 2 ─ Wave 4 ─ Group F
Phase 2 (公開前完成) ────── Sprint 3 ─ Wave 5 ─ Group H
                                      Wave 6 ─ Group I / J
                                      Wave 7 ─ (final validation)
```

- **Sprint** = 経営/PM 視点の集約単位 (1-2 週間相当)
- **Wave** = Claude Code 並列セッション視点の execution 単位 (1 wave = 30-50 並列で 2-4h)
- **Phase** = リリース判定の境界 (dogfood / public release / cleanup)

## Vertical Slice の定義

v3 では「1 機能 = 画面 + API + test + RLS の bundle」を default とする。

```json
{
  "id": "F-V3-AUTH",
  "name": "認証",
  ...,
  "vertical_slice_components": {
    "screens": ["S-001 login", "S-002 signup", "S-003 password_reset", "S-004 mfa_setup"],
    "api_endpoints": [
      "POST /api/auth/login",
      "POST /api/auth/logout",
      "POST /api/auth/signup",
      "POST /api/auth/password-reset",
      "POST /api/auth/mfa/enroll",
      "POST /api/auth/mfa/verify"
    ],
    "entities": ["E-001 User", "E-038 AuthSession"],
    "rls_policies": ["auth_sessions:user_own_select", "users:self_select", "users:self_update"],
    "tests": ["e2e/auth/login.spec.ts", "backend/tests/test_auth_*.py"],
    "middleware": ["require_auth", "rate_limit"]
  }
}
```

Vertical Slice の利点:
- 1 機能を 1 Claude Code セッション (= 1 PR) で完結できる
- structural + functional + regression の 3-tier AC を 1 commit で満たせる
- レイヤー間 (FE/BE/DB) の境界で wait が発生しない

例外 (Vertical Slice にしない場合):
- Group A (infra) : 単独 task
- Group C-1 (DB schema migration): 1 entity = 1 task (migration 番号で順序保証)
- Group I/J (cleanup/rename): 単独 task

## 機能オブジェクトの v3 拡張フィールド

```json
{
  "id": "F-V3-XXX",
  "name": "機能名",
  "category": "auth | payment | crud | notification | search | admin | infra | cleanup",
  "group": "A | B | C | D | E | F | G | H | I | J",
  "phase": 0 | 1 | 1.5 | 2,
  "sprint": 0 | 1 | 2 | 3,
  "wave": 0 | 1 | 2 | ...,

  // 既存フィールド
  "role": "...",
  "input": [...],
  "output": [...],
  "dependencies": ["F-V3-YYY"],
  "independence": "high | medium | low",
  "difficulty": "easy | medium | hard",
  "estimated_days": 2,
  "risk": "...",

  // v3 新規: functional-breakdown の 4 JSON から pull
  "screen_ids": ["S-001", "S-002"],
  "entity_ids": ["E-001 User"],
  "api_endpoints": [
    {"method": "POST", "path": "/api/auth/login", "auth": "public"}
  ],
  "rls_policies": ["users:self_select"],
  "ears_ac_seed": [
    "EVENT-DRIVEN: When POST /api/auth/login is called ..."
  ],

  // v3 新規: Vertical Slice 定義
  "vertical_slice_components": {
    "screens": [...],
    "api_endpoints": [...],
    "entities": [...],
    "rls_policies": [...],
    "tests": [...]
  },

  // v3 新規: drift 入力 (functional-breakdown の legacy_drift_notes が source)
  "drift_origin": null | {
    "source_screen_id": "S-006",
    "diff_severity": "high",
    "recommendation": "..."
  }
}
```

## CI gate 連携 (8 ゲート)

各機能は task-decomposition で細分化された後、以下 8 ゲート全 pass で merge される:

| # | Gate | 検出する漏れ |
|---|---|---|
| 1 | mock lint (1-19) | 絵文字 / AGPL / mock-impl diff / screens-API / entity-table naming |
| 2 | 3-tier AC validator | AC 形式違反 / EARS 違反 |
| 3 | audit MD validator | generic 文言 / 不在 |
| 4 | RLS coverage | RLS policy 不足 |
| 5 | pytest + coverage | unit test 失敗 / カバレッジ < 70% |
| 6 | pyright strict | Python 型エラー |
| 7 | TypeScript strict | TS 型エラー |
| 8 | mock-impl diff | structural mismatch |

feature-decomposition スキルは、各機能の `vertical_slice_components` が 8 ゲート全部を満たす設計になっているかをチェックする。例えば:
- `screens` が空 → gate #8 mock-impl diff は不要
- `entities` が空 → gate #4 RLS coverage は不要
- `tests` が空 → gate #5 pytest 不可 → **設計失敗**

## functional-breakdown 出力からの pull pattern

STEP 1 で functional-breakdown の 4 JSON path を確認し、pull する:

```
## 入力情報の確認
- functional-breakdown 出力: docs/functional-breakdown/<date>_v<N>/
  - screens.json: N 件
  - features.json: N 件
  - roles.json: R 件
  - entities.json: E 件
  - (任意) addendum.json: 0 or N 件
- drift 検知出力 (legacy_drift_notes): N 件 → Group D 機能候補
```

各機能の v3 拡張フィールドは functional-breakdown 出力から **逐語コピー** する:
- `screen_ids` ← screens.json の id
- `entity_ids` ← entities.json の id
- `api_endpoints` ← features.json の api_endpoints[]
- `rls_policies` ← entities.json の rls_policies[].name
- `ears_ac_seed` ← features.json の ears_ac_seed[]

これにより spec ↔ feature ↔ task の 3 階層が情報的に同期する。

## task-decomposition への引き継ぎ

feature-decomposition の出力 (機能 JSON) を task-decomposition の STEP 1 input にする:

| feature 側 | task 側 |
|---|---|
| `id` | `feature_id` (1 機能 → N task) |
| `group` | task の `group` (継承) |
| `phase / sprint / wave` | task の `phase / wave` (継承) |
| `screen_ids` | task の `screen_ids` (1 機能の screen を tasks に分散) |
| `entity_ids` | task の `entity_ids` |
| `vertical_slice_components.api_endpoints` | task の `files_changed` (backend/routers/...) |
| `vertical_slice_components.tests` | task の `files_changed` (backend/tests/...) |
| `rls_policies` | task の `rls_policies_required` |
| `ears_ac_seed` | task の `acceptance_criteria.functional` |
| `estimated_days` | task の `estimate_hours` の合計目安 (1 day ~= 6-8h) |

task-decomposition は 1 機能を **2-8h 粒度の task** に細分化する (Vertical Slice なら 1 機能 = 1 task で済むこともある)。

## DAG.md output (v3 新規)

STEP 5 で出力する DAG.md は以下の構造:

```markdown
# DAG / Wave Plan — <project>

## 物量
| 指標 | 値 |
|---|---|
| 総機能数 | N |
| Sprint 数 | N |
| Wave 数 | N |
| 並列度上限 | 30-50 |
| 推定総工数 | N 日 |

## Sprint 構成
| Sprint | Phase | Group | 機能数 | Wave |
|---|---|---|---:|---|
| 0 | Infrastructure | A | N | 0 |
| 1 | dogfood 必須 | C/B/D/E/G | N | 1-2 |
| 2 | REFACTOR | F | N | 4 |
| 3 | Cleanup | H/I/J | N | 5-6 |

## 依存 DAG
[Wave 0] Group A 全機能 ─→ [Wave 1] Group B-1/C/G ─→ [Wave 2] Group B-2/D/E ─→ ...

## 並列実行可能グループ (Wave 別)
### Wave 0 (Phase 0)
- F-V3-INFRA-01〜08 (互いに独立 / 8 並列)

### Wave 1 (Phase 1)
- F-V3-AUTH-{login/signup/mfa/oauth/password-reset} 等 (Group B)
- F-V3-DB-{users/accounts/...} 等 (Group C)
...

## Risk flags (Bottleneck 候補)
| 機能 | risk | 影響範囲 | mitigation |
|---|---|---|---|
| F-V3-INFRA-03 (lint #17) | ブロッキング | Wave 1-2 全機能の merge gate | Sprint 0 で必ず最優先完成 / 2 人アサイン |
```

## 互換性

- v1 (`docs/feature-decomposition/2026-05-09_v1/`): freeze。Sprint 0-7 概念は維持 (legacy 参照のみ)
- v3 (`docs/feature-decomposition/<date>_v3/`): 新規出力先 / Group A-J + 30-50 並列 Wave + Vertical Slice
- ローダー (task-decomposition) は v3 を優先 / v1 は legacy 参照のみ
