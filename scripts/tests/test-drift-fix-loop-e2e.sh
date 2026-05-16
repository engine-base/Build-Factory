#!/usr/bin/env bash
# Build-Factory v3 Phase 0 follow-up F2 — drift fix loop end-to-end integration test
#
# T-02 (scripts/lint-mock-impl-diff.py)
#   -> T-05 (scripts/generate-drift-tickets.py)
#   -> validate-tickets.py --check-file
# の 3 段を artificial drift fixture で連結し、output / input schema 互換性 +
# 生成 drift task の field 整合 (Group D / 3-tier AC / deliverable_layer 等) を assert する.
#
# Spec: skills/integration/references/v3-core.md の 主軸 3 (drift fix queue 流し込み)
# Audit: docs/audit/2026-05-16_v3/F2-drift-fix-loop-e2e.md (Tier 1-3 AC)
#
# Usage:
#   bash scripts/tests/test-drift-fix-loop-e2e.sh
# Exit codes:
#   0 = 全 step PASS / 1 = いずれかの step FAIL / 64 = 環境エラー (cd 失敗等)

set -euo pipefail

# ----------------------------------------------------------------
# Setup: REPO_ROOT 解決 + tmp dir + trap cleanup
# ----------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${REPO_ROOT}" || exit 64

TMP_DIR="$(mktemp -d -t drift-e2e-XXXXXX)"
# shellcheck disable=SC2317  # invoked via `trap` (shellcheck cannot statically detect this)
cleanup() {
  if [[ -n "${TMP_DIR:-}" && -d "${TMP_DIR}" ]]; then
    rm -rf "${TMP_DIR}"
  fi
}
trap cleanup EXIT

MOCK_DIR="${TMP_DIR}/mocks"
IMPL_DIR="${TMP_DIR}/impl"
DRIFT_JSON="${TMP_DIR}/drift.json"
TICKETS_JSON="${TMP_DIR}/drift-tickets-W1.json"
mkdir -p "${MOCK_DIR}" "${IMPL_DIR}/screens"

# ----------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------

fail() {
  echo "[drift-e2e] FAIL: $*" >&2
  exit 1
}

pass() {
  echo "[drift-e2e] PASS: $*"
}

step() {
  echo
  echo "----- $* -----"
}

# ----------------------------------------------------------------
# Setup fixtures: 3 種の artificial drift
#   drift A: meta value mismatch (screen-id only, other fields aligned)
#   drift B: impl file 不存在
#   drift C: mock 側の meta 欠落 (phase のみ欠落, 他は impl と一致)
# ----------------------------------------------------------------

step "Setup: 3 artificial drift fixtures in ${TMP_DIR}"

# --- drift A : mock S-001 -> impl has data-screen-id="S-002" (only screen-id diverges) ---
cat >"${MOCK_DIR}/S-001.html" <<'EOF'
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>drift-A S-001</title>
<meta name="screen-id" content="S-001" />
<meta name="feature-id" content="F-100" />
<meta name="task-ids" content="T-100-01" />
<meta name="entities" content="users" />
<meta name="phase" content="P1" />
</head>
<body><h1>drift A</h1></body>
</html>
EOF

cat >"${IMPL_DIR}/screens/S-001.tsx" <<'EOF'
/**
 * @screen-id S-002
 * @feature-id F-100
 * @task-ids T-100-01
 * @entities users
 * @phase P1
 */
import * as React from "react";
export default function S001(): React.ReactElement {
  return (
    <div
      data-screen-id="S-002"
      data-feature-id="F-100"
      data-task-ids="T-100-01"
      data-entities="users"
      data-phase="P1"
    >
      <h1>drift A</h1>
    </div>
  );
}
EOF

# --- drift B : mock S-002 exists, impl file 不存在 ---
cat >"${MOCK_DIR}/S-002.html" <<'EOF'
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>drift-B S-002</title>
<meta name="screen-id" content="S-002" />
<meta name="feature-id" content="F-200" />
<meta name="task-ids" content="T-200-01" />
<meta name="entities" content="orders" />
<meta name="phase" content="P1" />
</head>
<body><h1>drift B</h1></body>
</html>
EOF
# 故意に ${IMPL_DIR}/screens/S-002.tsx を作らない

# --- drift C : mock S-003 has screen-id but missing phase ; impl has all 5 fields ---
cat >"${MOCK_DIR}/S-003.html" <<'EOF'
<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8" />
<title>drift-C S-003</title>
<meta name="screen-id" content="S-003" />
<meta name="feature-id" content="F-300" />
<meta name="task-ids" content="T-300-01" />
<meta name="entities" content="invoices" />
</head>
<body><h1>drift C (phase meta missing)</h1></body>
</html>
EOF

cat >"${IMPL_DIR}/screens/S-003.tsx" <<'EOF'
/**
 * @screen-id S-003
 * @feature-id F-300
 * @task-ids T-300-01
 * @entities invoices
 * @phase P1
 */
import * as React from "react";
export default function S003(): React.ReactElement {
  return (
    <div
      data-screen-id="S-003"
      data-feature-id="F-300"
      data-task-ids="T-300-01"
      data-entities="invoices"
      data-phase="P1"
    >
      <h1>drift C</h1>
    </div>
  );
}
EOF

pass "Fixtures created (3 drift scenarios)"

# ----------------------------------------------------------------
# Step 1: lint-mock-impl-diff.py で drift.json 生成 → 3 件 assert
# ----------------------------------------------------------------

step "Step 1: lint-mock-impl-diff.py --output drift.json"

python3 scripts/lint-mock-impl-diff.py \
  --mock-dir "${MOCK_DIR}" \
  --impl-dir "${IMPL_DIR}" \
  --output "${DRIFT_JSON}" \
  || fail "lint-mock-impl-diff.py exited non-zero (expected 0 without --strict)"

if [[ ! -s "${DRIFT_JSON}" ]]; then
  fail "drift.json was not created or is empty: ${DRIFT_JSON}"
fi

drift_count="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['drift_count'])" "${DRIFT_JSON}")"
if [[ "${drift_count}" != "3" ]]; then
  echo "[drift-e2e] drift.json contents:" >&2
  cat "${DRIFT_JSON}" >&2
  fail "drift_count expected 3, got ${drift_count}"
fi

# 3 件の kind / screen_id を逐一検査
python3 - "${DRIFT_JSON}" <<'PY' || fail "drift.json field-level assertions failed (see stderr)"
import json
import sys

path = sys.argv[1]
data = json.load(open(path, encoding="utf-8"))
drifts = data["drifts"]
errors = []

# drift A : S-001 / screen-id field / value_mismatch
A = [d for d in drifts if d["screen_id"] == "S-001"]
if not (len(A) == 1
        and A[0]["field"] == "screen-id"
        and A[0]["kind"] == "value_mismatch"
        and A[0]["mock_value"] == "S-001"
        and A[0]["impl_value"] == "S-002"):
    errors.append(f"drift A unexpected: {A!r}")

# drift B : S-002 / field=* / missing_in_impl / severity=error
B = [d for d in drifts if d["screen_id"] == "S-002"]
if not (len(B) == 1
        and B[0]["field"] == "*"
        and B[0]["kind"] == "missing_in_impl"
        and B[0]["severity"] == "error"):
    errors.append(f"drift B unexpected: {B!r}")

# drift C : S-003 / field=phase / missing_field_in_mock / severity=error
C = [d for d in drifts if d["screen_id"] == "S-003"]
if not (len(C) == 1
        and C[0]["field"] == "phase"
        and C[0]["kind"] == "missing_field_in_mock"
        and C[0]["severity"] == "error"
        and C[0]["mock_value"] is None
        and C[0]["impl_value"] == "P1"):
    errors.append(f"drift C unexpected: {C!r}")

if errors:
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1)

print("[drift-e2e] step1 assertions: 3/3 PASS")
PY

pass "Step 1: drift.json = 3 drifts (A=value_mismatch / B=missing_in_impl / C=missing_field_in_mock)"

# ----------------------------------------------------------------
# Step 2: generate-drift-tickets.py で drift-tickets-W1.json 生成 → 3 件 assert
# ----------------------------------------------------------------

step "Step 2: generate-drift-tickets.py --source-wave W1 --target-wave W2"

python3 scripts/generate-drift-tickets.py \
  --lint-output "${DRIFT_JSON}" \
  --source-wave W1 \
  --target-wave W2 \
  --output "${TICKETS_JSON}" \
  --date 2026-05-16 \
  || fail "generate-drift-tickets.py exited non-zero"

if [[ ! -s "${TICKETS_JSON}" ]]; then
  fail "drift-tickets-W1.json was not created or is empty: ${TICKETS_JSON}"
fi

total_tasks="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['summary']['total_tasks'])" "${TICKETS_JSON}")"
if [[ "${total_tasks}" != "3" ]]; then
  echo "[drift-e2e] drift-tickets-W1.json contents:" >&2
  cat "${TICKETS_JSON}" >&2
  fail "summary.total_tasks expected 3, got ${total_tasks}"
fi

# 3 件の id 順を検査 (T-DRIFT-W1-001 / 002 / 003)
python3 - "${TICKETS_JSON}" <<'PY' || fail "drift-tickets-W1.json id sequence assertion failed"
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
ids = [t["id"] for t in data["tasks"]]
expected_ids = ["T-DRIFT-W1-001", "T-DRIFT-W1-002", "T-DRIFT-W1-003"]
if ids != expected_ids:
    print(f"id sequence mismatch: expected {expected_ids}, got {ids}", file=sys.stderr)
    sys.exit(1)

# source/target wave + version + project sanity
if data.get("version") != "v3":
    print(f"version expected 'v3', got {data.get('version')!r}", file=sys.stderr)
    sys.exit(1)
if data.get("source_wave") != "W1" or data.get("target_wave") != "W2":
    print(f"wave mismatch: {data.get('source_wave')!r} -> {data.get('target_wave')!r}", file=sys.stderr)
    sys.exit(1)

print("[drift-e2e] step2 id sequence: 3/3 PASS")
PY

pass "Step 2: drift-tickets-W1.json = 3 drift tasks (T-DRIFT-W1-001..003)"

# ----------------------------------------------------------------
# Step 3: validate-tickets.py --check-file で v3 schema 検証 → PASS
# ----------------------------------------------------------------

step "Step 3: validate-tickets.py --check-file PASS"

if ! python3 scripts/validate-tickets.py --check-file "${TICKETS_JSON}" >"${TMP_DIR}/validate.log" 2>&1; then
  echo "[drift-e2e] validate-tickets.py output:" >&2
  cat "${TMP_DIR}/validate.log" >&2
  fail "validate-tickets.py --check-file failed (drift-tickets schema not v3 compliant)"
fi

if ! grep -q "OK: all tasks pass v3 schema validation." "${TMP_DIR}/validate.log"; then
  echo "[drift-e2e] validate-tickets.py output:" >&2
  cat "${TMP_DIR}/validate.log" >&2
  fail "validate-tickets.py did not print the expected OK line"
fi

pass "Step 3: validate-tickets.py --check-file PASS (v3 schema valid)"

# ----------------------------------------------------------------
# Step 4: 生成 drift task の field 検証
#   deliverable_layer == "ui" (mock-impl-diff rule の既定)
#   target_wave == "W2"
#   group == "D" (BF profile 検出時)
#   acceptance_criteria に structural / functional / regression 各 1 件以上
#   audit_md_path / branch / drift_source / files_changed 整合
# ----------------------------------------------------------------

step "Step 4: drift task field assertions (deliverable_layer / group / 3-tier AC)"

python3 - "${TICKETS_JSON}" <<'PY' || fail "drift task field assertions failed"
import json
import sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
errors = []

if data.get("project") != "Build-Factory":
    errors.append(
        f"project expected 'Build-Factory' (BF profile detected), got {data.get('project')!r}"
    )

for idx, t in enumerate(data["tasks"], start=1):
    tid = t.get("id", f"<index {idx}>")
    src_screen = t["drift_source"]["screen_id"]

    if t.get("deliverable_layer") != "ui":
        errors.append(f"{tid}: deliverable_layer expected 'ui' (mock-impl-diff rule), got {t.get('deliverable_layer')!r}")
    if t.get("wave") != "W2":
        errors.append(f"{tid}: wave expected 'W2' (target_wave), got {t.get('wave')!r}")
    if t.get("group") != "D":
        errors.append(f"{tid}: group expected 'D' (BF profile drift_fix_queue), got {t.get('group')!r}")
    if t.get("phase") != "Foundation":
        errors.append(f"{tid}: phase expected 'Foundation', got {t.get('phase')!r}")
    if t.get("label") != "FIX":
        errors.append(f"{tid}: label expected 'FIX', got {t.get('label')!r}")
    if t.get("category") != "infra":
        errors.append(f"{tid}: category expected 'infra', got {t.get('category')!r}")

    # 3-tier AC seed
    ac = t.get("acceptance_criteria") or {}
    if not isinstance(ac.get("structural"), list) or len(ac["structural"]) < 1:
        errors.append(f"{tid}: acceptance_criteria.structural must have >= 1 entry")
    if not isinstance(ac.get("functional"), list) or len(ac["functional"]) < 3:
        errors.append(f"{tid}: acceptance_criteria.functional must have >= 3 entries (UBIQUITOUS/EVENT-DRIVEN/UNWANTED)")
    if not isinstance(ac.get("regression"), list) or len(ac["regression"]) < 6:
        errors.append(f"{tid}: acceptance_criteria.regression must have >= 6 entries (BF tier3 regression set)")

    # files_changed / work_package_boundary が screen 名と整合
    expected_impl = f"frontend/src/screens/{src_screen}.tsx"
    if expected_impl not in (t.get("files_changed") or []):
        errors.append(f"{tid}: files_changed missing {expected_impl}")
    wpb = t.get("work_package_boundary") or {}
    if expected_impl not in (wpb.get("editable") or []):
        errors.append(f"{tid}: work_package_boundary.editable missing {expected_impl}")
    for k in ("shared_no_concurrent_edit", "readonly", "forbidden"):
        if k not in wpb:
            errors.append(f"{tid}: work_package_boundary.{k} missing")

    # audit_md_path / branch
    expected_audit = f"docs/audit/2026-05-16_v3/{tid}.md"
    if t.get("audit_md_path") != expected_audit:
        errors.append(f"{tid}: audit_md_path expected {expected_audit!r}, got {t.get('audit_md_path')!r}")
    expected_branch = f"claude/{tid}"
    if t.get("branch") != expected_branch:
        errors.append(f"{tid}: branch expected {expected_branch!r}, got {t.get('branch')!r}")

    # drift_source.source_wave / rule_id
    if t["drift_source"].get("source_wave") != "W1":
        errors.append(f"{tid}: drift_source.source_wave expected 'W1'")
    if t["drift_source"].get("rule_id") != "mock-impl-diff":
        errors.append(f"{tid}: drift_source.rule_id expected 'mock-impl-diff'")

if errors:
    for e in errors:
        print(e, file=sys.stderr)
    sys.exit(1)

print("[drift-e2e] step4 assertions: all PASS for 3 drift tasks")
PY

pass "Step 4: drift task field assertions (Group D / target_wave W2 / 3-tier AC / boundaries)"

# ----------------------------------------------------------------
# Step 5: cleanup (trap EXIT が削除する; ここでは sanity echo のみ)
# ----------------------------------------------------------------

step "Step 5: cleanup (handled by trap EXIT)"
echo "[drift-e2e] tmp dir will be removed: ${TMP_DIR}"

# ----------------------------------------------------------------
# 全 step PASS
# ----------------------------------------------------------------

echo
echo "============================================================"
echo "[drift-e2e] ALL 5 STEPS PASS — drift fix loop end-to-end OK"
echo "============================================================"
exit 0
