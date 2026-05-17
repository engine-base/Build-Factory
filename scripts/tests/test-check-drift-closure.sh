#!/usr/bin/env bash
# T-V3-D-15 self-test for scripts/check-drift-closure.py
#
# 検証シナリオ:
#   1. broken fixture: legacy_drift_notes.impl_table='(missing)' → check が NG を返す
#   2. broken fixture: 不存在 ticket id → check が NG を返す
#   3. broken fixture: 不整合 status + 不整合 table_name → check が NG を返す
#   4. real repo: check が exit 0 を返す (final guard)
#
# Usage:
#   bash scripts/tests/test-check-drift-closure.sh
#
# Exit codes:
#   0  全 scenario PASS
#   1  どこかの scenario FAIL

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

PASS=0
FAIL=0

pass() {
  echo -e "${GREEN}PASS${NC} - $1"
  PASS=$((PASS + 1))
}

fail() {
  echo -e "${RED}FAIL${NC} - $1"
  FAIL=$((FAIL + 1))
}

echo "===== T-V3-D-15 check-drift-closure.py self-test ====="
echo ""

# ----------------------------------------------------------------
# Helper: temp fixture をセットアップする
# ----------------------------------------------------------------
TMP_DIR=$(mktemp -d)
trap 'rm -rf "${TMP_DIR}"' EXIT

# real tickets file は読み取り専用で読む (validation の左辺)
TICKETS_FILE="docs/task-decomposition/2026-05-16_v3_phase1/tickets-group-d-drift.json"

# ----------------------------------------------------------------
# Scenario 1: impl_table='(missing)' を含む entities.json fixture
#   → 該当 entity が open に出ること + exit non-zero
# ----------------------------------------------------------------
FIXTURE_MISSING="${TMP_DIR}/entities_missing.json"
cat > "${FIXTURE_MISSING}" <<'JSON'
{
  "entities": [
    {
      "id": "E-009",
      "name": "SkillExecution",
      "table_name": "skill_executions",
      "spec_table_name": "skill_executions",
      "status": "decided",
      "legacy_drift_notes": {
        "impl_table": "(missing)",
        "task_id": "T-V3-DRIFT-E-009"
      }
    }
  ]
}
JSON

OUTPUT_1=$(python3 scripts/check-drift-closure.py \
  --entities-file "${FIXTURE_MISSING}" \
  --tickets-file "${TICKETS_FILE}" \
  --skip-rls-check --skip-lint-check 2>&1)
EXIT_1=$?

if [ "${EXIT_1}" -eq 1 ] && echo "${OUTPUT_1}" | grep -q "E-009 legacy_drift_notes.impl_table == '(missing)'"; then
  pass "scenario 1: impl_table='(missing)' is detected and reported"
else
  fail "scenario 1: expected exit=1 with '(missing)' detection, got exit=${EXIT_1}"
  echo "${OUTPUT_1}" | head -20
fi

# ----------------------------------------------------------------
# Scenario 2: 不存在 ticket file → exit 64
# ----------------------------------------------------------------
OUTPUT_2=$(python3 scripts/check-drift-closure.py \
  --tickets-file "${TMP_DIR}/does-not-exist.json" \
  --skip-rls-check --skip-lint-check 2>&1)
EXIT_2=$?

if [ "${EXIT_2}" -eq 64 ] && echo "${OUTPUT_2}" | grep -q "not found or empty"; then
  pass "scenario 2: missing tickets file returns exit=64"
else
  fail "scenario 2: expected exit=64, got exit=${EXIT_2}"
  echo "${OUTPUT_2}" | head -10
fi

# ----------------------------------------------------------------
# Scenario 3: status='decided' + table_name != spec_table_name で
#   resolver 不在 → open に分類されること
# ----------------------------------------------------------------
FIXTURE_UNRESOLVED="${TMP_DIR}/entities_unresolved.json"
cat > "${FIXTURE_UNRESOLVED}" <<'JSON'
{
  "entities": [
    {
      "id": "E-008",
      "name": "Skill",
      "table_name": "skills",
      "spec_table_name": "skill_definitions",
      "status": "decided",
      "legacy_drift_notes": {
        "task_id": "T-NONEXISTENT",
        "impl_table": "skills"
      }
    }
  ]
}
JSON

OUTPUT_3=$(python3 scripts/check-drift-closure.py \
  --entities-file "${FIXTURE_UNRESOLVED}" \
  --tickets-file "${TICKETS_FILE}" \
  --skip-rls-check --skip-lint-check 2>&1)
EXIT_3=$?

if [ "${EXIT_3}" -eq 1 ] && echo "${OUTPUT_3}" | grep -q "E-008.*expected resolver T-V3-D-01"; then
  pass "scenario 3: unresolved drift (placeholder task + drift name) is flagged"
else
  fail "scenario 3: expected exit=1 with E-008 open, got exit=${EXIT_3}"
  echo "${OUTPUT_3}" | head -20
fi

# ----------------------------------------------------------------
# Scenario 4: empty entities.json (all 48 in-scope entities missing) → exit 1
# ----------------------------------------------------------------
FIXTURE_EMPTY="${TMP_DIR}/entities_empty.json"
cat > "${FIXTURE_EMPTY}" <<'JSON'
{
  "entities": []
}
JSON

OUTPUT_4=$(python3 scripts/check-drift-closure.py \
  --entities-file "${FIXTURE_EMPTY}" \
  --tickets-file "${TICKETS_FILE}" \
  --skip-rls-check --skip-lint-check 2>&1)
EXIT_4=$?

if [ "${EXIT_4}" -eq 1 ] && echo "${OUTPUT_4}" | grep -q "expected resolution.*entity not present"; then
  pass "scenario 4: missing in-scope entities are reported"
else
  fail "scenario 4: expected exit=1 with 'entity not present' message, got exit=${EXIT_4}"
  echo "${OUTPUT_4}" | head -10
fi

# ----------------------------------------------------------------
# Scenario 5: real repo state → exit 0 (FINAL GUARD — proves the script
#   accepts the actual Phase 1 closure state).
# ----------------------------------------------------------------
OUTPUT_5=$(python3 scripts/check-drift-closure.py 2>&1)
EXIT_5=$?

if [ "${EXIT_5}" -eq 0 ] && echo "${OUTPUT_5}" | grep -q "PHASE 1 DRIFT CLOSURE 100% GREEN"; then
  pass "scenario 5: real repo state passes (exit 0, all categories green)"
else
  fail "scenario 5: expected exit=0 on real repo, got exit=${EXIT_5}"
  echo "${OUTPUT_5}" | tail -20
fi

# ----------------------------------------------------------------
# Scenario 6: JSON mode is parseable
# ----------------------------------------------------------------
OUTPUT_6=$(python3 scripts/check-drift-closure.py --json --skip-rls-check --skip-lint-check 2>&1)
EXIT_6=$?

if [ "${EXIT_6}" -eq 0 ] && echo "${OUTPUT_6}" | python3 -c "
import json, sys
d = json.loads(sys.stdin.read())
assert d['all_green'] is True, 'all_green should be True'
assert len(d['categories']) == 4, f'expected 4 categories (rls/lint skipped), got {len(d[\"categories\"])}'
" 2>&1; then
  pass "scenario 6: --json output is parseable and all_green=true"
else
  fail "scenario 6: JSON mode failed (exit=${EXIT_6})"
  echo "${OUTPUT_6}" | head -10
fi

# ----------------------------------------------------------------
# Summary
# ----------------------------------------------------------------
echo ""
echo "===== Result: ${PASS} passed / ${FAIL} failed ====="

if [ "${FAIL}" -gt 0 ]; then
  exit 1
fi
exit 0
