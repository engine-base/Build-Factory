# v3 Core Concepts — integration

> integration スキルを v3 で再設計するための汎用コア概念。プロジェクト固有の値 (script path / phase 名 / 並列数 / lint 番号 / drift fix group 名 等) は `references/profiles/<project>.md` に分離する。本ファイルには **完全汎用** の概念のみ。

## なぜ v3 か (汎用)

v1 / v2 では:
- 数本〜10 本程度のブランチを手動順序付けでマージする想定 → N 並列 (project-defined capacity) の Wave 構成に対応できない
- conflict は「発生したら解決する」前提 → file mutex で事前防止する仕組みがない
- Phase ゲート判定が「リリース判断」レベルで止まり、Foundation completion / Backend completion / UI completion の段階で機械判定する基準がない
- drift 検出時の対応 (どこに流すか) が定義されていない
- rollback がブランチ単位の reset → 並列セッションに対応できない

v3 では:
- **Wave 完了時の集計** が integration の主タスク (個別マージは auto-merge 済)
- **work-package boundary (file mutex)** で conflict を事前防止 → 発生は仕様違反として原因記録
- **Phase gate 判定** は **Foundation completion → Backend completion → UI completion → Polish completion** の段階で mechanical / observable な条件で機械判定
- **drift は drift fix queue (project-defined group naming)** に流す (修正タスクを `<drift_ticket_generator>` で自動生成)
- **rollback は PR revert** (task 単位) + drift fix queue 再起動

## 3-tier AC (上流 task-decomposition から継承)

各 task は以下 3 層の受け入れ条件を持つ:
- **structural**: mock / spec 一致 (UI / DB schema / API path)
- **functional**: EARS 5 形式 AC (UBIQUITOUS / EVENT / STATE / OPTIONAL / UNWANTED)
- **regression**: test / lint / type check / coverage

integration では各 PR が 3-tier AC 全てを test レベルで満たした上で N CI gate (project-defined) を通過し auto-merge される前提。

## Foundation → Backend → UI → Polish フロー (汎用 phase transition)

```
Foundation phase (基盤整備)
  ├─ CI/CD pipeline (lint / format / type check / coverage gate)
  ├─ Test infrastructure (unit / integration / E2E runner)
  ├─ Access control framework (RLS / RBAC)
  ├─ Audit / logging infrastructure
  └─ Pre-flight audit MD mechanism

   ↓ Foundation completion gate (mechanical)

Backend phase (per slice)
  ├─ Data layer (entity / migration / access control policy)
  ├─ Service layer (business logic)
  ├─ API layer (REST / GraphQL / gRPC)
  ├─ Contract test
  └─ Backend integration test

   ↓ Backend completion gate (mechanical)

UI phase (per slice)
  ├─ Component implementation
  ├─ State management
  ├─ UI integration test
  └─ Accessibility check

   ↓ UI completion gate (mechanical)

Polish phase (cross-cutting)
  ├─ Performance optimization
  ├─ Security audit
  ├─ Documentation
  └─ Release readiness

   ↓ Release gate (human + mechanical hybrid)
```

各 Phase 移行は次の **Phase gate 機械判定** に従う。

## Vertical Slice (上流から継承)

各 Wave 内の Backend / UI deliverable は単一 feature を E2E で完結する縦切片。integration では「Vertical Slice 単位で Backend → UI の順に merge され、UI completion gate 後に次の Phase に進む」前提で Wave 集計を行う。

## Wave 並列実行 (汎用)

Wave とは「N 並列セッションが同時に走る単位」。1 Wave = project-defined 時間 × N 並列。各 Wave 内で次の 4 カテゴリの deliverable が混在:
- Foundation deliverable (Foundation phase のみ)
- Backend deliverable
- UI deliverable
- Polish deliverable
- Drift fix queue (前 Wave から流れた修正)

Wave 単位の集計が integration スキルの主軸。

## file-level mutex / work-package boundary

各 task は `editable_files` (排他編集 file pattern) と `shared_no_concurrent_edit` (同 Wave 内で他 task と被ったら中断) を持つ。Wave 起動前に `<mutex_checker>` で衝突 0 を確認する前提。conflict 発生 = この検査の漏れ = v3 仕様違反。

## pre-flight audit MD (上流から継承)

各 task は実装着手前に audit MD を埋める。integration では「pre-flight audit MD が存在しない PR は auto-merge 対象外」の運用。

## CI gate auto-merge

各 task は N CI gate (project-defined) 全 pass で `gh pr merge --auto --squash` により機械的に merge される。連続 N 失敗で human エスカ (project-defined retry threshold)。

## Phase gate 機械判定 (Foundation/Backend/UI/Polish completion)

| Phase 移行 | 判定基準 (汎用) | tool (project-defined) |
|---|---|---|
| **Foundation completion → Backend phase** | N CI gate 全 green + lint 違反 0 件 + AC validator pass + access control framework 稼働 | `<phase_gate_checker> --phase foundation` |
| **Backend completion → UI phase** | Backend slice 全 merge + contract test pass + access control matrix pass | `<phase_gate_checker> --phase backend` |
| **UI completion → Polish phase** | UI slice 全 merge + visual regression pass + a11y check pass + drift 累積 0 | `<phase_gate_checker> --phase ui` |
| **Polish completion → Release** | performance budget 内 + security audit pass + SLA target 達成 + docs ready | `<release_readiness_checker>` |

各 tool は exit code 0 で OPEN_GATE / 非 0 で BLOCKED を返す。中間状態 (PENDING) は「criteria の一部が未評価」の場合のみ。

## 入力 (上流出力 pull)

| 上流 | pull する内容 |
|---|---|
| distributed-dev | 管理 JSON 群 (各 task の branch-package.json) — 全 N 件の status |
| schedule-design | wave-schedule.json — phases / waves / milestones / critical_path |
| test-verification | gate-config.yml + ears-test-mapping.json |
| GitHub | PR list + auto-merge 状態 + CI status |

## 主軸 1: Wave 完了集計

### Wave 完了レポート (wave-integration-report.md) スキーマ

```markdown
# Wave Integration Report: W<N>

## 概要
- wave_id: W<N>
- phase_id: <project-defined>
- 期間: YYYY-MM-DD 〜 YYYY-MM-DD
- 並列セッション数: <N>
- task 件数: <N>
- カテゴリ内訳: Foundation=<N> / Backend=<N> / UI=<N> / Polish=<N> / Drift fix=<N>

## auto-merge 集計 (4 カテゴリ × deliverable category)
| 状態 | Foundation | Backend | UI | Polish | Drift fix | 合計 |
|------|-----------|---------|----|----|--------|-----|
| auto-merged (N gate green) | <N> | <N> | <N> | <N> | <N> | <N> |
| retried (1 〜 2 失敗で recovery) | <N> | <N> | <N> | <N> | <N> | <N> |
| escalated (連続 N 失敗 → human) | <N> | <N> | <N> | <N> | <N> | <N> |
| rolled back (post-merge 問題) | <N> | <N> | <N> | <N> | <N> | <N> |

## 連続失敗の原因分析
- T-XXX-XX: gate #<N> <gate_name> N 連続失敗 → boundary 設計に <root cause> があった
  - 対応: pre-flight audit MD に追記、distributed-dev で再起動

## drift 検出 (drift fix queue 行き)
| rule_id | 件数 | 修正 task |
|---------|------|----------|
| <rule_id_1> | <N> | T-DRIFT-W<N>-01〜0N |
| <rule_id_2> | <N> | T-DRIFT-W<N>-0N |

→ 次 Wave (W<N+1>) の drift fix queue (project-defined group naming) に追加。

## 統合先 git state
- main ahead: <N> commit
- main HEAD: <sha>
- backend test cov: <%>
- frontend type check: 0 error
- 全 N gate (project-defined): green
```

### 集計の自動化

```bash
<wave_integration_reporter> \
  --wave-id W<N> \
  --branch-packages <branch_packages_glob> \
  --gh-prs "<pr_branch_pattern>" \
  --output <wave_integration_report_path>
```

## 主軸 2: Phase gate 開放判定

### phase-gate-decision.json スキーマ (汎用)

```json
{
  "version": "v3",
  "skill": "integration",
  "decisions": [
    {
      "phase_transition": "Foundation completion → Backend phase",
      "evaluated_at": "YYYY-MM-DDTHH:MM:SSZ",
      "criteria": [
        {"name": "N CI gate", "status": "green", "evidence": "all gates passed for last N commits"},
        {"name": "lint", "status": "0 violations", "evidence": "<lint_runner> exit 0"},
        {"name": "AC validator", "status": "pass", "evidence": "<ac_validator> exit 0"}
      ],
      "decision": "OPEN_GATE",
      "block_release_until": null,
      "next_wave": "W<N+1>",
      "approver": "automated (mechanical gate)"
    },
    {
      "phase_transition": "Backend completion → UI phase",
      "evaluated_at": null,
      "criteria": [],
      "decision": "PENDING",
      "block_release_until": "<remaining work description>",
      "next_wave": "W<N+M>",
      "approver": null
    }
  ]
}
```

`decision` は `OPEN_GATE` / `PENDING` / `BLOCKED` の 3 値:
- **OPEN_GATE**: 全 criteria green / 次 Phase へ進行可
- **PENDING**: 一部 criteria 未評価 / 評価待ち
- **BLOCKED**: 1 件以上の criteria red / `block_release_until` に残課題

## 主軸 3: drift fix → drift fix queue 流し込み

### drift 検出フロー (汎用)

```
W<N> 完了集計 (<wave_integration_reporter>)
  ↓ lint 違反検出 (project-defined rule_ids)
drift 修正 task を自動生成 (T-DRIFT-W<N>-<seq>)
  ↓ tickets schema に追加
W<N+1> の drift fix queue (project-defined group naming) 候補リストに追加
  ↓ schedule-design.wave-schedule.json 更新
W<N+1> 起動時に drift fix group 割当 (project-defined %) を確保
```

### drift task の自動生成

```bash
<drift_ticket_generator> \
  --report <wave_integration_report_path> \
  --output <drift_tickets_output_path> \
  --target-wave W<N+1>
```

各 drift task は 3-tier AC を持つ通常 task と同じ schema。`task_id: T-DRIFT-W<N>-<seq>` で識別。

## 主軸 4: conflict 発生時の原因追跡

v3 では work-package boundary (file mutex) で conflict が事前防止される前提。発生時は仕様違反として原因記録:

### conflict 発生時のフロー (汎用)

```
PR merge 時に conflict 検出
  ↓
1. <mutex_checker> の漏れ調査
   - 同 Wave 内に同一 file への editable task が複数 ない か
   - shared_no_concurrent_edit の宣言漏れ ない か
2. boundary 設計修正 (tickets schema の work_package_boundary 更新)
3. 該当 task を revert
4. drift task として drift fix queue Wave に再投入
5. wave-integration-report.md に原因記録
```

## 主軸 5: rollback (v3 / task 単位)

### task 単位 rollback

```bash
# 1. 該当 PR を revert
gh pr create --base main --head revert/<task_id> \
  --title "revert: <task_id> (post-merge issue: <reason>)" \
  --body "Reverts #<PR>. See <wave_integration_report_path>"

# 2. revert PR を auto-merge
gh pr merge revert/<task_id> --auto --squash

# 3. drift task を drift fix queue Wave に追加
<drift_ticket_generator> --task <task_id>-redo --target-wave W<N+1>
```

ブランチ単位の `git reset --hard` は **使用禁止** (N 並列で他 task に影響)。

## connections (連携先)

| 上流 | このスキルが受け取る情報 |
|---|---|
| **distributed-dev** | branch-package.json (各 task の管理 JSON) |
| **schedule-design** | wave-schedule.json (Phase × Wave 構成) |
| **test-verification** | gate-config.yml (N gate 定義) |
| **GitHub** | PR list + CI status + auto-merge 状態 |

| 下流 | このスキルが供給する情報 |
|---|---|
| **schedule-design** (drift fix back-feed) | drift-tickets-W<N>.json → 次 Wave drift fix queue に追加 |
| **delivery** | phase-gate-decision.json (Release ゲート) |
| **task-decomposition** | drift task 自動生成依頼 |

## 互換性

- v1: freeze
- v3 (新運用): Wave 集計 + Phase gate 機械判定 (Foundation→Backend→UI→Polish) + drift fix queue + conflict 仕様違反扱い

## 旧 v1 fall-back (小規模納品時)

外部納品プロジェクトで 1 案件 = 5-10 ブランチ程度の場合は v1 流のブランチ単位整理を併用。判定: `team_size < N_THRESHOLD && parallel_wave_count == 0` なら v1 path、それ以外は v3 path。N_THRESHOLD は project-defined。
