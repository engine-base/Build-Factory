#!/usr/bin/env bash
# Build-Factory 完了判定スクリプト (Single Source of Truth)
#
# IMPLEMENTATION_PROTOCOL.md Step 6 / 7 を機械的に強制する。
# このスクリプトの全項目が PASS / SKIP-WITH-REASON のいずれかになるまで
# 「タスク完了」と報告してはならない。N/A は禁止。
#
# 検査対象:
#   1. 構造 lint     (絵文字 / AGPL / ARCHIVE 残留 / tickets メタ)
#   2. Python syntax (backend/ 全 .py を ast.parse)
#   3. Backend smoke (main:app が import できるか / onlook routes 残存ゼロ)
#   4. Frontend tsc  (変更ファイルに新規 TS エラーが出ていないか)
#
# 結果は .last-precommit-check に JSON で記録する。
# .claude/settings.json の hook がこのファイルを参照し、commit 前に未実行なら警告。
#
# Usage:
#   bash scripts/pre-commit-check.sh           # フル実行
#   bash scripts/pre-commit-check.sh --quick   # tsc を skip (作業中の高速チェック)
#   bash scripts/pre-commit-check.sh --strict  # 1 つでも SKIP があれば exit 2

set -uo pipefail
cd "$(dirname "$0")/.."

RED='\033[0;31m'
YEL='\033[0;33m'
GRN='\033[0;32m'
DIM='\033[0;90m'
NC='\033[0m'

MODE="${1:-full}"
STAMP_FILE=".last-precommit-check"
RESULT_LINES=()
EXIT_CODE=0
SKIP_COUNT=0

print_step() {
  local status="$1"; local name="$2"; local detail="${3:-}"
  case "$status" in
    PASS) echo -e "  [${GRN}PASS${NC}] $name ${DIM}$detail${NC}" ;;
    FAIL) echo -e "  [${RED}FAIL${NC}] $name ${detail}" ;;
    SKIP) echo -e "  [${YEL}SKIP${NC}] $name ${detail}" ;;
  esac
  RESULT_LINES+=("$(printf '{"step":"%s","status":"%s","detail":"%s"}' "$name" "$status" "${detail//\"/\'}")")
}

# ----------------------------------------------------------------
# Step 1. 構造 lint (lint-mock.sh のサブチェック単位)
#   厳格 (FAIL = exit 1):
#     - AGPL: ライセンス違反は SaaS 提供で許容できないため絶対 NG
#     - ARCHIVE: 削除済みコンポーネント (onlook 等) の参照残留は新規導入禁止
#   寛容 (ベースライン超過のみ FAIL):
#     - emoji: 既存違反が ~200 件あるため別タスクで段階解消 (ADR-005)
#     - tickets: 既存メタ不足が 147/165 あるため別タスクで段階補完
# ----------------------------------------------------------------
echo "[1/4] 構造 lint (AGPL / ARCHIVE: 厳格 / emoji / tickets: ベースライン)"
LINT_LOG=/tmp/precommit-lint.log
: > "$LINT_LOG"

# 厳格モード
if bash scripts/lint-mock.sh --agpl >> "$LINT_LOG" 2>&1; then
  print_step PASS "lint-agpl"
else
  print_step FAIL "lint-agpl" "AGPL 依存が検出されました — CLAUDE.md §3 / ADR 違反"
  EXIT_CODE=1
fi
if bash scripts/lint-mock.sh --archive >> "$LINT_LOG" 2>&1; then
  print_step PASS "lint-archive"
else
  print_step FAIL "lint-archive" "ARCHIVE 残留参照が検出されました"
  EXIT_CODE=1
fi

# 寛容モード (ベースラインと比較)
EMOJI_BASELINE_FILE=".lint-baseline-emoji"
EMOJI_BASE=0; [ -f "$EMOJI_BASELINE_FILE" ] && EMOJI_BASE=$(cat "$EMOJI_BASELINE_FILE")
EMOJI_OUT=$(bash scripts/lint-mock.sh --emoji 2>&1)
EMOJI_LINES=$(echo "$EMOJI_OUT" | grep -cE "^[A-Za-z0-9_./-]+:[0-9]+:" || true)
EMOJI_OVERFLOW=$(echo "$EMOJI_OUT" | grep -oE "他 [0-9]+ 件" | grep -oE "[0-9]+" | head -1)
[ -z "$EMOJI_OVERFLOW" ] && EMOJI_OVERFLOW=0
EMOJI_NOW=$((EMOJI_LINES + EMOJI_OVERFLOW))
if [ "$EMOJI_NOW" -le "$EMOJI_BASE" ]; then
  print_step PASS "lint-emoji" "($EMOJI_NOW <= baseline $EMOJI_BASE)"
else
  print_step FAIL "lint-emoji" "($EMOJI_NOW > baseline $EMOJI_BASE) — 新規絵文字が導入されました (ADR-005 違反)"
  EXIT_CODE=1
fi

TIX_BASELINE_FILE=".lint-baseline-tickets"
TIX_BASE=999; [ -f "$TIX_BASELINE_FILE" ] && TIX_BASE=$(cat "$TIX_BASELINE_FILE")
TIX_NOW=$(python3 scripts/validate-tickets.py 2>&1 | grep -oE "[0-9]+/[0-9]+ tickets need updates" | head -1 | awk -F/ '{print $1}' | tr -d '\n')
[ -z "$TIX_NOW" ] && TIX_NOW=0
if [ "$TIX_NOW" -le "$TIX_BASE" ]; then
  print_step PASS "lint-tickets" "($TIX_NOW <= baseline $TIX_BASE)"
else
  print_step FAIL "lint-tickets" "($TIX_NOW > baseline $TIX_BASE) — 新規メタ不足が増えました"
  EXIT_CODE=1
fi

# ----------------------------------------------------------------
# Step 2. Python syntax
# ----------------------------------------------------------------
echo "[2/4] Python syntax (backend/)"
if [ -d backend ]; then
  PY_FAILS=$(find backend -name '*.py' -not -path '*/__pycache__/*' \
    -exec python3 -c "import ast,sys; [ast.parse(open(f).read(),f) for f in sys.argv[1:]]" {} + 2>&1 | head -10)
  if [ -z "$PY_FAILS" ]; then
    PY_COUNT=$(find backend -name '*.py' -not -path '*/__pycache__/*' | wc -l)
    print_step PASS "python-syntax" "($PY_COUNT files)"
  else
    print_step FAIL "python-syntax" "$PY_FAILS"
    EXIT_CODE=1
  fi
else
  print_step SKIP "python-syntax" "(no backend/)"
  SKIP_COUNT=$((SKIP_COUNT+1))
fi

# ----------------------------------------------------------------
# Step 3. Backend smoke (main:app import + 削除済み参照ゼロ)
# ----------------------------------------------------------------
echo "[3/4] Backend smoke (main:app import + ARCHIVE 残存ゼロ)"
if [ -f backend/main.py ]; then
  SMOKE=$(cd backend && python3 -c "
import sys, json
sys.path.insert(0, '.')
try:
    import main as m
    paths = sorted({getattr(r,'path','') for r in m.app.routes})
    leftover = [p for p in paths if 'onlook' in p.lower()]
    print(json.dumps({'ok': not leftover, 'routes': len(paths), 'leftover_onlook': leftover}))
except ModuleNotFoundError as e:
    print(json.dumps({'ok': None, 'reason': f'missing_dep: {e.name}'}))
except Exception as e:
    print(json.dumps({'ok': False, 'reason': f'{type(e).__name__}: {e}'}))
" 2>&1 | tail -1)
  if echo "$SMOKE" | grep -q '"ok": true'; then
    ROUTES=$(echo "$SMOKE" | python3 -c "import json,sys; print(json.load(sys.stdin)['routes'])")
    print_step PASS "backend-smoke" "($ROUTES routes, no onlook)"
  elif echo "$SMOKE" | grep -q '"ok": null'; then
    REASON=$(echo "$SMOKE" | python3 -c "import json,sys; print(json.load(sys.stdin)['reason'])")
    print_step SKIP "backend-smoke" "依存未インストール: $REASON  →  pip install -r backend/requirements.txt"
    SKIP_COUNT=$((SKIP_COUNT+1))
  else
    print_step FAIL "backend-smoke" "$SMOKE"
    EXIT_CODE=1
  fi
else
  print_step SKIP "backend-smoke" "(no backend/main.py)"
  SKIP_COUNT=$((SKIP_COUNT+1))
fi

# ----------------------------------------------------------------
# Step 4. Frontend tsc (changed files only — baseline errors not allowed to grow)
# ----------------------------------------------------------------
if [ "$MODE" = "--quick" ]; then
  print_step SKIP "frontend-tsc" "(--quick 指定)"
  SKIP_COUNT=$((SKIP_COUNT+1))
elif [ -d frontend ] && [ -f frontend/package.json ]; then
  echo "[4/4] Frontend tsc --noEmit (baseline diff)"
  if [ ! -d frontend/node_modules ]; then
    print_step SKIP "frontend-tsc" "node_modules 未インストール  →  cd frontend && pnpm install"
    SKIP_COUNT=$((SKIP_COUNT+1))
  else
    TSC_OUT=$(cd frontend && pnpm exec tsc --noEmit 2>&1 | grep -E "^src/.*error TS" || true)
    NEW_ERR_COUNT=$(echo "$TSC_OUT" | grep -c "^src/" || true)
    BASELINE_FILE=".tsc-baseline"
    BASELINE=0
    [ -f "$BASELINE_FILE" ] && BASELINE=$(cat "$BASELINE_FILE")
    if [ "$NEW_ERR_COUNT" -le "$BASELINE" ]; then
      print_step PASS "frontend-tsc" "($NEW_ERR_COUNT errors, baseline=$BASELINE)"
    else
      print_step FAIL "frontend-tsc" "($NEW_ERR_COUNT > baseline $BASELINE) — 新規 TS エラーが導入されました"
      echo "$TSC_OUT" | head -10 | sed 's/^/    /'
      EXIT_CODE=1
    fi
  fi
else
  print_step SKIP "frontend-tsc" "(no frontend/)"
  SKIP_COUNT=$((SKIP_COUNT+1))
fi

# ----------------------------------------------------------------
# 結果記録
# ----------------------------------------------------------------
{
  echo "{"
  echo "  \"timestamp\": \"$(date -u +%Y-%m-%dT%H:%M:%SZ)\","
  echo "  \"git_head\": \"$(git rev-parse --short HEAD 2>/dev/null || echo unknown)\","
  echo "  \"working_tree_clean\": $([ -z "$(git status --porcelain 2>/dev/null)" ] && echo true || echo false),"
  echo "  \"exit_code\": $EXIT_CODE,"
  echo "  \"skip_count\": $SKIP_COUNT,"
  echo "  \"results\": ["
  IFS=',' ; echo "    ${RESULT_LINES[*]}" ; unset IFS
  echo "  ]"
  echo "}"
} > "$STAMP_FILE"

echo
if [ "$EXIT_CODE" -eq 0 ] && [ "$SKIP_COUNT" -eq 0 ]; then
  echo -e "${GRN}✔ 全項目 PASS${NC} — このタスクは完了報告可能です。"
elif [ "$EXIT_CODE" -eq 0 ] && [ "$SKIP_COUNT" -gt 0 ]; then
  if [ "$MODE" = "--strict" ]; then
    echo -e "${RED}✘ SKIP が ${SKIP_COUNT} 件あります (--strict)${NC} — 環境を整えて再実行してください。"
    exit 2
  fi
  echo -e "${YEL}△ SKIP が ${SKIP_COUNT} 件あります${NC} — 完了報告には SKIP の理由 (依存未インストール 等) を明記すること。"
  echo -e "${DIM}  記録: $STAMP_FILE${NC}"
else
  echo -e "${RED}✘ FAIL あり${NC} — 修正してから再実行してください。"
  exit "$EXIT_CODE"
fi
