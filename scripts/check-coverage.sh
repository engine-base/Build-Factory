#!/usr/bin/env bash
# 徹底修正: pytest + coverage 計測 (CLAUDE.md §5.3 「カバレッジ ≥ 70%」のベースライン)
#
# 現状 (Sprint 0/1 スケルトン段階): baseline=30% (実 SDK 呼び出し経路は
# テストしづらいため低め)。Sprint 4-5 で実装が増えるたびに baseline を引き上げる。
#
# 使い方:
#   bash scripts/check-coverage.sh          # 計測のみ
#   bash scripts/check-coverage.sh --gate    # baseline 未満なら exit 1
set -e

cd "$(dirname "$0")/.."

PYTEST="${PYTEST:-/usr/local/bin/python3 -m pytest}"
BASELINE_FILE=".coverage-baseline"
BASELINE=30
[ -f "$BASELINE_FILE" ] && BASELINE=$(cat "$BASELINE_FILE")

if ! /usr/local/bin/python3 -c "import pytest_cov" 2>/dev/null; then
  echo "[SKIP] pytest-cov 未インストール → pip install pytest-cov pytest"
  exit 0
fi

cd backend
COV=$($PYTEST tests/ \
  --cov=services.swarm --cov=services.memory_service \
  --cov-report=term 2>&1 \
  | awk '/^TOTAL/ {gsub("%","",$NF); print $NF}')

if [ -z "$COV" ]; then
  echo "[FAIL] coverage 計測失敗"
  exit 2
fi

cd ..
echo "coverage = ${COV}% (baseline ${BASELINE}%)"

if [ "${1:-}" = "--gate" ]; then
  # COV は整数で比較 (浮動小数点は bc を使う)
  if [ "$(printf '%.0f' "$COV")" -lt "$BASELINE" ]; then
    echo "[FAIL] coverage ${COV}% < baseline ${BASELINE}%"
    exit 1
  fi
fi
echo "[OK] coverage check passed"
