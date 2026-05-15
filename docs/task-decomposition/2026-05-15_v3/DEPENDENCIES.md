# v3 Dependencies / Wave Plan — 2-day Claude Code 並列実行

> **作成日**: 2026-05-15
> **目的**: 211 task / 689 hour / 252 session を **2 日で完走** + **漏れゼロ** で着地させるための DAG と wave 設計

## 物量

| 指標 | 値 |
|---|---|
| 総 task 数 | **113** (2026-05-15 Group H 集約後) |
| 総工数 | **594 hour** (~74 person-day @ 8h) |
| Claude Code セッション換算 | **154 セッション** |
| Phase 0 (gate 整備) | 8 task |
| Phase 1 (Phase 1 dogfood 必須) | 89 task |
| Phase 2 (公開前完成) | 16 task (cleanup + rename + v1 freeze 宣言) |

> Group H が 99 → 1 件 (T-V3-AUDIT-SUMMARY) に圧縮されたため、Wave 5 は短縮されて Day 2 昼が空く。Day 2 で完走可能 (元 2 日計画より 0.5 日短縮)。

## 2 日で完走するための前提

### 必須インフラ
1. **Claude Code 並列セッション = 30-50 並列稼働** (Claude Code on web の同時セッション制限内)
2. **各 task = 独立した branch + worktree** で衝突回避
3. **CI auto-merge gate**: 3-tier AC validator + lint 1-19 + pyright strict + coverage 70% を全部 pass したら手動 review 不要で auto-merge
4. **失敗時の retry スクリプト**: gate 落ちたら同じ task を別セッションで再実行

### 並列実行可能な前提条件
- Phase 0 (Group A) は **必ず先に完走** (8 task / 1 wave)。これが gate を提供する。
- Phase 1 / Phase 2 のタスクは **依存 DAG 上で並列実行可能**

---

## Wave 構成 (依存 DAG ベース)

### Day 0 (準備, ~30 分)
- **Wave -1**: Build-Factory リポジトリの worktree 環境準備、Claude Code 並列 session の認証セットアップ、CI workflow に v3 gate 追加 (CI yml 修正のみ)

### Day 1 朝 (4 時間)
- **Wave 0 — Phase 0 / Group A** (8 task, 8 並列)
  - ADR-013, ADR-014 起票
  - lint #17, #18, #19 実装
  - 3-tier AC validator 実装
  - pyright strict + coverage gate
  - **所要: 2-4h** (lint scripts は最大 1d 規模だが Claude 並列で 2-4h に圧縮)
  - **Wave 0 完了 = 全 PR が新 gate で守られる状態**

### Day 1 昼 (4 時間)
- **Wave 1 — Phase 1 / 基盤 (DB + AUTH)** (50 並列)
  - Group C-1 (4 task): 不在 entity の table 新設 (PhaseGate / ScreenComponent / ArtifactVersion / UserKnowledgeNamespace)
  - Group C-2 (6 task): bf_* rename (依存: ADR-014)
  - Group C-3 (18 task): RLS policy 追加
  - Group B-1 (7 task): AUTH backend (login / signup / pwd-reset / mfa-enroll / mfa-verify / oauth-callback / require_auth)
  - Group G (4 task): 確定 gap 4 件
  - **計 39 task** (並列度: ほぼ全て独立、DB は migration 番号で順序保証)
  - 所要: 4h

### Day 1 夕方 (4 時間)
- **Wave 2 — Phase 1 / Frontend & Drift** (50 並列)
  - Group B-2 (5 task): AUTH frontend (S-001〜S-005)
  - Group B-3 (3 task): AUTH tests
  - Group D (5 task): 重大 drift 修正 (S-006 / S-036 / S-040 + accounts dashboard API + ADR-015)
  - Group E (15 task): 未実装 15 画面の実装 (S-008/010/011/015/020/021/022/023/024/025/030/033/037/042/043)
  - **計 28 task** (各画面 + API + test を 1 task で実装)
  - 所要: 4h

### Day 1 夜 (2 時間)
- **Wave 3 — Phase 1 確認**
  - Wave 0-2 の PR が auto-merge されてるか確認
  - 失敗 task を別 session で retry
  - Phase 1 dogfood 動作確認 (ブラウザで全画面手動巡回 / Playwright で auto)

### Day 2 朝 (4 時間)
- **Wave 4 — Phase 1.5 / REFACTOR** (50 並列)
  - Group F (22 task): 既存 22 画面 REFACTOR (R-1〜R-4 適用)
  - 所要: 3-4h (各画面 4-8h だが REFACTOR は既存ベースなので速い)

### Day 2 昼 (4 時間)
- **Wave 5 — Phase 2 / Audit retrofit** (50 並列)
  - Group H (99 task): v1 怪しい 63 件 再検証 + audit MD 不在 36 件 retrofit
  - **各 task は ~1h ですむ純粋な docs 作業** (Claude が v1 task の impl/test を確認 → 3-tier AC で audit MD を書く)
  - 所要: 99 / 50 並列 = 2 wave × 1h = 2-3h

### Day 2 夕方 (3 時間)
- **Wave 6 — Phase 2 / Cleanup + Rename** (20 並列)
  - Group I (5 task): 余剰整理
  - Group J (10 task): 命名 migration
  - **計 15 task** (依存があるので 3 sub-wave に分ける)
  - 所要: 3h

### Day 2 夜 (2 時間)
- **Wave 7 — Final validation**
  - 全 PR auto-merge 確認 (211 件)
  - 全 audit MD validate-audit-md.py PASS 確認
  - lint 1-19 全 PASS 確認
  - pytest 全 PASS / coverage >= 70% 確認
  - REVIEW_REPORT_2026-05-16_v3.md 起票 (v1 とは違う本物のレビュー)

---

## 依存 DAG (簡略)

```
[Wave 0: Phase 0]
  T-V3-INFRA-01 (ADR-013) ─┐
  T-V3-INFRA-02 (ADR-014) ─┤
  T-V3-INFRA-03 (lint #17) ┤
  T-V3-INFRA-04 (lint #18) ├─→ [Wave 1 & 2 解禁]
  T-V3-INFRA-05 (lint #19) ┤
  T-V3-INFRA-06 (AC validator) ┤
  T-V3-INFRA-07 (pyright) ─┤
  T-V3-INFRA-08 (coverage) ┘

[Wave 1: DB + AUTH backend + Fix]
  Group C (28 task) ──┐
  Group B-1 (7) ──────┼─→ [Wave 2 解禁]
  Group G (4) ────────┘

[Wave 2: AUTH frontend + Drift + 未実装画面]
  Group B-2 (5) ──┐
  Group B-3 (3) ──┤
  Group D (5) ────┼─→ [Wave 3 = Phase 1 dogfood OK]
  Group E (15) ───┘

[Wave 4: REFACTOR]
  Group F (22) ──────→ [Phase 1.5 完了]

[Wave 5: Audit retrofit]
  Group H (99) ──────→ [v1 整合性確定]

[Wave 6: Cleanup + Rename]
  Group I (5) ─┐
  Group J (10) ┤─→ [Wave 7 = Phase 2 完成]
```

## CI gate (各 PR で必須)

```yaml
# .github/workflows/v3-gate.yml (概念)
jobs:
  gate:
    runs-on: ubuntu-latest
    steps:
      - bash scripts/lint-mock.sh   # 1-19 全 OK
      - python3 scripts/validate-ears-ac.py docs/task-decomposition/2026-05-15_v3/tickets.json
      - python3 scripts/validate-audit-md.py docs/audit/2026-05-15_v3/${TASK_ID}.md
      - pytest --cov --cov-fail-under=70
      - pyright --strict
      - cd frontend && tsc --noEmit
      - cd frontend && pnpm run lint
      - if structural AC nonempty: bash scripts/lint-mock-impl-diff.sh ${SCREEN_IDS}
```

全部 PASS → auto-merge bot が main にマージ。
1 つでも FAIL → bot がコメントで失敗内容を書き、Claude session が retry。

## 失敗 retry プロトコル

各 task が gate 落ちた場合:
1. CI が PR コメントに失敗内容貼る
2. session orchestrator が同じ task の retry session を起動
3. 3 回連続失敗 → human エスカレーション (PM 確認)

## 並列度の上限

Claude Code on web の同時 session 制限は plan によるが、Build-Factory プラン想定で **30-50 並列**。
50 並列なら:
- Wave 1: 39 task / 50 = 1 wave で完走
- Wave 2: 28 task / 50 = 1 wave で完走
- Wave 4: 22 task / 50 = 1 wave で完走
- Wave 5: 99 task / 50 = 2 wave (但し短時間タスク)
- Wave 6: 15 task / 50 = 1 wave で完走

→ 合計 wave 数 = 7 wave、各 1-4 時間 = **2 日に収まる**。

## 漏れゼロの保証

「漏れ」の発生源 → 検出機構:

| 漏れの種類 | 検出機構 |
|---|---|
| 仕様 AC が満たされていない | 3-tier AC validator (functional 必須) |
| Mock と画面が違う | lint #17 mock-impl diff |
| Spec API が backend に無い | lint #18 screens-API |
| Entity 名前ドリフト / bf_ 残留 | lint #19 entity-table naming |
| RLS policy 不足 | scripts/verify-rls-coverage.py |
| audit MD が generic | validate-audit-md.py |
| coverage < 70% | pytest --cov-fail-under=70 |
| 型エラー | pyright --strict / tsc --noEmit |

**全 8 gate を merge gate にして、ひとつでも fail なら merge できない** → 漏れ構造的に発生不可能。
