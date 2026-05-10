#!/bin/bash
# Build-Factory モック / コード lint
#
# 検出するもの:
#   1. 絵文字の混入 (Lucide のみ許可)
#   2. AGPL ライセンスパッケージ
#   3. 未使用の onlook / penpot 参照
#   4. tickets.json メタ不足 (validate-tickets.py 委譲)
#   5. 実鍵リーク (Supabase / generic) の検出 (T-001-01 AC-5)
#   6. claude-agent-sdk runner module への LangGraph/LangChain 混入 (T-S0-08 AC-7 / ADR-010)
#
# Usage:
#   bash scripts/lint-mock.sh             # 全チェック
#   bash scripts/lint-mock.sh --emoji     # 絵文字のみ
#   bash scripts/lint-mock.sh --agpl      # AGPL のみ
#   bash scripts/lint-mock.sh --secrets   # 実鍵リークのみ
#   bash scripts/lint-mock.sh --no-langgraph  # runner への LangGraph 混入のみ

set -e
cd "$(dirname "$0")/.."

RED='\033[0;31m'
YELLOW='\033[0;33m'
GREEN='\033[0;32m'
NC='\033[0m'

EXIT_CODE=0
MODE="${1:-all}"

# ----------------------------------------------------------------
# 1. 絵文字検出
# ----------------------------------------------------------------
check_emoji() {
  echo "[1/4] 絵文字検出..."
  # 検出範囲: docs/mocks/ + frontend/src/ + backend/ (生成スクリプトと .git は除く)
  # スクリプト自体は除外
  local violations
  violations=$(python3 - <<'PY'
import re
from pathlib import Path

EMOJI_RE = re.compile(
    r'[\U0001F000-\U0001FFFF\U00002600-\U000027BF\U0001F300-\U0001F9FF'
    r'▲▶▸▼◀◂'  # Geometric Shapes: action triangles ▲ ▶ ▸ ▼ ◀ ◂
    r']'
)
TARGETS = ["docs/mocks", "frontend/src", "backend"]
EXCLUDES = {"scripts/lint-mock.sh", "scripts/validate-tickets.py"}
EXTS = {".html", ".tsx", ".ts", ".jsx", ".js", ".py", ".md"}

# ADR-005 適用範囲外: 外部チャット (Slack/Chatwork) 送信ペイロード。
# 受信側 UI が Lucide をレンダリングできないため絵文字使用を許可。
EMOJI_EXEMPT_FILES = {
    "backend/integrations/slack_block_kit.py",
    "backend/integrations/slack_client.py",
    "backend/integrations/slack_llm_session.py",
    "backend/integrations/chatwork_client.py",
}

found = []
for target in TARGETS:
    p = Path(target)
    if not p.exists():
        continue
    for f in p.rglob("*"):
        if f.suffix not in EXTS:
            continue
        if str(f) in EXCLUDES:
            continue
        if str(f) in EMOJI_EXEMPT_FILES:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except Exception:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            if EMOJI_RE.search(line):
                emojis = EMOJI_RE.findall(line)
                found.append(f"{f}:{line_no}: {' '.join(set(emojis))}")
for v in found:
    print(v)
PY
)
  if [ -n "$violations" ]; then
    echo -e "${RED}NG: 絵文字を検出${NC}"
    echo "$violations" | head -20
    local count
    count=$(echo "$violations" | wc -l)
    if [ "$count" -gt 20 ]; then
      echo "...と他 $((count - 20)) 件"
    fi
    echo "→ Lucide Icons (<i data-lucide=...>) に置換すること (CLAUDE.md §5.1)"
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: 絵文字なし${NC}"
  fi
}

# ----------------------------------------------------------------
# 2. AGPL 依存検出
# ----------------------------------------------------------------
check_agpl() {
  echo "[2/4] AGPL ライセンス依存検出..."
  local found=0

  # frontend (package.json)
  if [ -f frontend/package.json ]; then
    if grep -i "agpl" frontend/package.json > /dev/null 2>&1; then
      echo -e "${RED}NG: frontend/package.json に AGPL の文字${NC}"
      grep -i "agpl" frontend/package.json
      found=1
    fi
  fi

  # backend (pyproject.toml / requirements.txt)
  for f in backend/pyproject.toml backend/requirements.txt pyproject.toml requirements.txt; do
    if [ -f "$f" ]; then
      if grep -i "agpl" "$f" > /dev/null 2>&1; then
        echo -e "${RED}NG: $f に AGPL の文字${NC}"
        grep -i "agpl" "$f"
        found=1
      fi
    fi
  done

  if [ "$found" -eq 0 ]; then
    echo -e "${GREEN}OK: AGPL 依存なし${NC}"
  else
    echo "→ ADR-004 / requirements-v1 の方針で AGPL は SaaS 提供時に問題。代替を検討すること"
    EXIT_CODE=1
  fi
}

# ----------------------------------------------------------------
# 3. ARCHIVE 対象 (onlook / penpot) の残留検出
#    T-019-01 (W-7 Won't: Onlook / Open Design):
#      - onlook/ + penpot/ ディレクトリは AC-1 で削除必須
#      - ソースコード内の onlook 参照は AC-3/4 で削除必須
#      - penpot 統合コードは Phase 1.5 (S-3) で GrapesJS に置換するまで残置
# ----------------------------------------------------------------
check_archive() {
  echo "[3/4] ARCHIVE 対象 (onlook/penpot) 残留検出..."
  local found=0

  # ディレクトリ自体は両方とも削除必須
  for t in onlook penpot; do
    if [ -d "$t" ]; then
      echo -e "${YELLOW}WARN: $t/ ディレクトリが残っている${NC} (T-019-01 ARCHIVE 対象)"
      found=1
    fi
  done

  # ソースコード内の onlook 参照は禁止 (T-019-01 AC-3/4)
  local refs
  refs=$(grep -rn --include="*.ts" --include="*.tsx" --include="*.py" --include="*.js" "onlook" frontend/src backend 2>/dev/null || true)
  if [ -n "$refs" ]; then
    echo -e "${YELLOW}WARN: 'onlook' の参照が残っている:${NC}"
    echo "$refs" | head -5
    found=1
  fi

  if [ "$found" -eq 0 ]; then
    echo -e "${GREEN}OK: ARCHIVE 残留なし${NC}"
  else
    EXIT_CODE=1
  fi
}

# ----------------------------------------------------------------
# 6. claude-agent-sdk runner への LangGraph / LangChain 混入検出
#    T-S0-08 AC-7 + ADR-010: runner module は LangGraph に依存しない
#    対象: claude_agent_runner.py を含む claude-agent-sdk runner ファイル群
# ----------------------------------------------------------------
check_no_langgraph() {
  echo "[6/6] claude-agent-sdk runner の LangGraph/LangChain 混入検出..."
  local targets="backend/integrations/claude_agent_runner.py"
  local found=0
  for f in $targets; do
    if [ ! -f "$f" ]; then continue; fi
    if grep -nE "from langgraph|import langgraph|from langchain|import langchain" "$f" > /dev/null 2>&1; then
      echo -e "${RED}NG: $f に LangGraph/LangChain import (ADR-010 違反)${NC}"
      grep -nE "from langgraph|import langgraph|from langchain|import langchain" "$f"
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo -e "${GREEN}OK: runner module に LangGraph/LangChain 混入なし${NC}"
  else
    echo "→ ADR-010 で LangGraph は main path から削除。Subagent (Task tool) + 自前 state で代替"
    EXIT_CODE=1
  fi
}

# ----------------------------------------------------------------
# 5. 実鍵リーク検出 (T-001-01 AC-5)
#    sb_publishable_<chars> / sb_secret_<chars> パターンが
#    .env.example 以外のコミット対象ファイルに混入していたら FAIL
# ----------------------------------------------------------------
check_secrets() {
  echo "[5/5] 実鍵リーク検出..."
  local pattern='sb_(publishable|secret)_[A-Za-z0-9_-]{20,}'
  # 除外: .env (gitignore済) / .env.example (placeholder のみ許可) / lock files
  local hits
  hits=$(grep -rEn --include="*.py" --include="*.ts" --include="*.tsx" --include="*.js" --include="*.json" --include="*.sh" --include="*.md" --include="*.yaml" --include="*.yml" \
    --exclude-dir=node_modules --exclude-dir=.next --exclude-dir=__pycache__ --exclude-dir=.git \
    "$pattern" . 2>/dev/null | grep -v -E "(^|/)\.env(\.example)?:" | grep -v "REPLACE_WITH_" || true)
  if [ -n "$hits" ]; then
    echo -e "${RED}NG: 実鍵パターン (sb_publishable_*/sb_secret_*) を検出${NC}"
    echo "$hits" | head -10
    echo "→ env 経由で読み込み、コードにハードコードしないこと (CLAUDE.md §5.4)"
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: 実鍵リークなし${NC}"
  fi
}

# ----------------------------------------------------------------
# 4. tickets.json メタ検証
# ----------------------------------------------------------------
check_tickets() {
  echo "[4/4] tickets.json メタ検証..."
  if python3 scripts/validate-tickets.py > /tmp/lint_validate.log 2>&1; then
    echo -e "${GREEN}OK: 全タスクが必須メタを保持${NC}"
  else
    # クリティカルパスのみ FAIL 扱い
    if grep -q "CRITICAL PATH issues" /tmp/lint_validate.log; then
      echo -e "${RED}NG: クリティカルパスのタスクにメタ不足${NC}"
      grep -A 20 "CRITICAL PATH" /tmp/lint_validate.log | head -25
      EXIT_CODE=1
    else
      echo -e "${YELLOW}WARN: 一部の非クリティカルタスクにメタ不足 (実装着手時に補完)${NC}"
      tail -5 /tmp/lint_validate.log
    fi
  fi
}

# ----------------------------------------------------------------
# Dispatch
# ----------------------------------------------------------------
case "$MODE" in
  --emoji)        check_emoji ;;
  --agpl)         check_agpl ;;
  --archive)      check_archive ;;
  --tickets)      check_tickets ;;
  --secrets)      check_secrets ;;
  --no-langgraph) check_no_langgraph ;;
  all|"")
    check_emoji
    check_agpl
    check_archive
    check_tickets
    check_secrets
    check_no_langgraph
    ;;
  *)
    echo "Usage: $0 [--emoji|--agpl|--archive|--tickets|--secrets|--no-langgraph|all]"
    exit 2
    ;;
esac

if [ "$EXIT_CODE" -eq 0 ]; then
  echo -e "\n${GREEN}===== Lint OK =====${NC}"
else
  echo -e "\n${RED}===== Lint Failed =====${NC}"
  echo "違反内容を修正してから再度実行してください。"
fi
exit $EXIT_CODE
