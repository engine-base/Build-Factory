#!/bin/bash
# Company OS Dashboard — 起動スクリプト
set -e

ROOT="$(cd "$(dirname "$0")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
LOG="$ROOT/logs"
mkdir -p "$LOG"

# ── Python venv ────────────────────────────────────────────────────────────
if [ ! -d "$ROOT/.venv" ]; then
  echo "📦 Python仮想環境を作成中..."
  python3 -m venv "$ROOT/.venv"
fi
source "$ROOT/.venv/bin/activate"

# ── Install Python deps ────────────────────────────────────────────────────
pip install -q -r "$BACKEND/requirements.txt"

# ── Install Node deps ─────────────────────────────────────────────────────
if [ ! -d "$FRONTEND/node_modules" ]; then
  echo "📦 Node.jsパッケージをインストール中..."
  cd "$FRONTEND" && npm install --silent
fi

# ── Start Backend ──────────────────────────────────────────────────────────
echo "🚀 バックエンド起動中 (port 8001)..."
cd "$BACKEND"
uvicorn main:app --host 0.0.0.0 --port 8001 --reload > "$LOG/backend.log" 2>&1 &
BACKEND_PID=$!

# ── Start Frontend ─────────────────────────────────────────────────────────
echo "🚀 フロントエンド起動中 (port 3001)..."
cd "$FRONTEND"
npm run dev > "$LOG/frontend.log" 2>&1 &
FRONTEND_PID=$!

# ── Wait ────────────────────────────────────────────────────────────────────
echo ""
echo "✅ 起動完了！"
echo "   Dashboard:  http://localhost:3001"
echo "   API Docs:   http://localhost:8001/docs"
echo "   MCP:        http://localhost:8001/mcp"
echo ""
echo "停止: Ctrl+C"

cleanup() {
  echo "🛑 停止中..."
  kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
  exit 0
}
trap cleanup INT TERM
wait
