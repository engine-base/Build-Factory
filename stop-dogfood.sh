#!/usr/bin/env bash
# stop-dogfood.sh — Phase 1 dogfood の backend + cloudflared を停止
#
# Usage:
#   bash stop-dogfood.sh

set -e
cd "$(dirname "$0")"

G='\033[0;32m'; N='\033[0m'

echo "▶ stopping backend + cloudflared..."

# pid file 経由で kill (graceful)
for pidfile in .uvicorn.pid .cloudflared.pid; do
  if [ -f "$pidfile" ]; then
    pid=$(cat "$pidfile")
    if kill "$pid" 2>/dev/null; then
      echo -e "${G}✓${N} stopped ${pidfile%.pid} (PID $pid)"
    fi
    rm -f "$pidfile"
  fi
done

# 念のため pkill (pidfile 無い場合)
pkill -f "uvicorn.*8001" 2>/dev/null && echo "  + killed leftover uvicorn" || true
pkill -f "cloudflared.*tunnel" 2>/dev/null && echo "  + killed leftover cloudflared" || true

echo -e "\n${G}✓${N} all stopped"
