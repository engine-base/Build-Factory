# Build-Factory 機能分解結果（クライアント・PM 向け）

## 分解の方針

要件定義 v1.0 の 30 Must 機能 + functional-breakdown v1.0 + tech-stack v1.0 の決定を踏まえ、**34 機能 + 13 Should + 13 Could を 9 週間 / Sprint 0-7 で実装可能な単位に分解**しました。

並列開発できる単位を最大化しつつ、依存関係を 9 層に整理。dogfood 主軸の Claude Code を「実装エンジン」として並列実行（git worktree + 5 並列 swarm）することで、実質 5-6 週間に短縮可能です。

## 機能構造の概要

### Phase 1（MVP・34 機能）

```
基盤（Sprint 0）= 4 機能
  Supabase 基盤 / 既存 96 スキル整理 / テナント階層 / bootstrap 振り分け
    ↓
認可（Sprint 1）= 2 機能
  custom_permissions UI + monitor / プロフィール
    ↓
AI 基盤（Sprint 2）= 6 機能 ★ runtime 層 3 機能（M-27/28/30）含む
  LLM 抽象化 / AI 階層 + opt-in / AI 社員ハイブリッド
  + Intent Router / Context Builder / Memory 3 層統合
    ↓
仕様化（Sprint 3）= 5 機能
  EARS notation / HTML レポート 7 種 / hearing → 仕様 → 画面モック / タスク分解
    ↓
管理 UX（Sprint 4）= 4 機能
  フェーズ管理 / 依存グラフ / 多 view / グローバル検索
    ↓
実行コア（Sprint 5）= 5 機能
  Constitution / 赤線 / MCP / ▶︎ スポナー / 壁打ち
    ↓
並列 swarm（Sprint 6）= 3 機能
  git worktree / 並列マネージャ + crash detection + resume / WebSocket UI
    ↓
連携・観測（Sprint 7）= 5 機能
  GitHub / Slack / Obsidian / Langfuse / 監査・バックアップ
```

### Phase 1.5（社内拡張・13 機能）
- メンバー / クライアント招待
- Slack 双方向 + Claude Desktop MCP
- GrapesJS core で GUI 編集
- Obsidian Headless Sync
- impact-analysis + task-propagation
- BYOK 設定 UI
- AI モデル / プロンプトバージョン管理
- 通知・アラートフル
- ナレッジ自動キュレーション
- crash detection 完成
- 部署リーダー AI 4 体（Sam / Dani / Quinn-Lead / Logan）
- オンボーディング
- **Real-time Session Steering（Codex CLI 参考）**

### Phase 2/3/Future（13 機能）
- OpenFGA / AI 評価基盤 / デプロイ連携アダプタ / テンプレート / E2E
- COO AI / **Knowledge Graph (Apache AGE)** / **実装エンジン切替（Codex CLI / Gemini CLI）**
- Stripe 課金 / SaaS マルチテナント本格化 / i18n / Marketplace / 個人クローン化サービス

## AI 社員の動作（並列開発の核）

各機能は **LangGraph の node** として動き、**LiteLLM** 経由で LLM 呼出。**実装エンジンは Claude Code（claude-agent-sdk 経由）** をデフォルトに、ユーザの好みで Phase 2 から Codex CLI / Gemini CLI に切替可能。

**Phase 1 = 10 体のメンバー AI 社員**（Mary BA / Preston PM / Winston Architect / Sally PO / Devon Dev / Quinn QA / Reviewer / Brand / Mockup / Curator）
**Phase 1.5 = 部署リーダー 4 体追加**
**Phase 2 = COO 1 体追加**
**Future = 個人クローン N 体（別アプリ C-11）**

## 並列開発戦略

| 段階 | dogfood 状況 |
|---|---|
| Week 4 | AI 基盤完成 → ヒアリング AI が動く |
| Week 5 | 仕様書 HTML 生成可 |
| Week 7 | 部分 dogfood 開始（▶︎ 単発 + 壁打ち） |
| Week 8 | 並列 swarm 動作 → フル dogfood |
| Week 9-10 | 連携・観測完備 → Phase 1 MVP 完成 |

## コスト

| Phase | 月額（運用） |
|---|---|
| Phase 1（dogfood） | **¥125 + 個人 Claude Max ¥30,000** |
| Phase 1.5 | ¥17,000-21,000 + 各メンバープラン |
| Phase 2 | ¥40,000-80,000（顧客課金で相殺可） |
| Phase 3 | ¥120,000-200,000（MAU 100 で採算） |

## ライセンス（全クリア）

- **AGPL 完全除外**（CI で license-checker / pip-licenses）
- 主要 OSS：MIT / Apache 2.0 / BSD-3 / PostgreSQL License
- Sentry（BSL 1.1）= 自社運用 OK
- **Codex CLI（Apache 2.0）はコードロジック参考のみ**（依存に入れない）

## 関連ファイル

- `features-decomposed.json` — 34 機能 + 依存 + 工数
- `dependency-map.md` — 依存関係マップ
- `decision-log.json` — 14 主要決定 + 5 未解決事項 + リサーチ
- `../../tech-stack/2026-05-09_v1/` — tech-stack v1.0
