#!/usr/bin/env bash
# fix-and-restart-dogfood.sh
#   1. .env を pooler URL に修正 (既存 secret は温存)
#   2. dogfood 再起動
#   3. Tunnel URL を抽出
#   4. Vercel env を Tunnel URL に差し替え
#   5. vercel deploy --prod
#
# 使い方:
#   cd ~/Documents/Build-Factory
#   git pull
#   bash scripts/fix-and-restart-dogfood.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

G='\033[0;32m'; R='\033[0;31m'; Y='\033[0;33m'; N='\033[0m'
step() { echo -e "\n${G}▶${N} $1"; }
warn() { echo -e "${Y}⚠${N} $1"; }
err()  { echo -e "${R}✗${N} $1" >&2; exit 1; }

POOLER_URL="postgresql://postgres.xyqdwremtusadozuicvg:Y8v%21qK2m%23R7pLx9%40aN4z@aws-1-ap-northeast-1.pooler.supabase.com:5432/postgres"
SUPABASE_URL_VALUE="https://xyqdwremtusadozuicvg.supabase.co"

# ────────────────────────────────────────────────────────────
# 1. .env 検証 + 修正
# ────────────────────────────────────────────────────────────
step "1. .env を pooler URL に修正"

[ -f .env ] || err ".env がない. 先に .env を作成してください."

BACKUP=".env.backup.$(date +%s)"
cp .env "$BACKUP"
echo "  backup: $BACKUP"

# DATABASE_URL と SUPABASE_URL の行を削除 → 先頭に正しい値で追加
grep -v "^DATABASE_URL=" .env | grep -v "^SUPABASE_URL=" > .env.tmp
{
  echo "SUPABASE_URL=$SUPABASE_URL_VALUE"
  echo "DATABASE_URL=$POOLER_URL"
  cat .env.tmp
} > .env
rm -f .env.tmp

# 検証
DB_COUNT=$(grep -c "^DATABASE_URL=" .env || true)
SU_COUNT=$(grep -c "^SUPABASE_URL=" .env || true)
HAS_POOLER=$(grep -q "pooler.supabase.com" .env && echo YES || echo NO)
HAS_OLD=$(grep -q "@db\.xyqdwremtusadozuicvg" .env && echo YES || echo NO)

echo "  DATABASE_URL count: $DB_COUNT (expect 1)"
echo "  SUPABASE_URL count: $SU_COUNT (expect 1)"
echo "  Pooler present:     $HAS_POOLER (expect YES)"
echo "  Old direct present: $HAS_OLD (expect NO)"

[ "$DB_COUNT" = "1" ] || err ".env DATABASE_URL count != 1"
[ "$SU_COUNT" = "1" ] || err ".env SUPABASE_URL count != 1"
[ "$HAS_POOLER" = "YES" ] || err ".env pooler URL not present"
[ "$HAS_OLD" = "NO" ] || err ".env still has old direct URL"

# 他必須キー (JWT_SECRET / ANTHROPIC_API_KEY 等) は温存されているはず
for k in SUPABASE_PUBLISHABLE_KEY SUPABASE_SECRET_KEY SUPABASE_ANON_KEY SUPABASE_SERVICE_KEY SUPABASE_JWT_SECRET ANTHROPIC_API_KEY; do
  if ! grep -q "^${k}=" .env; then
    err ".env に ${k}= が無い (backup: $BACKUP)"
  fi
done

echo -e "${G}✓${N} .env OK"

# ────────────────────────────────────────────────────────────
# 2. 既存プロセス kill
# ────────────────────────────────────────────────────────────
step "2. 既存 uvicorn / cloudflared を kill"
pkill -f "uvicorn.*8001" 2>/dev/null || true
pkill -f "cloudflared.*tunnel" 2>/dev/null || true
sleep 2
echo -e "${G}✓${N} kill done"

# ────────────────────────────────────────────────────────────
# 3. dogfood 起動 (supabase link は実行済前提で y を自動応答)
# ────────────────────────────────────────────────────────────
step "3. start-dogfood.sh 実行"
echo "y" | bash start-dogfood.sh || err "start-dogfood.sh が失敗 (.uvicorn.log / .cloudflared.log 確認)"

# ────────────────────────────────────────────────────────────
# 4. Tunnel URL 抽出
# ────────────────────────────────────────────────────────────
step "4. Tunnel URL 抽出"
TUNNEL_URL=$(grep -oE "https://[a-z0-9-]+\.trycloudflare\.com" .cloudflared.log | head -1)
[ -n "$TUNNEL_URL" ] || err "Tunnel URL が取れない (.cloudflared.log 確認)"
echo -e "${G}✓${N} Tunnel: $TUNNEL_URL"

# ────────────────────────────────────────────────────────────
# 5. backend health check
# ────────────────────────────────────────────────────────────
step "5. backend health check"
sleep 3
HEALTH=$(curl -s -o /dev/null -w "%{http_code}" "$TUNNEL_URL/api/health" || echo "000")
if [ "$HEALTH" = "200" ] || [ "$HEALTH" = "404" ]; then
  echo -e "${G}✓${N} backend reachable (HTTP $HEALTH)"
else
  warn "backend health = $HEALTH (継続するが Vercel から呼べないかも)"
fi

# ────────────────────────────────────────────────────────────
# 6. Vercel env 更新
# ────────────────────────────────────────────────────────────
step "6. Vercel env (NEXT_PUBLIC_API_URL) を更新"

if ! command -v vercel &> /dev/null; then
  warn "vercel CLI が無い. 手動で env 更新してください:"
  echo "  vercel env rm NEXT_PUBLIC_API_URL production"
  echo "  vercel env add NEXT_PUBLIC_API_URL production"
  echo "  値: $TUNNEL_URL"
  echo "  Sensitive: n"
  echo "  vercel deploy --prod"
  exit 0
fi

# 既存削除 (失敗しても続行)
vercel env rm NEXT_PUBLIC_API_URL production --yes 2>&1 | tail -3 || true

# 追加: 値を stdin から / sensitivity 質問にも "n" 応答
# 形式: <URL>\n<sensitive_answer>\n
printf "%s\nn\n" "$TUNNEL_URL" | vercel env add NEXT_PUBLIC_API_URL production 2>&1 | tail -5 || {
  warn "vercel env add が失敗. 手動で実行してください:"
  echo "  vercel env add NEXT_PUBLIC_API_URL production"
  echo "  値: $TUNNEL_URL"
  echo "  Sensitive: n"
  echo "  vercel deploy --prod"
  exit 1
}
echo -e "${G}✓${N} env updated"

# ────────────────────────────────────────────────────────────
# 7. Vercel deploy
# ────────────────────────────────────────────────────────────
step "7. Vercel deploy --prod"
vercel deploy --prod || err "vercel deploy --prod が失敗"

# ────────────────────────────────────────────────────────────
# 8. 完了
# ────────────────────────────────────────────────────────────
step "8. 完了 🎉"

cat << EOF

═══════════════════════════════════════════════════════════════════════
  Tunnel URL  : $TUNNEL_URL
  Vercel URL  : https://build-factory-nine.vercel.app/
═══════════════════════════════════════════════════════════════════════

【動作確認】
$ curl $TUNNEL_URL/api/health
→ ブラウザで https://build-factory-nine.vercel.app/ を開く

【停止】
$ bash stop-dogfood.sh

【⚠️ secret rotation 推奨】
チャット履歴に貼った以下を後で rotate:
  - SUPABASE_SECRET_KEY  → https://supabase.com/dashboard/project/xyqdwremtusadozuicvg/settings/api
  - SUPABASE_JWT_SECRET  → 同上
  - DB password           → 同上 (Database → Reset password)
  - ANTHROPIC_API_KEY     → https://console.anthropic.com/settings/keys
  - SUPABASE_ACCESS_TOKEN → https://supabase.com/dashboard/account/tokens

EOF
