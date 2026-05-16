#!/usr/bin/env bash
# Build-Factory audit-md-check.sh self-test runner
#
# T-FOUNDATION-01 で追加。CI / pre-commit から呼べる薄い wrapper。
# audit-md-check.sh --self-test を実行し、その exit code を伝播する。
#
# Usage:
#   bash scripts/tests/test-audit-md-check.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}" || exit 64

echo "[test-audit-md-check] running scripts/audit-md-check.sh --self-test"
bash scripts/audit-md-check.sh --self-test
rc=$?

if [[ "${rc}" -eq 0 ]]; then
  echo "[test-audit-md-check] PASS"
else
  echo "[test-audit-md-check] FAIL (exit ${rc})" >&2
fi

exit "${rc}"
