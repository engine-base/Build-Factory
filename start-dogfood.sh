#!/usr/bin/env bash
# start-dogfood.sh — Phase 1 dogfood セットアップを 1 コマンドで起動
#
# Usage:
#   cd ~/Documents/Build-Factory
#   bash start-dogfood.sh
#
# 前提:
#   - macOS / Linux (bash 4+)
#   - Python 3.11.5+ (brew install python@3.11)
#   - Homebrew (mac)
#   - .env が repo root に置かれている (必須キー埋まっている事)
#
# 何をする:
#   1. backend venv + deps install (初回のみ)
#   2. supabase CLI install (初回のみ)
#   3. supabase db push (migrations 適用)
#   4. cloudflared install (初回のみ)
#   5. backend uvicorn 起動 (background)
#   6. cloudflared quick tunnel 起動 (background)
#   7. tunnel URL を表示
#
# 停止: bash stop-dogfood.sh (or `pkill -f uvicorn; pkill -f cloudflared`)

set -e

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$REPO_ROOT"

# ANSI colors
G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; D='\033[0;90m'; N='\033[0m'

step() { echo -e "\n${G}▶${N} $1"; }
warn() { echo -e "${Y}⚠${N} $1"; }
err()  { echo -e "${R}✗${N} $1" >&2; exit 1; }

# ────────────────────────────────────────────────────────────
# 0. .env 必須キー check
# ────────────────────────────────────────────────────────────
step "0. .env 必須キーチェック"

if [ ! -f .env ]; then
  err ".env がない. 先に作成してください (docs/PHASE1_DOGFOOD_SETUP.md 参照)"
fi

for k in SUPABASE_URL SUPABASE_ANON_KEY SUPABASE_SERVICE_KEY SUPABASE_JWT_SECRET DATABASE_URL ANTHROPIC_API_KEY; do
  if ! grep -q "^${k}=" .env || grep -q "^${k}=REPLACE\|^${k}=dummy\|^${k}=$" .env; then
    err ".env の ${k} が未設定 (REPLACE_ME / dummy / 空). 編集してから再実行: nano .env"
  fi
done

# DATABASE_URL に password の URL encode 漏れがないか check
# (Y8v!qK2m#R7pLx9@aN4z が含まれていれば未エンコード)
if grep -q "Y8v!qK2m#R7pLx9@aN4z" .env; then
  warn ".env の DATABASE_URL に password が URL encode されてない可能性. 修正:"
  echo "  DATABASE_URL=postgresql://postgres:Y8v%21qK2m%23R7pLx9%40aN4z@db.xyqdwremtusadozuicvg.supabase.co:5432/postgres"
  err "DATABASE_URL を上記に書き換えて再実行"
fi

echo -e "${G}✓${N} .env OK"

# ────────────────────────────────────────────────────────────
# 1. Backend venv + deps
# ────────────────────────────────────────────────────────────
step "1. Backend venv + deps install"

cd backend
if [ ! -d .venv ]; then
  python3.11 -m venv .venv || err "python3.11 がない. brew install python@3.11"
fi

source .venv/bin/activate
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
echo -e "${G}✓${N} backend venv ready"

cd "$REPO_ROOT"

# ────────────────────────────────────────────────────────────
# 2. Supabase CLI install + login + link
# ────────────────────────────────────────────────────────────
step "2. Supabase CLI 確認"

if ! command -v supabase &> /dev/null; then
  echo "Installing supabase CLI..."
  brew install supabase/tap/supabase || err "supabase CLI install 失敗"
fi
echo -e "${G}✓${N} supabase CLI: $(supabase --version)"

# project link (idempotent)
PROJECT_REF="xyqdwremtusadozuicvg"
if [ ! -f .supabase/.temp/project-ref ] || [ "$(cat .supabase/.temp/project-ref 2>/dev/null)" != "$PROJECT_REF" ]; then
  warn "supabase project link が未実行. 以下を手動で実行してください:"
  echo ""
  echo "    supabase link --project-ref $PROJECT_REF"
  echo ""
  echo "    (password 聞かれる → .env の DATABASE_URL に書いてある password を URL decode した値を入力)"
  echo "    例: Y8v%21qK2m%23R7pLx9%40aN4z → Y8v!qK2m#R7pLx9@aN4z"
  echo ""
  read -p "実行しましたか? (y/n) " ans
  [ "$ans" != "y" ] && err "supabase link を実行してから再試行"
fi

# ────────────────────────────────────────────────────────────
# 3. migrations apply
# ────────────────────────────────────────────────────────────
step "3. Supabase migrations apply (22 件)"

# db push (冪等)
supabase db push --include-all 2>&1 | tail -10 || warn "supabase db push が一部失敗 (既に apply 済の可能性)"
echo -e "${G}✓${N} migrations applied"

# ────────────────────────────────────────────────────────────
# 4. cloudflared install
# ────────────────────────────────────────────────────────────
step "4. cloudflared 確認"

if ! command -v cloudflared &> /dev/null; then
  brew install cloudflared || err "cloudflared install 失敗"
fi
echo -e "${G}✓${N} cloudflared: $(cloudflared --version | head -1)"

# ────────────────────────────────────────────────────────────
# 5. Backend uvicorn 起動 (background)
# ────────────────────────────────────────────────────────────
step "5. Backend uvicorn 起動 (background)"

# 既存 process kill
pkill -f "uvicorn.*8001" 2>/dev/null || true
sleep 1

cd backend
source .venv/bin/activate
nohup uvicorn main:app --host 127.0.0.1 --port 8001 > "$REPO_ROOT/.uvicorn.log" 2>&1 &
UVICORN_PID=$!
cd "$REPO_ROOT"
echo "$UVICORN_PID" > .uvicorn.pid

# 起動待ち (最大 30 秒)
for i in {1..30}; do
  if curl -sS http://127.0.0.1:8001/api/health -o /dev/null -w "%{http_code}" 2>/dev/null | grep -q "200\|404"; then
    echo -e "${G}✓${N} uvicorn started (PID $UVICORN_PID)"
    break
  fi
  sleep 1
  if [ "$i" -eq 30 ]; then
    err "uvicorn 起動 timeout. ログ確認: tail -30 .uvicorn.log"
  fi
done

# ────────────────────────────────────────────────────────────
# 6. cloudflared quick tunnel 起動 (background)
# ────────────────────────────────────────────────────────────
step "6. cloudflared quick tunnel 起動 (background)"

pkill -f "cloudflared.*tunnel" 2>/dev/null || true
sleep 1

nohup cloudflared tunnel --url http://localhost:8001 > .cloudflared.log 2>&1 &
CF_PID=$!
echo "$CF_PID" > .cloudflared.pid

# URL 取得 (最大 30 秒)
TUNNEL_URL=""
for i in {1..30}; do
  TUNNEL_URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" .cloudflared.log | head -1)
  if [ -n "$TUNNEL_URL" ]; then
    break
  fi
  sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
  err "tunnel URL 取得失敗. ログ確認: tail -30 .cloudflared.log"
fi

echo -e "${G}✓${N} cloudflared tunnel ready (PID $CF_PID)"

# ────────────────────────────────────────────────────────────
# 7. 完了
# ────────────────────────────────────────────────────────────
step "7. Phase 1 dogfood セットアップ完了 🎉"

cat << EOF

═══════════════════════════════════════════════════════════════════════
  Tunnel URL: ${TUNNEL_URL}
═══════════════════════════════════════════════════════════════════════

【次の作業】
1. Vercel ダッシュボードで Settings → Environment Variables を開く
2. NEXT_PUBLIC_API_URL を上記の Tunnel URL に設定 (置換)
3. Deployments → 最新の Redeploy (Use existing build cache: OFF)
4. デプロイ完了後、Vercel URL を開いて dogfood 開始

【動作確認】
$ curl ${TUNNEL_URL}/api/health
# → JSON が返れば成功

【停止】
$ bash stop-dogfood.sh
or
$ kill \$(cat .uvicorn.pid) \$(cat .cloudflared.pid)

【ログ】
- backend:     tail -f .uvicorn.log
- cloudflared: tail -f .cloudflared.log

EOF
