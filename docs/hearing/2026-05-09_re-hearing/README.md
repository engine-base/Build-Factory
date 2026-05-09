# 2026-05-09 再ヒアリング — Build-Factory v2

このフォルダは、2026-05-09 に実施した Build-Factory の **再ヒアリング**（コンセプトから根本再設計）の最終出力をまとめたものです。

> v1 PROJECT_BRIEF（2026-05-01）はコンセプト含めて白紙化し、ここから新しい仕様体系（v2）が始まります。

---

## ファイル一覧

| ファイル | 役割 | 想定読者 |
|---|---|---|
| **`hearing_summary.md`** | ヒアリングサマリー（Markdown） | PM / クライアント / 社内共有 |
| **`hearing_summary.html`** | ヒアリングサマリー（HTML 版・Tailwind + SVG 図解付き） | 同上（リッチに読みたい時） |
| **`project_brief.json`** | プロジェクト起点 構造化データ | 後続スキル（requirements-definition / architecture-design 等）への入力 |
| **`decision_log.json`** | 判断ログ + Web リサーチ findings + ヒアリングパターン | MCP 連携 / 案件 DB 蓄積 / 次回類似案件の高速化 |

---

## クイックビュー

### コンセプト（v2 確定）
> **企画から納品までの全工程を 1 環境で完璧に進めるプロジェクト管理 OS**

### 本質的なゴール
1 人で **10 案件並走**しても破綻しない開発体制を作り、SaaS 商用化する

### Phase 1 Must（22 項目）
- Supabase 基盤移行 / 既存スキル整理 / AI 社員ハイブリッド統合
- account / workspace 階層 / ヒアリング → 仕様書 HTML / タスク分解
- 多 view（Kanban + List + DAG）/ フェーズ管理 / 依存グラフ
- MCP / ▶︎ 再生 / 並列 swarm / WebSocket UI
- リーダー AI 壁打ち / 赤線リスト / GitHub / Slack / HTML レポート
- Obsidian / Langfuse / 監査ログ + バックアップ / bootstrap 振り分け

### 主要な方針転換（v1 からの差分）
- **Onlook / Open Design 不採用** → 仕様書 → HTML/CSS で完璧再現 + GrapesJS GUI 編集
- **出力フォーマット = HTML + Markdown ハイブリッド**（HTML デフォルト）
- **タスク ▶︎ 再生 + 並列実行 + swarm view** を Phase 1 から実装
- **DB / 認証 = Supabase 全面採用**（SQLite から移行）
- **AI 社員 = BMAD + Anthropic Agent Teams + 既存 96 スキル ハイブリッド**
- **実装層 LLM = 各自 Claude Pro/Max プラン**（Build-Factory 側 API 課金最小）
- **デプロイ環境 = 連携アダプタ式**（Vercel / Netlify / Coolify / Cloud Run / 自前 SSH）
- **ナレッジ母艦 = Obsidian**

---

## 次のスキル進行順（推奨）

```
hearing（このセッション・完了）
  ↓
requirements-definition  ← M-1〜M-19 の要件を詳細化
  ↓
architecture-design      ← Supabase 移行 / AI 社員統合 / Plan-Gen-Eval の技術設計
  ↓
tech-stack               ← OSS 候補の最終選定（BMAD / GrapesJS / Langfuse 等）
  ↓
functional-breakdown     ← 画面・機能・ロール権限・エンティティ草案
  ↓
feature-decomposition    ← 機能を分散開発可能な粒度まで分解
  ↓
task-decomposition       ← 各機能を Claude Code が独立実装できる単位に
  ↓
distributed-dev          ← 各タスクを「ブランチ実装パッケージ」に変換
  ↓
（Build-Factory が指示所、Claude Code が実装、リーダー AI が壁打ち）
```

---

## 関連ファイル

- `../2026-05-01_hearing_log.md` — v1 ヒアリングログ（参考）
- `../../PROJECT_BRIEF.md` — v1 PROJECT_BRIEF（参考・白紙化済）
- `../../PROJECT_BRIEF.json` — v1 構造化版（参考）
- `../../../README.md` — リポジトリ README

---

## 編集ルール

このフォルダのファイルは **生きた仕様書** ですが、原則として **再ヒアリング時のスナップショット**として保持します。
- 内容の更新が必要になった場合は、新しい日付フォルダ（例：`2026-XX-XX_re-hearing/`）を切ってください
- このフォルダ内のファイルは「2026-05-09 時点の決定」として履歴的価値を残してください

最新の正式仕様書は次のフェーズ（requirements-definition 以降）の出力で更新されます。
