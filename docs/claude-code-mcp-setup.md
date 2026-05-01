# Claude Code MCP 接続設定

Claude Code から Build-Factory の `bf_*` ツールを使うための設定。

## 前提

- Build-Factory backend が起動済 (`http://localhost:8001`)
- Claude Code CLI または Desktop アプリがインストール済
- Build-Factory のリポジトリパス: `~/Documents/Build-Factory`

## 設定方法

### 方法 A: Claude Code CLI（プロジェクト単位）

Build-Factory プロジェクトで作業する場合に推奨。
リポジトリ内 `.mcp.json` で Claude Code が自動認識する。

`.mcp.json` を Build-Factory ルートに配置（同梱済）:

```json
{
  "mcpServers": {
    "build-factory": {
      "command": "/Users/masato0420/Documents/Build-Factory/backend/.venv/bin/python3",
      "args": ["/Users/masato0420/Documents/Build-Factory/backend/mcp_stdio_server.py"],
      "env": {
        "PYTHONPATH": "/Users/masato0420/Documents/Build-Factory/backend"
      }
    }
  }
}
```

Claude Code CLI を Build-Factory 配下で起動すれば自動で接続される:
```bash
cd ~/Documents/Build-Factory
claude
# → mcp サーバーが起動・bf_* tools 利用可能
```

### 方法 B: Claude Desktop アプリ（グローバル）

`~/Library/Application Support/Claude/claude_desktop_config.json` に追記:

```json
{
  "mcpServers": {
    "build-factory": {
      "command": "/Users/masato0420/Documents/Build-Factory/backend/.venv/bin/python3",
      "args": ["/Users/masato0420/Documents/Build-Factory/backend/mcp_stdio_server.py"],
      "env": {
        "PYTHONPATH": "/Users/masato0420/Documents/Build-Factory/backend"
      }
    }
  }
}
```

Claude Desktop を再起動。

## 提供される MCP ツール

### Build-Factory 開発フロー連携 (`bf_*`)

| ツール | 用途 |
|---|---|
| `bf_list_workspaces` | account 配下の workspace 一覧 |
| `bf_get_workspace` | workspace 詳細（design_system_ref / project_meta） |
| `bf_list_tasks` | タスク一覧 |
| `bf_get_next_task` | 次にやるべきタスク 1 件（Planner の入口） |
| `bf_get_spec` | タスクの仕様書パッケージ + 関連 artifact + design_md |
| `bf_load_skill` | SKILL.md 全文ロード |
| `bf_list_design_systems` | Open Design 取り込みの 129 デザインシステム |
| `bf_post_progress` | タスク進捗書き戻し |
| `bf_attach_artifact` | 成果物（15 view 型）を artifact 化 |
| `bf_request_review` | レビュアー AI（リン）に壁打ち依頼 |
| `bf_get_review_feedback` | レビュー結果取得 |

### Build-Factory 既存ツール

| ツール | 用途 |
|---|---|
| `query_company_db` | DB に SELECT クエリ |
| `get_company_kpi` | KPI サマリ |
| `list_skills` / `get_skill` / `create_skill` | スキル管理 |
| `list_artifacts` / `get_artifact` / `update_artifact` | artifact 操作 |
| `sync_obsidian_now` | Obsidian 同期（任意） |

## 動作確認

### 1. mcp_stdio_server を直接起動して動作確認

```bash
cd ~/Documents/Build-Factory/backend
source .venv/bin/activate
PYTHONPATH=. python mcp_stdio_server.py
# → stdio で待機状態に入る・Ctrl+C で終了
```

### 2. Claude Code から呼び出し

Claude Code 内で:

```
ユーザー: 「Build-Factory のワークスペース一覧を見せて」

Claude Code:
  bf_list_workspaces(account_id=1) を実行
  → [{id: 1, name: "Build-Factory 初期 Workspace", status: "active"}]
  返答: ENGINE BASE に 1 つのワークスペースがあります...
```

```
ユーザー: 「次のタスクをやろう」

Claude Code:
  bf_get_next_task(workspace_id=1) を実行
  → 結果に基づき bf_get_spec(task_id) で詳細取得
  → 実装・テスト
  → bf_post_progress / bf_attach_artifact で書き戻し
  → bf_request_review で レビュアー AI に依頼
```

## トラブルシューティング

### MCP server が起動しない

```bash
# venv の python があるか確認
ls ~/Documents/Build-Factory/backend/.venv/bin/python3

# 直接実行してエラー確認
cd ~/Documents/Build-Factory/backend
source .venv/bin/activate
PYTHONPATH=. python mcp_stdio_server.py
```

### tools が認識されない

Claude Code CLI / Desktop を完全終了→再起動。
`.mcp.json` の絶対パスが正しいか確認。

### DB エラー

```bash
# DB の存在確認
ls -la ~/Documents/Build-Factory/data/db/build.db

# テーブルが揃ってるか
sqlite3 ~/Documents/Build-Factory/data/db/build.db ".tables"

# 不足してたら migrate
cd ~/Documents/Build-Factory/backend
source .venv/bin/activate
.venv/bin/alembic upgrade head
```
