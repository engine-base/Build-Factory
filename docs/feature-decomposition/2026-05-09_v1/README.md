# Build-Factory feature-decomposition v1.0（2026-05-09）

このフォルダは **feature-decomposition スキルの最終出力**を保管します。

要件定義 + アーキ + functional-breakdown + tech-stack を入力に、**34 機能を実装単位に分解 + 依存関係 + Sprint 配分**を確定。

## ファイル一覧

| ファイル | 役割 |
|---|---|
| `client-summary.md` | クライアント・PM 向け説明 |
| `features-decomposed.json` | 開発用 JSON（機能 + 依存 + 工数） |
| `dependency-map.md` | 依存関係マップ |
| `decision-log.json` | 判断ログ |

## クイックビュー

### 機能数（v1.1 反映）
- **Phase 1 Must = 34 機能**（v1.0 の 30 + M-27/28/29/30）
- Phase 1.5 Should = 13（S-1〜S-12 + S-13 Real-time Steering）
- Phase 2/3/Future Could = 13（C-1〜C-11 + C-12 Knowledge Graph + C-13 実装エンジン切替）
- Won't = 8

### Sprint 配分（9-10 週間）

| Sprint | 期間 | 機能 |
|---|---|---|
| Sprint 0（基盤）| W1-2 | F-019 / F-001 / F-002 / F-004 |
| Sprint 1（認可）| W2-3 | F-021 / F-023 |
| Sprint 2（AI 基盤）| W3-4 | F-020 / F-022 / F-003 + **M-27 Intent Router** + **M-28 Context Builder** + **M-30 Memory 3 層統合** |
| Sprint 3（仕様化）| W4-5 | F-025 / F-015 / F-005 / F-005b / F-006 |
| Sprint 4（管理 UX）| W5-6 | F-008 / F-009 / F-007 / F-024 |
| Sprint 5（実行コア）| W6-7 | F-026 / F-012 / F-010a / F-010b / F-011 |
| Sprint 6（並列 swarm）| W7-8 | F-010c / F-010d + **M-29 git worktree** |
| Sprint 7（連携・観測）| W8-9 | F-013 / F-014 / F-016 / F-017 / F-018 |

### 依存層（9 層）
```
L0 整理 → L1 基盤 → L2 認可 → L3 AI 基盤（+ runtime 補強）
→ L4 仕様化 → L5 管理層 → L6 実行コア
→ L7 並列・UI → L8 連携 → L9 観測
```

### dogfood 開始ライン
- **Week 7**：部分 dogfood 開始可（▶︎ 単発 + 壁打ち動作）
- **Week 9**：フル dogfood 完成（自社 1 案件 End-to-End 完走可）

## 関連ファイル
- `../../tech-stack/2026-05-09_v1/` — tech-stack v1.0
- `../../functional-breakdown/2026-05-09_v1/` — 機能分解詳細 v1.0 → v1.1 更新中
- `../../architecture/2026-05-09_v1/` — アーキ v1.0 → v1.1 更新中

## 改訂履歴
- **v1.0**（2026-05-09）：feature-decomposition 5STEP 完了・34 機能 + Sprint 配分確定
