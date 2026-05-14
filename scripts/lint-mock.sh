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
    # ADR-005 適用範囲外 (negative test): 絵文字禁止を pytest で機械検証する
    # テストファイル自体は forbidden char 列を保持する必要がある.
    "backend/tests/test_t_010b_04_play_session_button.py",
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
  # ARCHIVE 検証用 test ファイル (test_supabase_migrations.py /
  # test_t_019_03_bootstrap_health.py / test_t_019_01_archive_invariants.py /
  # test_t_019_01_bootstrap_archive_spec.py (Wave 5 v2 audit) /
  # test_t_s0_13_inventory_invariants.py) は "onlook" 文字列を含むので除外.
  local refs
  refs=$(grep -rn --include="*.ts" --include="*.tsx" --include="*.py" --include="*.js" \
    --exclude="test_supabase_migrations.py" \
    --exclude="test_t_019_03_bootstrap_health.py" \
    --exclude="test_t_019_01_archive_invariants.py" \
    --exclude="test_t_019_01_bootstrap_archive_spec.py" \
    --exclude="test_t_s0_13_inventory_invariants.py" \
    "onlook" frontend/src backend 2>/dev/null || true)
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
# 6. backend メイン経路への LangGraph / LangChain 混入検出
#    T-S0-08 AC-7 + ADR-010: メイン経路は LangGraph に依存しない
#    対象: claude-agent-sdk runner + 会話オーケストレータ + 秘書エージェント
# ----------------------------------------------------------------
check_no_langgraph() {
  echo "[6/11] backend メイン経路の LangGraph/LangChain 混入検出..."
  # T-003-02 AC-5 (#2): handoff path (secretary_chat / delegation_service)
  # に LangGraph / LangChain が紛れ込まないことも機械検知 (ADR-010 §UNWANTED).
  local targets="backend/integrations/claude_agent_runner.py backend/services/orchestrator_graph.py backend/ai_agents/secretary_agent.py backend/services/secretary_chat.py backend/services/delegation_service.py"
  local found=0
  for f in $targets; do
    if [ ! -f "$f" ]; then continue; fi
    if grep -nE "^[[:space:]]*from langgraph|^[[:space:]]*import langgraph|^[[:space:]]*from langchain|^[[:space:]]*import langchain" "$f" > /dev/null 2>&1; then
      echo -e "${RED}NG: $f に LangGraph/LangChain import (ADR-010 違反)${NC}"
      grep -nE "^[[:space:]]*from langgraph|^[[:space:]]*import langgraph|^[[:space:]]*from langchain|^[[:space:]]*import langchain" "$f"
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo -e "${GREEN}OK: backend メイン経路に LangGraph/LangChain 混入なし${NC}"
  else
    echo "→ ADR-010 で LangGraph は main path から削除。Subagent (Task tool) + 自前 state で代替"
    EXIT_CODE=1
  fi
}

# ----------------------------------------------------------------
# 7. claude-runner への LiteLLM 混入検出 (T-M12-01 AC-5 / ADR-010)
#    メイン経路は claude-agent-sdk + anthropic-python のみ。 LiteLLM はサブ用途専用.
# ----------------------------------------------------------------
check_no_litellm_in_runner() {
  echo "[7/7] backend メイン経路の LiteLLM 混入検出..."
  local targets="backend/integrations/claude_agent_runner.py backend/services/orchestrator_graph.py backend/ai_agents/secretary_agent.py"
  local found=0
  for f in $targets; do
    if [ ! -f "$f" ]; then continue; fi
    if grep -nE "^[[:space:]]*from litellm|^[[:space:]]*import litellm" "$f" > /dev/null 2>&1; then
      echo -e "${RED}NG: $f に LiteLLM import (T-M12-01 AC-5 違反 / ADR-010)${NC}"
      grep -nE "^[[:space:]]*from litellm|^[[:space:]]*import litellm" "$f"
      found=1
    fi
  done
  if [ "$found" -eq 0 ]; then
    echo -e "${GREEN}OK: backend メイン経路に LiteLLM 混入なし${NC}"
  else
    echo "→ T-M12-01 / ADR-010: LiteLLM はサブ用途専用 (services/litellm_router.py)。メイン経路は claude-agent-sdk + anthropic-python のみ"
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
check_domain_boundaries() {
  echo "[8/11] backend bounded-context domain barrel + 循環依存検出..."
  if python3 scripts/check-domain-boundaries.py > /tmp/lint_domains.log 2>&1; then
    echo -e "${GREEN}OK: backend/domains/ 13 barrel 健全 (no bypass / no cycle)${NC}"
  else
    cat /tmp/lint_domains.log
    EXIT_CODE=1
  fi
}

# ----------------------------------------------------------------
# 9. T-AI-MEM-04 (ADR-012 Decision 5): provider 切替 routing 自前実装の禁止語検知
#    任意切替 + 障害時 fallback は backend/services/provider_adapter_memory.py
#    の resolve_active_provider() に集約する. 各 router / service が個別に
#    if-elif で provider 文字列分岐する routing を行うのは禁止
#    (provider_adapter / provider_adapter_memory 経由を強制).
# ----------------------------------------------------------------
check_no_self_provider_routing() {
  echo "[9/13] provider 切替 routing 自前実装検知 (T-AI-MEM-04 / ADR-012 Decision 5)..."
  # 禁止語: provider 切替の自前 routing 関数 / private resolver / route hack
  local forbidden_re='\bdef[[:space:]]+(_resolve_provider_locally|_route_to_provider|_custom_provider_switch|_pick_provider_inline|_byok_then_anthropic)\b'
  local hits
  hits=$(grep -rnE "$forbidden_re" \
    --include="*.py" \
    --exclude="provider_adapter_memory.py" \
    --exclude="provider_adapter.py" \
    backend/services backend/routers 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo -e "${RED}NG: provider 切替 routing 自前実装の禁止語 (T-AI-MEM-04 / ADR-012)${NC}"
    echo "$hits"
    echo "→ provider 切替は services/provider_adapter_memory.resolve_active_provider() を経由"
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: provider 切替 routing 自前実装なし${NC}"
  fi
}

# ----------------------------------------------------------------
# 10. T-M28-02 AC-4 UNWANTED: tool result trimming 自前実装の禁止語検知
#     ADR-010: trim 本体は claude-agent-sdk の内蔵機能.
#     app code (backend/services + backend/routers 全般) で size cap / age cap /
#     dedup / truncate / window eviction の自前実装を行わない.
# ----------------------------------------------------------------
check_no_self_tool_trim() {
  echo "[10/13] tool result trim 自前実装検知 (T-M28-02 AC-4)..."
  local forbidden_re='\b(trim_tool_result|_apply_size_cap|_apply_age_cap|_dedup_tool_results|truncate_tool_result|_compute_trimmed_payload|_run_trim_policy|_apply_window_eviction)\b'
  local hits
  hits=$(grep -rnE "$forbidden_re" \
    --include="*.py" \
    backend/services backend/routers 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo -e "${RED}NG: app code に tool trim 自前実装の禁止語 (T-M28-02 AC-4 / ADR-010)${NC}"
    echo "$hits"
    echo "→ trim 本体は claude-agent-sdk 内蔵機能を使う. app 側は record_trim_event audit wrapper のみ"
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: app code (services/routers) に tool trim 自前実装なし${NC}"
  fi
}

# ----------------------------------------------------------------
# 11. T-BTSTRAP-01 AC-4 UNWANTED: templates/project-bootstrap/ 必須ファイル不在検知
#     新規案件作成時に bootstrap で展開される必須スケルトンが欠けていたら lint fail.
#     関連: ADR-009 / M-31 / T-BTSTRAP-02 (WorkspaceService.bootstrap で参照).
# ----------------------------------------------------------------
check_template_skeleton_complete() {
  echo "[11/13] templates/project-bootstrap/ 必須スケルトン完整性検査 (T-BTSTRAP-01 AC-4)..."
  local required=(
    "templates/project-bootstrap/CLAUDE.md.j2"
    "templates/project-bootstrap/docs/HANDOVER.md.j2"
    "templates/project-bootstrap/docs/task-decomposition/IMPLEMENTATION_PROTOCOL.md"
    "templates/project-bootstrap/scripts/lint-mock.sh"
    "templates/project-bootstrap/scripts/validate-tickets.py"
    "templates/project-bootstrap/.claude/settings.json"
    "templates/CHANGELOG.md"
  )
  local missing=()
  for f in "${required[@]}"; do
    if [ ! -f "$f" ]; then
      missing+=("$f")
    fi
  done
  if [ ${#missing[@]} -gt 0 ]; then
    echo -e "${RED}NG: templates/project-bootstrap/ に必須スケルトン欠落 (T-BTSTRAP-01 AC-4)${NC}"
    for f in "${missing[@]}"; do
      echo "  - $f"
    done
    echo "→ T-BTSTRAP-02 の自動展開が失敗する. 全案件への伝播 (T-BTSTRAP-05) も不可能."
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: templates/project-bootstrap/ 必須スケルトン全 ${#required[@]} 件あり${NC}"
  fi
}

# ----------------------------------------------------------------
# 12. T-AI-04 AC-1/4: Constitution 自前 system prompt 組み立て禁止
#     constitution_engine.inject_for_session() 以外で system prompt に
#     "Section 4 red lines" 等の Constitution テキストを直接組み立てる経路は禁止.
# ----------------------------------------------------------------
# ----------------------------------------------------------------
# 13. T-AI-08 AC-UNWANTED: fallback / circuit-breaker 自前実装の禁止語検知
#     services/fallback_router.py + services/circuit_breaker.py 以外で
#     独自の health-check loop / circuit-breaker / failover routing を実装
#     してはならない (ADR-010 + T-AI-08 spec).
# ----------------------------------------------------------------
check_no_self_fallback_circuit() {
  echo "[13/13] fallback / circuit-breaker 自前実装検知 (T-AI-08 AC-UNWANTED)..."
  local forbidden_re='\bdef[[:space:]]+(_custom_health_circuit|_self_failover_loop|_inline_3_strike_fallback|_manual_recovery_streak|_route_to_untested_provider)\b'
  local hits
  hits=$(grep -rnE "$forbidden_re" \
    --include="*.py" \
    --exclude="fallback_router.py" \
    --exclude="circuit_breaker.py" \
    backend/services backend/routers 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo -e "${RED}NG: fallback / circuit-breaker 自前実装の禁止語 (T-AI-08 AC-UNWANTED)${NC}"
    echo "$hits"
    echo "→ fallback は services/fallback_router.record_health_check() 経由のみ. 未テスト provider への routing 禁止"
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: fallback / circuit-breaker 自前実装なし${NC}"
  fi
}

check_no_self_constitution_inject() {
  echo "[12/13] Constitution 自前 inject 検知 (T-AI-04 AC-1/4)..."
  # 禁止語: constitution を自前で system prompt に組み込む関数 / 文字列
  local forbidden_re='\bdef[[:space:]]+(_build_constitution_prompt|_inject_constitution_manually|_compose_red_lines_inline|_manual_constitution_inject)\b'
  local hits
  hits=$(grep -rnE "$forbidden_re" \
    --include="*.py" \
    --exclude="constitution_engine.py" \
    backend/services backend/routers backend/ai_agents backend/integrations 2>/dev/null || true)
  if [ -n "$hits" ]; then
    echo -e "${RED}NG: Constitution 自前 inject の禁止語 (T-AI-04 AC-1/4 / ADR-012)${NC}"
    echo "$hits"
    echo "→ Constitution は services/constitution_engine.inject_for_session() 経由のみ"
    EXIT_CODE=1
  else
    echo -e "${GREEN}OK: Constitution 自前 inject なし${NC}"
  fi
}

case "$MODE" in
  --emoji)        check_emoji ;;
  --agpl)         check_agpl ;;
  --archive)      check_archive ;;
  --tickets)      check_tickets ;;
  --secrets)      check_secrets ;;
  --no-langgraph) check_no_langgraph ;;
  --no-litellm-in-runner) check_no_litellm_in_runner ;;
  --domains)      check_domain_boundaries ;;
  --no-self-provider-routing) check_no_self_provider_routing ;;
  --no-self-tool-trim) check_no_self_tool_trim ;;
  --template-skeleton) check_template_skeleton_complete ;;
  --no-self-constitution) check_no_self_constitution_inject ;;
  --no-self-fallback-circuit) check_no_self_fallback_circuit ;;
  all|"")
    check_emoji
    check_agpl
    check_archive
    check_tickets
    check_secrets
    check_no_langgraph
    check_no_litellm_in_runner
    check_domain_boundaries
    check_no_self_provider_routing
    check_no_self_tool_trim
    check_template_skeleton_complete
    check_no_self_constitution_inject
    check_no_self_fallback_circuit
    ;;
  *)
    echo "Usage: $0 [--emoji|--agpl|--archive|--tickets|--secrets|--no-langgraph|--no-litellm-in-runner|--domains|--no-self-provider-routing|--no-self-tool-trim|--template-skeleton|--no-self-constitution|--no-self-fallback-circuit|all]"
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
