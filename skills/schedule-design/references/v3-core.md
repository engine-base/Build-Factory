# schedule-design v3 Core Concepts

> 2026-05-15 v3 採用版 (2026-05-16 汎用化)。schedule-design は **Foundation / Backend / UI / Polish phase の 4 段階** + **Sprint = Wave 単位** + **project-defined parallel capacity (Claude Code セッション並列)** + **N CI gate auto-merge** 前提で再設計。phase 名・Wave 数・並列数・gate 数はすべて project-defined で、本ファイルは汎用的な概念のみ定義する。

## なぜ v3 が必要か (汎用)

v1 / v2 では:
- 「外部実装者 N 名」(人数前提) のリソース計画で、並列セッション主体のスケジュールに合わない
- Foundation phase (lint / AC validator / CI gate) を「準備期間」扱いし、Backend phase / UI phase と並列で進めて drift が増殖
- クライアント確認待ちが各フェーズ末に組まれているが、内製 dogfood では確認は Phase ゲート時のみで十分なケースもある
- ガント表が「週次 × 担当」で粒度が荒く、Wave 単位 (数時間) で実行する並列セッションに対応できない

v3 では:
- **Foundation phase = Wave 0 で必ず単独実行** → CI gate 整備済まで他 task を起動しない (機械的 block)
- **Sprint = Wave = ガント横軸** (1 Wave = project-defined parallel capacity × 数時間)
- **完了判定 = N CI gate auto-merge** (gate 数・内容・閾値はすべて project-defined)
- **wave-schedule.json** で Wave 単位の実行プランを出力 → claude-runner / Swarm が読む

## 3-tier AC (汎用)

タスクの受け入れ条件 (AC) は 3 階層に分けて記述する：

| Tier | 名前 | 意味 | 例 (汎用) |
|---|---|---|---|
| 1 | structural | mock / spec との一致 | 「実装が UI mock と差分 0」「screens.json と route 一致」「entity と DB schema 一致」 |
| 2 | functional | EARS 形式の振る舞い | 「When user clicks login, the system shall ...」「If credentials are invalid, the system shall not ...」 |
| 3 | regression | 自動 test / lint / 型 / coverage | 「lint rule X passes」「test coverage ≥ T%」「type check strict pass」 |

各 Tier は CI gate に 1:1 対応し、CI gate 全 pass で auto-merge される。

## Foundation → Backend → UI → Polish フロー

```
Foundation phase (Wave 0)
  ├─ CI/CD pipeline (lint / format / type check / coverage gate)
  ├─ Test infrastructure (pytest / vitest / Playwright 等)
  ├─ Access control framework (RLS / RBAC / policy enforcement)
  ├─ Audit / logging infrastructure
  └─ Pre-flight checklist mechanism
   ↓ Foundation gate passes (mechanical / observable)
Backend phase (Wave 1〜M, per slice / per feature)
  ├─ Data layer (entity / migration / access policy)
  ├─ Service layer (business logic)
  ├─ API layer (REST / GraphQL / gRPC) + OpenAPI / IDL
  ├─ Contract test (Schemathesis / Pact / consumer-driven)
  └─ Backend integration test (access matrix / business logic E2E)
   ↓ Backend gate passes
UI phase (Wave M+1〜N, per slice / per feature)
  ├─ Component implementation (against spec / against mock)
  ├─ State management (data fetching / cache)
  ├─ UI integration test (visual regression / interaction)
  └─ Accessibility check
   ↓ UI gate passes
Polish phase (Wave N+1〜, cross-cutting)
  ├─ Performance optimization
  ├─ Security audit
  ├─ Documentation
  └─ Release readiness
```

**順序保証ルール:**
- Foundation gate 未達のまま Backend phase Wave を起動しない (機械的 block)
- 同一 Slice の UI phase Wave は対応する Backend phase Wave 完了後にのみ起動
- Polish phase は全 Slice の UI phase 完了後

## Vertical Slice

E2E feature 切片 = 1 Slice。1 Slice には Backend (data + service + API) + UI (screen + component) の両方が含まれる。Slice 単位で並列開発し、各 Slice が単独で価値を提供できる状態で完了する。

例:
- Slice 0 = auth + workspace + base schema
- Slice 1 = project + hearing
- Slice 2 = requirement + screen-spec
- ...

(Slice 数・内容は project-defined。例の Slice は profile 参照)

## Wave 単位の並列実行 (汎用)

| 指標 | 値 |
|---|---|
| 並列度 | project-defined (small 1-5 / medium 10-30 / large 30-100 / massive 100+) |
| 1 Wave 実行時間 | 数時間 (project-defined, 例: 2-4 時間) |
| 1 Wave のタスク数 | 並列度と同等 |
| 完了判定 | 全 task が N CI gate auto-merge 済 |
| Wave 切替 | 前 Wave の Foundation 依存 task が全 done でゲート開放 |

### parallel capacity の段階モデル

| 規模 | 並列セッション数 | 想定 project |
|---|---|---|
| small | 1-5 | 個人開発 / プロトタイプ |
| medium | 10-30 | 中小プロジェクト / 受託案件 |
| large | 30-100 | 大規模プロジェクト / 内製 SaaS dogfood |
| massive | 100+ | エンタープライズ / 大規模複数チーム並列 |

並列度は GitHub Actions / Vercel / hosting plan の上限と整合させる必要がある。上限超過すると CI が直列化してスケジュール破綻する。

## file-level mutex / work-package boundary

同一 file への並列 edit を禁止し、task 分解時に **work-package boundary** で file 単位の排他を保証する。boundary 設計は task-decomposition / distributed-dev で行うが、schedule-design は同 Wave 内で boundary が衝突していないかを STEP 3 で検証する。

## pre-flight audit MD

各 task 着手前に audit MD (Markdown) で AC / dependencies / risk を記録。schedule-design は audit MD template が tickets.json から自動生成可能であることを Foundation gate に組み込む。

## CI gate auto-merge (汎用)

各 task の完了判定 = N CI gate 全 pass で **PR を Claude Code が自動 merge**:

```
Claude Code session (1 task)
  ↓ commit + push
GitHub PR
  ↓ CI run (N gate parallel, project-defined)
  ├─ gate: lint (project-defined rule set)
  ├─ gate: AC validator (3-tier schema + EARS form)
  ├─ gate: access control coverage (e.g. RLS verifier)
  ├─ gate: audit MD existence check
  ├─ gate: test coverage ≥ T%
  ├─ gate: type check strict
  ├─ gate: drift detector (mock-impl-diff 等)
  └─ ... (project-defined)
  ↓ 全 pass
auto-merge (mcp__github__merge_pull_request 等)
  ↓ Wave 進行表更新
```

連続 N 失敗 (閾値 project-defined, 例: 3) → human エスカ (Slack / メール通知)。

## Phase gate 機械判定

各 Phase 完了は mechanical / observable な tool で判定する。「準備完了」「ほぼ動く」のような主観的判定は不可。

| Phase | 完了判定例 |
|---|---|
| Foundation | N CI gate 全 green + lint 0 件 + AC validator 動作確認 |
| Backend | 全 Slice の API contract test pass + access control matrix pass + 全 Phase ゲート audit MD 存在 |
| UI | 全 Slice の UI E2E test pass + a11y check pass |
| Polish | release readiness checklist 全 pass |

## drift 修正 task の組み込み

各 Backend phase 以降の Wave で **Group D (drift fix)** タスクを 5-10 件並列実行:

| Group | 役割 | Wave 内割合 |
|---|---|---|
| Group A (Foundation) | gate / validator / template | Foundation phase でのみ |
| Group B (Vertical Slice impl) | data + service + API or screen + component | Backend / UI phase で 70% |
| Group C (Integration test) | E2E + contract | 各 phase で 10% |
| Group D (Drift fix) | drift 検出 lint 違反修正 | Backend phase 以降 20% |

## v3 リスク (汎用)

| リスク ID | リスク | 発生確率 | 対応策 |
|---|---|---|---|
| R-V3-01 | CI gate 連続失敗 (1 task / N+ 回 reject) | 中 | N 回で human エスカ + audit MD で原因記録 |
| R-V3-02 | 並列セッション競合 (同一 file への並列 edit) | 中 | task 分解時に file-level mutex (work-package boundary) |
| R-V3-03 | drift 増殖 (Group D 滞留) | 高 | Backend phase 以降の Wave で常時 20% を drift fix に割当 |
| R-V3-04 | Foundation gate 未達のまま Backend phase 開始 | 高 | Wave 0 完了判定を mechanical gate にし、Wave 1 起動を機械的に block |
| R-V3-05 | CI tier (GitHub Actions / hosting plan) 並列上限超過 | 中 | 並列度を下げる or 有料枠への切替 |
| R-V3-06 | UI phase が Backend phase の API spec 変更で手戻り | 中 | Backend phase 完了後に UI phase Wave を起動 (順序保証) |

## 入力 (上流 skill から pull する内容)

### task-decomposition 出力
- `tickets.json` — 全 task の 3-tier AC + dependencies + status
- `DEPENDENCIES.md` — DAG (Mermaid + 隣接リスト)
- `tasks-overview.md` — Foundation 群 + Vertical Slice の分類

### feature-decomposition 出力
- `DAG.md` — Slice 依存関係
- `phase-mapping.md` — Foundation / Backend / UI / Polish phase マッピング (project-defined naming)

### architecture-design 出力
- `foundation_gates.json` — N CI gate の定義
- `selected-stack.json` — 採用技術 (work-package size に影響)

## 出力 (下流 skill に渡す内容)

| 下流 | このスキルが供給する情報 |
|---|---|
| **distributed-dev** | wave-schedule.json → 各 task の起動順序を決定 |
| **claude-runner / Swarm** | wave-schedule.json + ci_gate_auto_merge 設定 |
| **integration** | Wave 単位完了集計と Phase gate 判定の基礎データ |
| **delivery** | milestones + Phase gate 完了基準 |

## v3 必須出力フィールド

### wave-schedule.json (v3 新規)

```json
{
  "version": "v3",
  "skill": "schedule-design",
  "phases": [
    {
      "phase_id": "foundation",
      "name": "Foundation phase (project-defined naming)",
      "wave_ids": ["W0"],
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "duration_days": 0,
      "completion_gate": "N CI gate 全 pass + drift 0 件",
      "phase_review_required": true
    },
    {
      "phase_id": "backend",
      "name": "Backend phase",
      "wave_ids": ["W1", "W2", "W3"],
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "completion_gate": "全 Slice API contract test pass",
      "phase_review_required": true
    }
  ],
  "waves": [
    {
      "wave_id": "W0",
      "phase_id": "foundation",
      "name": "Foundation: lint / AC validator / CI gate",
      "start_date": "YYYY-MM-DD",
      "end_date": "YYYY-MM-DD",
      "parallel_session_count_target": 10,
      "group_split": {"A": 10, "B": 0, "C": 0, "D": 0},
      "tasks": ["T-FND-01", "T-FND-02"],
      "depends_on_waves": [],
      "completion_criteria": [
        "all N CI gates pass (project-defined gate set)",
        "all lint rules 0 violations",
        "AC validator validates 3-tier schema"
      ]
    }
  ],
  "milestones": [
    {
      "milestone_id": "M0",
      "name": "Foundation phase 完了 / Foundation gate 開放",
      "date": "YYYY-MM-DD",
      "depends_on": ["W0"],
      "type": "phase_gate"
    }
  ],
  "ci_gate_auto_merge": {
    "enabled": true,
    "gates": [
      "lint (project-defined rule set)",
      "AC validator (3-tier schema + EARS form)",
      "access control coverage (e.g. RLS verifier)",
      "audit MD existence",
      "test coverage gate (e.g. >= 70%)",
      "type check (e.g. pyright / tsc strict)",
      "drift detector (e.g. mock-impl-diff)"
    ],
    "consecutive_failure_threshold": 3,
    "human_escalation_after": 3
  }
}
```

## connections (汎用 / project profile で具体化)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **task-decomposition** | tickets.json (3-tier AC) / DEPENDENCIES.md (DAG) |
| **feature-decomposition** | DAG.md / phase-mapping.md (Slice 依存) |
| **architecture-design** | foundation_gates.json (N CI gate) |

| 下流 | このスキルが供給する情報 |
|---|---|
| **distributed-dev** | wave-schedule.json |
| **claude-runner / Swarm** | wave-schedule.json + ci_gate_auto_merge 設定 |
| **integration** | Wave 完了集計と Phase gate 判定基礎データ |
| **delivery** | milestones + Phase gate 完了基準 |

## 互換性

- v1 (旧 schedule.md): freeze
- v3 (新出力): wave-schedule.json + Foundation/Backend/UI/Polish phase + project-defined parallel capacity + CI gate auto-merge を必須化
- project-specific 値はすべて `references/profiles/<project>.md` に分離
