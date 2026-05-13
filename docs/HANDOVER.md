# Build-Factory 引き継ぎ書 (HANDOVER)

> **このファイルは新セッションが「最初に読むべき」統合インデックス。**
> CLAUDE.md (リポジトリ直下) を読んだ後、ここから各フェーズ成果物に飛ぶ。

---

## 0. クイック俯瞰 (3 分で全容を把握する)

| 質問 | 答え | リンク |
|---|---|---|
| **何を作ってるの?** | SaaS 型「開発工場 OS」 = 1 人で 10 案件並列 | §1 |
| **誰のため?** | 受託会社 / 中小企業の社内開発 / フリーランス + ENGINE BASE 内製 | `requirements/` |
| **どこまで進んだ?** | フェーズ 1〜8 完了、フェーズ 9「実装」が次 | §2 |
| **何個タスクある?** | 113 件 (REUSE 14 / REFACTOR 50 / NEW 49 / ARCHIVE 9) | `task-decomposition/` |
| **何画面?** | 43 画面、HTML モック完成済み | `mocks/2026-05-09_v1/` |
| **どこから実装する?** | クリティカルパス先頭の `T-019-01` | §6 |
| **コストは?** | Phase 1 = ¥0/月 (Vercel Hobby + Oracle Cloud Free + Supabase Free) | `tech-stack/` |
| **重要ルール?** | アイコンは Lucide のみ、AC は EARS 形式、AGPL 禁止 | `CLAUDE.md` §5 |

---

## 1. プロジェクト概要

**Build-Factory** = 株式会社 ENGINE BASE の **SaaS 型「開発工場 OS」**。

```
ヒアリング → 要件定義 → アーキ設計 → 機能分解 → タスク分解 → 実装 → テスト → 進捗管理 → 納品
```

これら全てを **1 つの Web アプリ**で完結させ、AI 社員 (BMAD 10 ペルソナ) を実行者として **1 人で 10 案件を並列運用** する。

詳細: [`hearing/2026-05-09_re-hearing/hearing_summary.html`](hearing/2026-05-09_re-hearing/hearing_summary.html)

---

## 2. フェーズ進捗マップ

```
[Phase 1] ヒアリング          ✅ → docs/hearing/2026-05-09_re-hearing/
[Phase 2] 要件定義             ✅ → docs/requirements/2026-05-09_v1/
[Phase 3] アーキ設計           ✅ → docs/architecture/2026-05-09_v1/
[Phase 4] 機能分解             ✅ → docs/functional-breakdown/2026-05-09_v1/
[Phase 5] 技術選定             ✅ → docs/tech-stack/2026-05-09_v1/
[Phase 6] 機能依存分解         ✅ → docs/feature-decomposition/2026-05-09_v1/
[Phase 7] タスク分解           ✅ → docs/task-decomposition/2026-05-09_v1/
[Phase 8] 画面モック (43 件)   ✅ → docs/mocks/2026-05-09_v1/
─────────────────────────────────────
[Phase 9] 実装 (113 タスク)    ⏳ NEXT
[Phase 10] レビュー / 納品     ⏸ 未着手
```

---

## 3. 全成果物のインデックス

### 3.1 ヒアリング → 要件定義
| 成果物 | パス | 重要度 |
|---|---|---|
| ヒアリング サマリー HTML | `hearing/2026-05-09_re-hearing/hearing_summary.html` | ★★★ |
| project_brief.json | `hearing/2026-05-09_re-hearing/project_brief.json` | ★★ |
| 決定ログ | `hearing/2026-05-09_re-hearing/decision_log.json` | ★★ |
| 要件定義書 v1 (HTML) | `requirements/2026-05-09_v1/requirements-v1.html` | ★★★ |
| Must 34 項目 (M-1〜M-30) | `requirements/2026-05-09_v1/requirements-v1.md` | ★★★ |

### 3.2 アーキテクチャ
| 成果物 | パス | 重要度 |
|---|---|---|
| アーキ設計書 v1 (HTML) | `architecture/2026-05-09_v1/architecture-v1.html` | ★★★ |
| ER 図 (43 entities) | `architecture/2026-05-09_v1/er-diagram-v1.html` | ★★★ |
| 7 層アーキ概要 | `architecture/2026-05-09_v1/architecture-v1.md` | ★★ |

### 3.3 機能分解
| 成果物 | パス | 重要度 |
|---|---|---|
| 機能分解 HTML | `functional-breakdown/2026-05-09_v1/functional-breakdown.html` | ★★★ |
| screens.json (43) | `functional-breakdown/2026-05-09_v1/screens.json` | ★★ |
| features.json (30) | `functional-breakdown/2026-05-09_v1/features.json` | ★★ |
| roles.json (6) | `functional-breakdown/2026-05-09_v1/roles.json` | ★ |
| entities.json (43) | `functional-breakdown/2026-05-09_v1/entities.json` | ★★ |

### 3.4 技術選定
| 成果物 | パス | 重要度 |
|---|---|---|
| tech-stack v1 (HTML) | `tech-stack/2026-05-09_v1/tech-stack-v1.html` | ★★★ |
| selected-stack.json | `tech-stack/2026-05-09_v1/selected-stack.json` | ★★ |
| コスト試算 | `tech-stack/2026-05-09_v1/cost-projection.md` | ★ |

### 3.5 機能依存分解 → タスク分解
| 成果物 | パス | 重要度 |
|---|---|---|
| 依存マップ MD | `feature-decomposition/2026-05-09_v1/dependency-map.md` | ★★ |
| features-decomposed.json | `feature-decomposition/2026-05-09_v1/features-decomposed.json` | ★★ |
| **113 タスク (Kanban HTML)** | `task-decomposition/2026-05-09_v1/tickets.html` | **★★★** |
| **tickets.json (機械処理用)** | `task-decomposition/2026-05-09_v1/tickets.json` | **★★★** |
| API インターフェース定義 | `task-decomposition/2026-05-09_v1/interfaces.md` | ★★ |
| 決定ログ | `task-decomposition/2026-05-09_v1/decision-log.json` | ★ |

### 3.6 画面モック (43 件)
| 成果物 | パス | 重要度 |
|---|---|---|
| **モック index** (43 一覧) | `mocks/2026-05-09_v1/index.html` | **★★★** |
| design-tokens.md (色 / フォント / アイコン規約) | `mocks/2026-05-09_v1/design-tokens.md` | **★★★** |
| mock-tracker.json | `mocks/2026-05-09_v1/mock-tracker.json` | ★★ |

#### 重要 10 画面 (フル実装)
| ID | 画面 | パス |
|---|---|---|
| S-001 | login | `mocks/2026-05-09_v1/auth/S-001-login.html` |
| S-006 | account_dashboard (10 案件俯瞰) | `mocks/2026-05-09_v1/account/S-006-account-dashboard.html` |
| S-012 | workspace_dashboard | `mocks/2026-05-09_v1/workspace/S-012-workspace-dashboard.html` |
| S-017 | dependency_graph (DAG) | `mocks/2026-05-09_v1/moat/S-017-dependency-graph.html` |
| S-020 | hearing_session | `mocks/2026-05-09_v1/spec/S-020-hearing-session.html` |
| S-022 | spec_viewer (HTML/MD タブ) | `mocks/2026-05-09_v1/spec/S-022-spec-viewer.html` |
| S-027 | task_kanban (機能別アコーディオン) | `mocks/2026-05-09_v1/task/S-027-task-kanban.html` |
| S-030 | task_detail (▶ + EARS AC) | `mocks/2026-05-09_v1/task/S-030-task-detail.html` |
| S-031 | swarm_grid (16 並列) | `mocks/2026-05-09_v1/task/S-031-swarm-grid.html` |
| S-032 | swarm_session_detail | `mocks/2026-05-09_v1/task/S-032-swarm-session-detail.html` |

残り 33 画面はカテゴリ別に `auth/`, `account/`, `workspace/`, `moat/`, `spec/`, `task/`, `review/`, `ai/`, `ops/`, `client/` に格納。

### 3.7 技術判断記録 (ADR)
| ADR | テーマ | パス |
|---|---|---|
| ADR-001 | モジュラーモノリス採用 | `decisions/ADR-001-modular-monolith.md` |
| ADR-002 | ⚠️ AI スタック 5 層構成 (Superseded by ADR-010) | `decisions/ADR-002-ai-stack-5-layer.md` |
| ADR-003 | Memory 3 tier | `decisions/ADR-003-memory-3-tier.md` |
| ADR-004 | Phase 1 ¥0 ホスティング | `decisions/ADR-004-phase1-zero-cost-hosting.md` |
| ADR-005 | アイコンは Lucide のみ | `decisions/ADR-005-lucide-icons-only.md` |
| ADR-006 | タスクラベル REUSE/REFACTOR/NEW/ARCHIVE | `decisions/ADR-006-task-labels.md` |
| ADR-007 | EARS notation 必須 | `decisions/ADR-007-ears-notation.md` |
| ADR-008 | Kanban 機能別アコーディオン | `decisions/ADR-008-kanban-by-feature.md` |
| ADR-009 | 各案件への強制レイヤー自動展開 | `decisions/ADR-009-project-bootstrap-enforcement.md` |
| ADR-010 | **AI スタック再設計 (3層 / Anthropic 純正中心 + LiteLLM サブ)** ⚠️ Amended by ADR-012 | `decisions/ADR-010-ai-stack-anthropic-native.md` |
| ADR-011 | 完了判定ゲート (`pre-commit-check.sh`) と N/A 禁止原則 | `decisions/ADR-011-completion-gate.md` |
| ADR-012 | **Anthropic 公式 Memory Tool / Context Editing / Subagent Memory 採用** (ADR-010 amend; T-AI-MEM-01〜04 新規; GPT-4o/Gemini fallback provider-adapter 含む) | `decisions/ADR-012-anthropic-memory-tool-adoption.md` |

---

## 4. 重要な数字 (覚えておくこと)

| 数値 | 意味 |
|---|---|
| **43** | 画面数 (モック完成) |
| **30** | 機能 (features) 数 |
| **43** | エンティティ (DB tables) 数 |
| **6** | ロール (RLS) 数 |
| **113** | 総タスク数 |
| **14 / 50 / 49 / 9** | REUSE / REFACTOR / NEW / ARCHIVE |
| **34** | Must 要件 (M-1〜M-30 + 4 件 sub) |
| **8** | Sprint 数 (S0〜S7) |
| **10** | 並列案件数 (1 人で運用) |
| **¥0** | Phase 1 月額 (ドメイン除く) |

---

## 5. クリティカルパス (実装着手順)

```
T-019-01 (ARCHIVE: onlook 削除)
  ↓
T-S0-13 (Sprint 0 scaffold)
  ↓
T-001-01 (FastAPI モジュラーモノリス基盤)
  ↓
T-001-02 (auth integration)
  ↓
T-001-04 (middleware)
  ↓
T-001-06 (RLS 設定)
  ↓
T-S0-08 (claude-runner 基盤)
  ↓
T-S0-09 (sandbox = Seatbelt/Landlock)
  ↓
T-021-03 (swarm 実装)
  ↓
T-020-02 (memory 3 tier)
  ↓
T-003-02 (workspace_dashboard)
  ↓
T-M28-01 (memory 完成)
```

各タスクの詳細仕様 (AC / 依存 / 既存ファイル) は [`task-decomposition/2026-05-09_v1/tickets.html`](task-decomposition/2026-05-09_v1/tickets.html) を参照。

---

## 6. 実装の進め方 (Phase 9 着手手順)

### 6.1 環境セットアップ (初回のみ)

```bash
# 1. リポジトリ最新化
cd ~/Documents/Build-Factory
git fetch origin
git checkout claude/project-overview-planning-McQUW
git pull

# 2. ローカル環境
# (詳細は README.md 参照、bootstrap 済み)

# 3. Supabase プロジェクト作成 (Phase 1 着手時のみ)
# (Supabase Dashboard で作成 → SUPABASE_URL / SUPABASE_KEY を .env に設定)

# 4. Vercel + Oracle Cloud のセットアップ (Phase 1 着手時のみ)
# (ADR-004 参照)
```

### 6.2 タスク実行サイクル (Sprint 0 から)

```
1. tickets.html でクリティカルパス先頭タスクを開く (T-019-01)
2. 対応するモック (S-XXX) と仕様書 (M-X) を確認
3. acceptance_criteria (EARS) を全て満たす実装をする
4. テスト (>= 70% カバレッジ) を書く
5. PR 作成 → CI Pass → quinn (QA) レビュー → masato 承認 → main マージ
6. tickets.html で次のタスクへ
```

### 6.3 Swarm 並列実行 (Sprint 4 以降)

T-S0-08 + T-021-03 が完成したら、複数タスクを並列起動できる:

```
swarm size = 4 / 9 / 16 / 64
各セッション = 1 タスクを別 git worktree + 別ブランチで実装
crash 時は S-032 で 4 択 resume (from_checkpoint / rerun_full / manual_fix / cancel)
```

詳細: [`mocks/2026-05-09_v1/task/S-031-swarm-grid.html`](mocks/2026-05-09_v1/task/S-031-swarm-grid.html)

---

## 7. お作法 (絶対遵守)

CLAUDE.md §5 と重複するが、忘れがちな順:

1. **アイコンは Lucide のみ** (`<i data-lucide="play">`) — 絵文字 ❌
2. **AC は EARS 形式** (UBIQUITOUS / EVENT / STATE / OPTIONAL / UNWANTED の 5 形式)
3. **既存実装 (bootstrap) を REUSE/REFACTOR で活用** — 新規追加は最後の手段
4. **AGPL 依存追加禁止** (SaaS 提供のため)
5. **`--no-verify` / `--force push` 禁止** (明示承認時のみ)
6. **本番 DB に DROP/TRUNCATE/DELETE * 禁止** (即セッション kill)
7. **重大変更は masato に確認** (DB schema / 主要パッケージ / Phase ゲート)
8. **モック修正は S-023 経由** (GUI / AI / HTML 編集 → 新バージョン保存)

---

## 8. 直近の変更履歴

```
2026-05-10  CLAUDE.md / HANDOVER.md / 8 ADR を整備 (このファイル含む)
2026-05-10  S-027 Kanban 機能別アコーディオン化、S-023 編集 UI 追加、絵文字 175 件 → Lucide
2026-05-10  43 画面モック完成 (重要 10 + 残り 33)
2026-05-09  113 タスクに圧縮 (152 → 113、REUSE 活用)
2026-05-09  全 8 フェーズ ヒアリング → 確定
2026-05-08 以前  bootstrap (40 routers + 50 services + 8 migrations)
```

git 履歴: `git log --oneline -20`

---

## 9. 困った時

| 状況 | 動き |
|---|---|
| **どこから読めばいい?** | このファイル → CLAUDE.md → 各フェーズ READMEの順 |
| **タスクの詳細仕様は?** | `task-decomposition/2026-05-09_v1/tickets.html` でカード形式 |
| **画面のイメージは?** | `mocks/2026-05-09_v1/index.html` をブラウザで |
| **API はどう設計?** | `task-decomposition/2026-05-09_v1/interfaces.md` |
| **DB スキーマは?** | `architecture/2026-05-09_v1/er-diagram-v1.html` |
| **なぜこの技術?** | `decisions/ADR-001` 〜 `ADR-009` を参照 |
| **判断に迷う** | masato (高本まさと) に AskUserQuestion で確認 |

---

**最終更新: 2026-05-10**
**このファイルが古い場合は CLAUDE.md の「最終更新」と git log を見て確認**
