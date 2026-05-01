# Build-Factory

**開発特化社員 AI エージェント** — 要件定義 → 設計 → 実装 → テスト → デプロイ → 運用 を AI 社員チームで回す OS。

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| AI Agent | [openai-agents-python](https://github.com/openai/openai-agents-python) + LangGraph |
| LLM | Claude / OpenAI / Ollama (ローカル) / LM Studio / LiteLLM |
| Backend | FastAPI + aiosqlite + alembic |
| Frontend | Next.js 15 + shadcn/ui + Recharts + TanStack Query |
| DB | SQLite (`data/db/build.db`) |
| State | Zustand |
| Protocol | MCP (Model Context Protocol) |
| Observability | Langfuse + Instructor + Mem0 |

## 同居している姉妹プロジェクト

`company-dashboard`（ENGINE BASE 会社運営 OS）と仕様基盤を共有する:

- AI 社員フレームワーク（OpenAI Agents SDK + LangGraph）
- スキル基盤（SKILL.md ベース・skill-creator スキル）
- Artifact 出力管理（15 view × 7 カテゴリ）
- Slot tracking + CoT ルール
- Slack / Web チャット / MCP 統合

両者で完全独立稼働できるよう、DB / Obsidian / credentials / Slack 等の外部リソースは個別 path に分離済み。

## 起動

```bash
# .env を整備（API キー設定）
cp .env.example .env
# OPENAI_API_KEY=sk-... 等を編集

# Backend
cd backend
python3.13 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
PYTHONPATH=. uvicorn main:app --host 0.0.0.0 --port 8001 --reload

# Frontend (別ターミナル)
cd frontend
pnpm install
pnpm dev -p 3001
```

アクセス先:
- Dashboard: http://localhost:3001
- API Docs:  http://localhost:8001/docs

## ポート / リソース割当（company-dashboard と並走可能）

| 項目 | company-dashboard | Build-Factory |
|---|---|---|
| Backend port | 8000 | **8001** |
| Frontend port | 3000 | **3001** |
| DB | `~/Documents/会社運営DB/db/company.db` | `<repo>/data/db/build.db` |
| Skills 格納 | `~/Documents/会社運営DB/skills/` | `<repo>/data/skills/` |
| Obsidian Vault | `~/Documents/Obsidian/ENGINE-BASE` | `<repo>/data/obsidian/` (env 切替可) |
| Claude skills mirror | `~/.claude/skills/` | `~/.claude/skills/build-factory/` |
| credentials store | `~/.engine-base/` | `~/.build-factory/` |
| MCP server 名 | `ENGINE BASE` | `Build-Factory` |

## AI 社員（開発特化版・予定）

| AI | 役割 | 主スキル |
|---|---|---|
| 🎀 PM 秘書 | 要件捕捉・タスク分解・進行管理 | requirements / decomposition / sprint |
| 🏛 アーキテクト | 設計判断・技術選定・ADR | architecture / tech-stack / adr |
| 💻 シニアエンジニア | 実装方針・コード生成 | implementation / patterns |
| 🔍 レビュアー | PR レビュー・品質ゲート | code-review / security |
| 🧪 QA | テスト戦略・E2E 設計 | test-strategy / e2e |
| 🚀 DevOps | CI/CD・デプロイ・運用 | deploy / infra / monitoring |
| 📚 ドキュメント担当 | README / ADR / changelog | documentation |

> 現在は company-dashboard の AI 社員設定をそのまま継承中。順次開発特化版に差し替え予定。

## ステータス

Bootstrap 完了。company-dashboard の core を流用して動く状態。
これから AI 社員 / スキル / 連携先（GitHub / CI/CD）を開発フローに特化する。

## ライセンス

Private (engine-base 内部用)
