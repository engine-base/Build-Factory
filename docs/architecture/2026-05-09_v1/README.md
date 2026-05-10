# Build-Factory v2.1 アーキテクチャ設計書 v1（2026-05-09）

このフォルダは **architecture-design スキル STEP 5 の最終出力**を保管します。

> 要件定義 v1.0 → アーキテクチャ設計 v1.0 への昇格段階。次は tech-stack / functional-breakdown スキルへ。

---

## ファイル一覧

| ファイル | 役割 | 想定読者 |
|---|---|---|
| **`architecture-v1.html`** | アーキテクチャ仕様書（HTML・ENGINE BASE 配色・Mermaid 図解付き） | クライアント / 監視担当 / 社内共有 |
| **`er-diagram-v1.html`** | ER 図 + テーブル定義 + インデックス設計（Mermaid ER） | 開発者 / DBA |
| **`architecture-v1.md`** | Markdown 版（軽量編集用） | 開発者 / Git 差分管理 |
| **`architecture_design.json`** | アーキ設計 JSON（後続スキル引き継ぎ） | functional-breakdown / feature-decomposition / tech-stack 入力 |
| **`architecture_decision_log.json`** | 判断ログ + リサーチ findings | MCP 連携 / 案件 DB 蓄積 |

---

## クイックビュー

### 確定したアーキ
- **アーキパターン**：モジュラーモノリス（FastAPI + Next.js）
- **DB / 認証**：Supabase Postgres + RLS + Auth + Storage + Realtime
- **AI 統合**：BMAD 思想流用 + 自前統合 + Anthropic Agent Teams ハイブリッド + 既存 96 スキル
- **LLM 抽象化**：LiteLLM（self-host）
- **subprocess 管理**：claude-agent-sdk（Python）
- **観測**：Langfuse self-host（MIT）
- **DB マイグレーション**：Supabase CLI（既存 alembic は archive）
- **個人クローン opt-in**：デフォルト OFF（プライバシー保守的）
- **Constitution + 赤線**：階層管理（Constitution が上位・赤線が検出ルール）

### Phase 1 = 初期コスト ¥0 構成
- Frontend：Vercel Hobby（無料）
- Backend + Worker + Langfuse：Oracle Cloud Free Tier（4 vCPU + 24GB RAM 永久無料）or 自宅 PC + Cloudflare Tunnel
- DB：Supabase Free（500MB）
- Sentry / Better Stack / GitHub Actions：無料枠
- 合計：¥0 / 月（API・Claude プラン除く）

### モジュラーモノリス構造（13 ドメインモジュール）
auth_tenant / ai_employee / skill / hearing_spec / phase_dependency / task / session_swarm / mcp_server / reviewer_loop / safety / permission / integration_* / observability / search

### DB（42 テーブル）
- 認証・テナント 6 / AI・スキル 5 / プロジェクト管理 6 / 仕様・モック 5 / 実装・レビュー 7 / 連携・運用 11 + 補助 2

---

## 次のスキル進行順

```
✅ hearing v2.1
✅ requirements-definition v1.0
✅ architecture-design v1.0  ← イマココ完了
  ↓
tech-stack（OSS 候補の最終選定 + 並列セッション PoC + Supabase plan + DPA）
  ↓
functional-breakdown（画面・機能・ロール権限・エンティティ草案）
  ↓
feature-decomposition（機能を分散開発可能粒度に + 壁打ち 3 ターン具体）
  ↓
task-decomposition（Phase 1 Must 30 項目を実装単位に + 工数見積もり）
  ↓
distributed-dev（Claude Code 実装パッケージ化 + dogfooding 開始）
```

---

## 関連ファイル

- `../../requirements/2026-05-09_v1/` — 要件定義 v1.0（前提ドキュメント）
- `../../hearing/2026-05-09_re-hearing/` — ヒアリング v2.1

## 後続成果物

- 🆕 **functional-breakdown v1.0** → `docs/functional-breakdown/2026-05-09_v1/`
- 🆕 **feature-decomposition v1.0** → `docs/feature-decomposition/2026-05-09_v1/`
- 🆕 **tech-stack v1.0** → `docs/tech-stack/2026-05-09_v1/`

## v1.1 反映予定（重要差分）

tech-stack / feature-decomposition で以下のアーキ更新が確定：

### AI Stack 5 層化（簡素化）
```
LangGraph (MIT) — 全体 Orchestrator
LiteLLM (MIT・self-host) — Provider 抽象化
claude-agent-sdk (MIT) — Claude Code subprocess
Anthropic Agent Teams — Claude Code 内部 Plan/Gen/Eval
[参考] openai/codex (Apache 2.0) — コードロジック参考のみ・依存なし
```
- **不採用**：OpenAI Agents SDK / openai-python 直接利用 / GrapesJS Studio SDK

### 新規 ai_runtime レイヤー（Phase 1 Must 4 項目追加）
- M-27 Intent Router（LangGraph entry node・分類 → handoff）
- M-28 Context Builder（**Claude 流 3-tier compaction + prompt cache + 9-section structured summary**）
- M-29 Workspace Isolation = git worktree（Codex CLI 参考）
- M-30 Memory 3 層統合層（短期 ChatThread / 中期 ChatMessage 圧縮済 / 長期 Mem0+Obsidian+Constitution）

### M-12 赤線強化
- OS-level sandbox（Seatbelt / Landlock + seccomp）を組込み（Codex CLI 参考）

### AI 社員構成（10 → 14 → 15 → +N）
- Phase 1：10 体メンバー（Mary BA / Preston PM / Winston Architect / Sally PO / Devon Dev / Quinn QA / Reviewer / Brand / Mockup / Curator）
- Phase 1.5：+4 部署リーダー（Sam Eng / Dani Design / Quinn-Lead QA / Logan Knowledge）
- Phase 2：+1 COO
- Future：+N 個人クローン（C-11・別アプリ切出し）

### Phase 別コスト
- Phase 1 dogfood = ¥125/月 + 個人 Claude Max ¥30,000
- Phase 1.5 = ¥17,000-21,000/月
- Phase 2 = ¥40,000-80,000/月
- Phase 3 = ¥120,000-200,000/月

### Phase 2 追加（Could）
- C-12 Knowledge Graph（Apache AGE）
- C-13 実装エンジン切替（Codex CLI / Gemini CLI）

## 改訂履歴

- **v1.0**（2026-05-09）: 要件定義 v1.0 → アーキ設計 v1.0 への正式昇格（30 Must）
- **v1.1 反映**（2026-05-09）: 5 層 AI スタック簡素化 + ai_runtime レイヤー追加 + Codex CLI 参考方針 + GrapesJS core 確定 + AI 社員構成詳細化（差分は本 README 反映・本フォルダ内ファイルは v1.0 snapshot 保持）
