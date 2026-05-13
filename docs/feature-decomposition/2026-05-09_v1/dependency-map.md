# Build-Factory 依存関係マップ v1.0（34 機能）

## 9 層階層

```
[L0] F-019 既存 bootstrap 振り分け（依存なし）
    ↓
[L1] F-001 Supabase 基盤 + seed
    ↓
[L2] F-004 account/ws/members ─┬─ F-002 既存スキル整理（並列可）
    ↓                              │
[L3] F-021 custom_permissions ─┴─ F-023 プロフィール（並列可）
    ↓                                    ↓
[L4] F-020 LLM 抽象化（LiteLLM）（F-001 + F-023 BYOK）
    ↓
[L5] F-022 AI 階層 + opt-in（F-001 F-004）
    ↓
    F-003 AI 社員ハイブリッド（F-002 F-020 F-022）
    ↓
🆕 [L5.5 ai_runtime] M-30 Memory 3 層 ← M-28 Context Builder ← M-27 Intent Router
    （LangGraph + Codex CLI 参考実装）
    ↓
[L6] F-025 EARS ─┬─ F-015 HTML レポート ─┬─ F-005 hearing→仕様
                 │                       │       ↓
                 └─────────────────┬─────┴─ F-005b 画面モック
                                   ↓
                             F-006 機能・タスク分解
    ↓
[L7] F-008 フェーズ管理 ─→ F-009 依存グラフ ─→ F-007 多 view UI
                                            ↘
       F-024 グローバル検索（F-001 + F-021 + 多数 entity）
    ↓
[L8] F-026 Constitution ─→ F-012 赤線（OS sandbox + Codex 参考）
    ↓
    F-010a MCP サーバー
    ↓
    F-010b ▶︎ スポナー（F-003 F-010a F-026 F-022 F-012）
    ↓
    F-011 壁打ちループ（F-003 F-010b）
    ↓
[L9] 🆕 M-29 git worktree → F-010c 並列 swarm（F-009 F-010b F-011 M-29）
    ↓
    F-010d WebSocket UI
    ↓
[L10 並列・終盤] 連携層
    F-013 GitHub / F-014 Slack / F-016 Obsidian
    ↓
[L11 最後] 観測層
    F-017 Langfuse / F-018 監査 + バックアップ
```

## 依存が強い箇所（要注意）

| 機能 | 依存先 | 問題 | 対策 |
|---|---|---|---|
| **F-010c** 並列マネージャ | F-009 / F-010b / F-011 / **M-29** | 4 依存・最 hard | F-010b 完成 + 簡易 stub の F-011 で先行 PoC |
| **F-003** AI 社員 | F-002 / F-020 / F-022 | 全 AI 機能の親 | F-020 / F-022 を先に完成（並列）→ F-003 で統合 |
| **F-001** Supabase 基盤 | F-019 のみ | **他 33 機能が直接 / 間接依存** | 最重要・最初に確実に完成 |
| **M-28** Context Builder | F-003 / M-30 | runtime 中核・最 hard | Codex CLI 参考実装で工数短縮 |
| **F-024** グローバル検索 | 多数 entity | 横断参照 | repository pattern で抽象化 |

## 疎結合化提案

| Before | After |
|---|---|
| F-010b スポナーが Constitution / 赤線 / AI 社員を直接呼ぶ | **M-28 Context Builder** 経由で集約 |
| F-007 タスク UI が tasks / DAG / status を直接 fetch | task_repository 層で集約 |
| F-013 GitHub 連携が直接 task 更新 | integration_event_bus（pub/sub）|
| F-024 検索が各 entity を直接 SELECT | search_indexer で集約 |
| F-011 壁打ちが直接 LLM 呼出 | F-020 LiteLLM gateway 経由 |
| AI 社員間の handoff が直結 | LangGraph state 遷移経由（M-27 Intent Router 起点） |

## Sprint 並列マトリクス

| Sprint | 並列 1 | 並列 2 | 並列 3 |
|---|---|---|---|
| Sprint 0 | F-019 | F-001 | F-002 + F-004 |
| Sprint 1 | F-021 | F-023 | - |
| Sprint 2 | F-020 | F-022 + M-30 | F-003 + **M-27 + M-28** |
| Sprint 3 | F-025 + F-015 | F-005 → F-005b | F-006 |
| Sprint 4 | F-008 → F-009 | F-007 | F-024 |
| Sprint 5 | F-026 → F-012 | F-010a | F-010b → F-011 |
| Sprint 6 | **M-29** → F-010c | F-010d（並行） | - |
| Sprint 7 | F-013 | F-014 + F-016 | F-017 + F-018 |

## dogfood 開始可能ライン

| Week | 状態 |
|---|---|
| Week 4 終了 | Sprint 0+1+2 完成 = ヒアリング AI + AI 社員 + LLM 抽象化 + Memory + Context Builder が動く |
| Week 5 | Sprint 3 完成 = 仕様書 HTML が出力できる ← 1 案件のヒアリング → 仕様化が回せる |
| Week 7 | Sprint 4+5 完成 = タスク分解 + ▶︎ 単発実行 + 壁打ちが回る ← 部分 dogfood 開始可能 |
| Week 8 | Sprint 6 完成 = 並列 swarm + git worktree が動く ← フル dogfood 開始可能 |
| Week 9-10 | Sprint 7 完成 = 連携 + 観測完備 ← 「自社 1 案件 End-to-End 完走」可能 |

## 改訂履歴
- v1.0（2026-05-09）：34 機能 + Sprint 配分 + 依存層 9 + 疎結合化提案 6 件
- v1.1 addendum（2026-05-13）：ADR-012 反映. T-AI-MEM-01〜04 を Sprint S2 / S4 に追加.

---

## 2026-05-13 Addendum — ADR-012 cascade

### Sprint S2 への追加 (Memory Tool / Context Editing / Subagent Memory)

| Ticket | Sprint | deps | 工数 (claude_code_hours) |
|---|---|---|---|
| T-AI-MEM-01 (Memory Tool client handler) | S2 | T-S0-08 | 2 |
| T-AI-MEM-02 (Context Editing config) | S2 | T-S0-08, T-AI-MEM-01 | 1 |
| T-AI-MEM-03 (Subagent Memory store) | S2 | T-AI-MEM-01, T-M27-03 | 2 |

### Sprint S4 への追加 (Provider-adapter fallback + 任意切替)

| Ticket | Sprint | deps | 工数 |
|---|---|---|---|
| T-AI-MEM-04 (Provider-adapter; 任意切替 + 障害時 fallback) | S4 | T-AI-MEM-01, T-AI-08, T-024-03 | 4 |
| T-024-04 (workspaces.preferred_provider migration) | S2 | T-024-03 | 1 (予定) |

### F-AI 依存層への影響

- 既存 F-AI 依存層 (T-AI-01 → 02 → 03 → 04 → 05 → 06 → 07 → 08) は不変.
- T-AI-04 (Constitution 注入) の実装方式が「自前」→「Memory Tool delegate」に変更 (依存関係は不変).
- 新規依存: T-AI-MEM-04 が T-AI-08 (障害時 fallback) と T-024-03 (RLS / workspace) に依存.

### 関連 ADR / spec

- ADR-012 (`docs/decisions/ADR-012-anthropic-memory-tool-adoption.md`)
- requirements-v1.md 2026-05-13 Addendum
- architecture-v1.md 2026-05-13 Addendum
- tech-stack-v1.md 2026-05-13 Addendum
