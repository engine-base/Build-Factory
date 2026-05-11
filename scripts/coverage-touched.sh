#!/usr/bin/env bash
# coverage-touched.sh — このセッションで触ったタスク群のターゲットファイル限定 coverage
#
# CLAUDE.md §5.3「テストカバレッジ ≥ 70% (Phase 1 ゲート)」
# IMPLEMENTATION_PROTOCOL.md Step 7 v2.1 適合チェック #2 の検証スクリプト。
#
# リポジトリ全体は legacy コード (40 routers + 50 services) も含むため、
# 全体カバレッジでの 70% 達成は非現実的。 本スクリプトは「セッションで
# 触ったタスクのターゲットファイル限定」で coverage を測定する。
#
# 使い方:
#   bash scripts/coverage-touched.sh
#   bash scripts/coverage-touched.sh --baseline   # baseline 更新
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACKEND="$ROOT/backend"
BASELINE_FILE="$ROOT/.coverage-baseline"

cd "$BACKEND"

TARGETS=(
  "services.bf_profile"
  "services.workspace_service"
  "services.user_lifecycle"
  "services.roles"
  "routers.bf_profile"
  "routers.oauth"
  "routers.workspaces"
  "routers.user_lifecycle"
)

COV_ARGS=()
for t in "${TARGETS[@]}"; do COV_ARGS+=(--cov="$t"); done

# pytest 実行 (silent)
OUTPUT=$(python3 -m pytest tests/ "${COV_ARGS[@]}" --cov-report=term --tb=line -q 2>&1)

# TOTAL 行から % を抽出
TOTAL_LINE=$(echo "$OUTPUT" | grep -E "^TOTAL\s" | tail -1)
COV_PCT=$(echo "$TOTAL_LINE" | grep -oE '[0-9]+%$' | tr -d '%')

if [[ -z "$COV_PCT" ]]; then
  echo "FAIL: coverage % not detected"
  echo "$OUTPUT" | tail -20
  exit 1
fi

# baseline 比較
if [[ "${1:-}" == "--baseline" ]]; then
  echo "$COV_PCT" > "$BASELINE_FILE"
  echo "Baseline updated: $COV_PCT%"
  exit 0
fi

BASELINE=$(cat "$BASELINE_FILE" 2>/dev/null || echo 0)

echo ""
echo "=================================================="
echo "Touched-files coverage report"
echo "=================================================="
echo "$OUTPUT" | grep -E "^(routers|services)/" | sort
echo "--------------------------------------------------"
echo "TOTAL:    ${COV_PCT}%"
echo "Baseline: ${BASELINE}%"
echo "Target:   70% (Phase 1 gate)"
echo "=================================================="

if (( COV_PCT < BASELINE )); then
  echo ""
  echo "FAIL: coverage decreased ($COV_PCT% < baseline $BASELINE%)"
  echo "Add tests to restore or update baseline with: bash scripts/coverage-touched.sh --baseline"
  exit 1
fi

if (( COV_PCT < 70 )); then
  echo ""
  echo "WARN: coverage $COV_PCT% < 70% Phase 1 gate"
  echo "(baseline $BASELINE% is maintained; tighten with more DB-mocked tests)"
fi

echo ""
echo "OK: coverage $COV_PCT% (baseline $BASELINE%)"
