# Company OS Dashboard

一人会社の経営を一元管理するAIダッシュボード。

## 技術スタック

| レイヤー | 技術 |
|---------|------|
| AI Agent | [openai-agents-python](https://github.com/openai/openai-agents-python) |
| LLM | Claude / OpenAI / **Ollama (ローカル)** / LM Studio / LiteLLM |
| Backend | FastAPI + aiosqlite |
| Frontend | Next.js 15 + shadcn/ui + Recharts + TanStack Query |
| DB | SQLite (company.db 23テーブル) |
| State | Zustand |
| Protocol | MCP (Model Context Protocol) |

## 起動

```bash
# .envにAPIキーを設定
cp .env.example .env
# ANTHROPIC_API_KEY=sk-ant-xxx を設定

# 起動（バックエンド + フロントエンド を同時起動）
bash start.sh
```

アクセス先:
- **Dashboard**: http://localhost:3000
- **API Docs**: http://localhost:8000/docs
- **MCP Server**: http://localhost:8000/mcp

## ローカルLLM (Ollama)

```bash
# Ollamaインストール後
ollama pull llama3.2
# UIでLLM選択 → "Ollama" を選択
```

## ページ構成

| ページ | 内容 |
|--------|------|
| `/` | KPI・売上グラフ・パイプライン・経費チャート |
| `/chat` | AIチャット（DB参照・SSEストリーミング） |
| `/records` | 90スキルのMarkdown出力閲覧 |
| `/pipeline` | 案件パイプライン一覧 |
| `/contacts` | コンタクト管理 |

## MCP連携 (Claude Code)

`~/.claude/settings.json` に追加:
```json
{
  "mcpServers": {
    "company-os": {
      "url": "http://localhost:8000/mcp"
    }
  }
}
```
