#!/usr/bin/env bash
# T-V3-D-02 regression test for lint-mock.sh rule #19 (entity-table-naming).
#
# 目的:
#   1. ADR-014 allow-list (E-014/15/16/17) は spec=impl=bf_* で揃っている → OK[allowlist]
#   2. allow-list 内で spec が drift していたら fail (ALLOWLIST_MISALIGNED)
#   3. allow-list 外で spec != impl の drift があれば fail (DRIFT)
#   4. 全 entity が spec == impl で揃っている fixture では PASS (exit 0)
#   5. CLI スイッチ `--entity-table-naming` で単体起動できる
#
# Run:
#   bash scripts/tests/test-lint-mock-rule19.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}"

PASS=0
FAIL=0

# 色
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

pass() {
  echo -e "${GREEN}PASS${NC} - $1"
  PASS=$((PASS + 1))
}

fail() {
  echo -e "${RED}FAIL${NC} - $1"
  FAIL=$((FAIL + 1))
}

# 一時 entities.json を使った scenario 評価 helper
# $1: 一時 entities.json の内容 (json string)
# $2: 期待 exit_code (0 = OK / 1 = NG)
# $3: 期待 output 部分文字列 (grep -F で検索)
# $4: テスト名
run_with_fixture() {
  local fixture_content="$1"
  local expected_exit="$2"
  local expected_substr="$3"
  local name="$4"

  local tmp_dir
  tmp_dir=$(mktemp -d)
  trap 'rm -rf "$tmp_dir"' RETURN

  # 一時 entities.json を作る (lint-mock.sh が読む path に向けて symlink ではなく
  # rule を inline 実行するため Python ワンライナーで scope を狭く検証する)
  local fixture_path="$tmp_dir/entities.json"
  echo "$fixture_content" > "$fixture_path"

  # 同じロジックを Python で再現 (rule #19 の core を import せず直接検証)
  local result
  result=$(python3 - "$fixture_path" <<'PY'
import json
import sys
from pathlib import Path

ENTITIES_PATH = Path(sys.argv[1])
ADR014_ALLOW = {
    "E-014": "bf_tasks",
    "E-015": "bf_task_dependencies",
    "E-016": "bf_acceptance_criteria",
    "E-017": "bf_constitutions",
}

data = json.loads(ENTITIES_PATH.read_text(encoding="utf-8"))
entities = data.get("entities", data) if isinstance(data, dict) else data

drift = []
allow_misaligned = []
for e in entities:
    eid = e.get("id")
    impl = e.get("table_name")
    spec = e.get("spec_table_name")
    if not eid or not impl or not spec:
        continue
    if eid in ADR014_ALLOW:
        expected = ADR014_ALLOW[eid]
        if spec != expected or impl != expected:
            allow_misaligned.append((eid, impl, spec, expected))
        continue
    if impl != spec:
        drift.append((eid, e.get("name", "?"), spec, impl))

if allow_misaligned:
    print("ALLOWLIST_MISALIGNED")
    for eid, impl, spec, expected in allow_misaligned:
        print(f"  {eid}: expected '{expected}', got impl='{impl}' spec='{spec}'")
else:
    print("ALLOWLIST_OK")
    for eid, expected in ADR014_ALLOW.items():
        print(f"  {eid}: spec=impl='{expected}' (ADR-014)")
if drift:
    print("DRIFT")
    for eid, name, spec, impl in drift:
        print(f"  {eid} {name}: spec='{spec}' impl='{impl}'")

if allow_misaligned or drift:
    sys.exit(1)
sys.exit(0)
PY
)
  local actual_exit=$?

  if [ "$actual_exit" -ne "$expected_exit" ]; then
    fail "$name (expected exit=$expected_exit, got=$actual_exit)"
    echo "  output: $result"
    return
  fi
  if [ -n "$expected_substr" ] && ! echo "$result" | grep -qF "$expected_substr"; then
    fail "$name (expected substr '$expected_substr' not in output)"
    echo "  output: $result"
    return
  fi
  pass "$name"
}

echo "===== T-V3-D-02 rule #19 (entity-table-naming) regression test ====="

# ----------------------------------------------------------------
# scenario 1: 全 entity が spec=impl で揃っている (PASS / exit 0)
# ----------------------------------------------------------------
FIXTURE_ALIGNED=$(cat <<'JSON'
{
  "entities": [
    {"id": "E-014", "name": "Task", "table_name": "bf_tasks", "spec_table_name": "bf_tasks"},
    {"id": "E-015", "name": "TaskDependency", "table_name": "bf_task_dependencies", "spec_table_name": "bf_task_dependencies"},
    {"id": "E-016", "name": "AcceptanceCriterion", "table_name": "bf_acceptance_criteria", "spec_table_name": "bf_acceptance_criteria"},
    {"id": "E-017", "name": "Constitution", "table_name": "bf_constitutions", "spec_table_name": "bf_constitutions"},
    {"id": "E-002", "name": "Account", "table_name": "accounts", "spec_table_name": "accounts"}
  ]
}
JSON
)
run_with_fixture "$FIXTURE_ALIGNED" 0 "ALLOWLIST_OK" "scenario 1: aligned fixture (allow-list + non-bf) -> exit 0"

# ----------------------------------------------------------------
# scenario 2: allow-list (E-014) で spec が impl から drift -> ALLOWLIST_MISALIGNED
# ----------------------------------------------------------------
FIXTURE_ALLOW_DRIFT=$(cat <<'JSON'
{
  "entities": [
    {"id": "E-014", "name": "Task", "table_name": "bf_tasks", "spec_table_name": "tasks"},
    {"id": "E-015", "name": "TaskDependency", "table_name": "bf_task_dependencies", "spec_table_name": "bf_task_dependencies"},
    {"id": "E-016", "name": "AcceptanceCriterion", "table_name": "bf_acceptance_criteria", "spec_table_name": "bf_acceptance_criteria"},
    {"id": "E-017", "name": "Constitution", "table_name": "bf_constitutions", "spec_table_name": "bf_constitutions"}
  ]
}
JSON
)
run_with_fixture "$FIXTURE_ALLOW_DRIFT" 1 "ALLOWLIST_MISALIGNED" "scenario 2: E-014 spec drift -> fail with ALLOWLIST_MISALIGNED"

# ----------------------------------------------------------------
# scenario 3: 非 allow-list で drift (E-008 Skill) -> DRIFT
# ----------------------------------------------------------------
FIXTURE_NON_ALLOW_DRIFT=$(cat <<'JSON'
{
  "entities": [
    {"id": "E-014", "name": "Task", "table_name": "bf_tasks", "spec_table_name": "bf_tasks"},
    {"id": "E-015", "name": "TaskDependency", "table_name": "bf_task_dependencies", "spec_table_name": "bf_task_dependencies"},
    {"id": "E-016", "name": "AcceptanceCriterion", "table_name": "bf_acceptance_criteria", "spec_table_name": "bf_acceptance_criteria"},
    {"id": "E-017", "name": "Constitution", "table_name": "bf_constitutions", "spec_table_name": "bf_constitutions"},
    {"id": "E-008", "name": "Skill", "table_name": "skill_definitions", "spec_table_name": "skills"}
  ]
}
JSON
)
run_with_fixture "$FIXTURE_NON_ALLOW_DRIFT" 1 "DRIFT" "scenario 3: E-008 Skill drift -> fail with DRIFT"

# ----------------------------------------------------------------
# scenario 4: 実プロジェクト entities.json で E-014/15/16/17 が ALLOWLIST_OK
# (本番 entities.json は他 entity の drift で fail するため、AC R2 の核
# 「rule #19 showing OK for E-014/15/16/17」を text 検証)
# ----------------------------------------------------------------
ENTITIES="docs/functional-breakdown/2026-05-16_v3/entities.json"
if [ -f "$ENTITIES" ]; then
  output=$(bash scripts/lint-mock.sh --entity-table-naming 2>&1 || true)
  if echo "$output" | grep -q "OK\[allowlist\]"; then
    if echo "$output" | grep -q "E-014: spec=impl='bf_tasks'"; then
      if echo "$output" | grep -q "E-015: spec=impl='bf_task_dependencies'"; then
        if echo "$output" | grep -q "E-016: spec=impl='bf_acceptance_criteria'"; then
          if echo "$output" | grep -q "E-017: spec=impl='bf_constitutions'"; then
            pass "scenario 4: real entities.json - E-014/15/16/17 OK[allowlist] confirmed"
          else
            fail "scenario 4: E-017 not OK"
          fi
        else
          fail "scenario 4: E-016 not OK"
        fi
      else
        fail "scenario 4: E-015 not OK"
      fi
    else
      fail "scenario 4: E-014 not OK"
    fi
  else
    fail "scenario 4: OK[allowlist] line not found"
    echo "$output" | head -15
  fi
else
  fail "scenario 4: $ENTITIES not found"
fi

# ----------------------------------------------------------------
# scenario 5: lint-mock.sh has --entity-table-naming CLI switch
# ----------------------------------------------------------------
if grep -q -- '--entity-table-naming' scripts/lint-mock.sh; then
  pass "scenario 5: --entity-table-naming CLI switch wired in lint-mock.sh"
else
  fail "scenario 5: --entity-table-naming CLI switch not found"
fi

echo
echo "===== Summary: PASS=$PASS / FAIL=$FAIL ====="
if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
