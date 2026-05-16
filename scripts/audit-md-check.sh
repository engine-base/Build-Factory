#!/usr/bin/env bash
# Build-Factory audit MD pre-flight チェック (Gate #4)
#
# T-FOUNDATION-01 で実装。
# 着手前に docs/audit/2026-05-16_v3/T-<task_id>.md が存在し、
# Tier 1/2/3 の 3 セクションがそろい、generic phrase を含まないことを保証する。
#
# Usage:
#   bash scripts/audit-md-check.sh <task_id>             # 単一 task 確認
#   bash scripts/audit-md-check.sh --all                 # tickets.json 全 task 確認
#   bash scripts/audit-md-check.sh --audit-dir <path>    # 監査 MD 配置先を切り替え
#   bash scripts/audit-md-check.sh --self-test           # 4 fixture self-test
#   bash scripts/audit-md-check.sh --help                # ヘルプ表示
#
# Exit codes:
#   0  PASS / self-test 全成功
#   1  audit MD ファイルが存在しない
#   2  3 セクション欠落 / generic phrase 検出 (structurally invalid)
#   64 引数誤り (usage error)

set -uo pipefail

# repo root へ移動 (script は scripts/ 配下)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}" || exit 64

# ----------------------------------------------------------------
# 既定値
# ----------------------------------------------------------------
DEFAULT_AUDIT_DIR="docs/audit/2026-05-16_v3"
GENERIC_PHRASE_REGEX='shall implement T-[A-Z0-9-]+ as specified'

# Tier セクションヘッダ (^...$ 完全一致)
TIER1_HEADER="## Tier 1: Structural"
TIER2_HEADER="## Tier 2: Functional"
TIER3_HEADER="## Tier 3: Regression"

# ----------------------------------------------------------------
# ヘルプ
# ----------------------------------------------------------------
usage() {
  cat <<'EOF'
audit-md-check.sh — Build-Factory pre-flight audit MD validator (Gate #4)

USAGE:
  scripts/audit-md-check.sh <task_id>
  scripts/audit-md-check.sh --all [--audit-dir <path>]
  scripts/audit-md-check.sh --self-test
  scripts/audit-md-check.sh --help

OPTIONS:
  --audit-dir <path>   監査 MD の配置 dir (default: docs/audit/2026-05-16_v3)
  --all                tickets.json (docs/task-decomposition/*/tickets.json) 全 task 検証
  --self-test          内蔵 4 fixture を実行
  --help               このヘルプを表示

EXIT CODES:
  0   全 PASS
  1   audit MD ファイルが見つからない
  2   3 セクション欠落 / generic phrase 検出
  64  引数誤り
EOF
}

# ----------------------------------------------------------------
# 単一 audit MD 検証
#   $1: task_id (T- プレフィクス込み or 無し)
#   $2: audit_dir
#   exit: 0 / 1 / 2
# ----------------------------------------------------------------
# AC-F1: EVENT-DRIVEN 有効な audit MD なら exit 0
# AC-F2: UNWANTED ファイル不在なら exit 1 + 'audit MD not found: <path>' to stderr
# AC-F3: UNWANTED 3 セクション欠落なら exit 2 + 欠損 list
# AC-F4: UNWANTED generic phrase 検出なら exit 2 + 'generic phrase detected at line N'
check_one() {
  local raw_id="$1"
  local audit_dir="$2"

  # T- プレフィクスを正規化 (raw_id が "FOUNDATION-01" でも "T-FOUNDATION-01" でも OK)
  local task_id="${raw_id#T-}"
  local md_path="${audit_dir}/T-${task_id}.md"

  # AC-F2: ファイル存在チェック
  if [[ ! -f "${md_path}" ]]; then
    echo "audit MD not found: ${md_path}" >&2
    return 1
  fi

  # AC-F3: 3 セクション必須
  local missing=()
  if ! grep -qE "^${TIER1_HEADER}\$" "${md_path}"; then
    missing+=("${TIER1_HEADER}")
  fi
  if ! grep -qE "^${TIER2_HEADER}\$" "${md_path}"; then
    missing+=("${TIER2_HEADER}")
  fi
  if ! grep -qE "^${TIER3_HEADER}\$" "${md_path}"; then
    missing+=("${TIER3_HEADER}")
  fi

  if [[ "${#missing[@]}" -gt 0 ]]; then
    echo "audit MD structurally invalid: ${md_path}" >&2
    echo "  missing sections:" >&2
    local s
    for s in "${missing[@]}"; do
      echo "    - ${s}" >&2
    done
    return 2
  fi

  # AC-F4: generic phrase 検出
  local hit
  hit="$(grep -nEi "${GENERIC_PHRASE_REGEX}" "${md_path}" || true)"
  if [[ -n "${hit}" ]]; then
    echo "generic phrase detected in ${md_path}:" >&2
    local line_no
    while IFS= read -r line; do
      line_no="${line%%:*}"
      echo "  generic phrase detected at line ${line_no}: ${line#*:}" >&2
    done <<< "${hit}"
    return 2
  fi

  return 0
}

# ----------------------------------------------------------------
# --all モード: tickets.json から task id を列挙し全件検証
#   AC-F6: OPTIONAL --all で aggregate (worst exit code wins)
# ----------------------------------------------------------------
check_all() {
  local audit_dir="$1"
  local worst_exit=0

  # tickets.json 群を取得 (docs/task-decomposition/*/tickets.json)
  local tickets_files=()
  while IFS= read -r f; do
    tickets_files+=("${f}")
  done < <(find docs/task-decomposition -name tickets.json -type f 2>/dev/null | sort)

  if [[ "${#tickets_files[@]}" -eq 0 ]]; then
    echo "no tickets.json found under docs/task-decomposition/" >&2
    return 64
  fi

  # jq 必須
  if ! command -v jq >/dev/null 2>&1; then
    echo "jq is required for --all mode but not found in PATH" >&2
    return 64
  fi

  local tf
  for tf in "${tickets_files[@]}"; do
    # 配列形式 (T-FOUNDATION-01 タイプ) と objects.tasks[].id を両方サポート
    local ids
    ids="$(jq -r '
      if type == "array" then .[]
      elif .tasks then .tasks[]
      else empty
      end
      | .id // empty
    ' "${tf}" 2>/dev/null || true)"

    if [[ -z "${ids}" ]]; then
      continue
    fi

    local id
    while IFS= read -r id; do
      [[ -z "${id}" ]] && continue
      check_one "${id}" "${audit_dir}"
      local rc=$?
      if [[ "${rc}" -gt "${worst_exit}" ]]; then
        worst_exit="${rc}"
      fi
    done <<< "${ids}"
  done

  return "${worst_exit}"
}

# ----------------------------------------------------------------
# --self-test: 4 fixture を順次検証
#   AC-F5: OPTIONAL --self-test で 4 cases 全 expected と一致なら exit 0
# ----------------------------------------------------------------
self_test() {
  local fixture_dir="scripts/tests/fixtures"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "${tmp_dir}"' RETURN

  local pass=0
  local fail=0

  # Case 1: valid fixture → expect exit 0
  cp "${fixture_dir}/audit-md-valid.md" "${tmp_dir}/T-FIXTURE-VALID.md"
  local rc1=0
  check_one "FIXTURE-VALID" "${tmp_dir}" >/dev/null 2>&1 || rc1=$?
  if [[ "${rc1}" -eq 0 ]]; then
    echo "  [PASS] case 1: valid fixture → exit 0"
    pass=$((pass + 1))
  else
    echo "  [FAIL] case 1: valid fixture → expected 0, got ${rc1}" >&2
    fail=$((fail + 1))
  fi

  # Case 2: missing section fixture → expect exit 2
  cp "${fixture_dir}/audit-md-missing-section.md" "${tmp_dir}/T-FIXTURE-MISSING.md"
  local rc2=0
  check_one "FIXTURE-MISSING" "${tmp_dir}" >/dev/null 2>&1 || rc2=$?
  if [[ "${rc2}" -eq 2 ]]; then
    echo "  [PASS] case 2: missing Tier 1 section → exit 2"
    pass=$((pass + 1))
  else
    echo "  [FAIL] case 2: missing section → expected 2, got ${rc2}" >&2
    fail=$((fail + 1))
  fi

  # Case 3: generic phrase fixture → expect exit 2
  cp "${fixture_dir}/audit-md-generic-phrase.md" "${tmp_dir}/T-FIXTURE-GENERIC.md"
  local rc3=0
  check_one "FIXTURE-GENERIC" "${tmp_dir}" >/dev/null 2>&1 || rc3=$?
  if [[ "${rc3}" -eq 2 ]]; then
    echo "  [PASS] case 3: generic phrase detected → exit 2"
    pass=$((pass + 1))
  else
    echo "  [FAIL] case 3: generic phrase → expected 2, got ${rc3}" >&2
    fail=$((fail + 1))
  fi

  # Case 4: non-existent file → expect exit 1
  local rc4=0
  check_one "FIXTURE-DOES-NOT-EXIST" "${tmp_dir}" >/dev/null 2>&1 || rc4=$?
  if [[ "${rc4}" -eq 1 ]]; then
    echo "  [PASS] case 4: non-existent file → exit 1"
    pass=$((pass + 1))
  else
    echo "  [FAIL] case 4: non-existent → expected 1, got ${rc4}" >&2
    fail=$((fail + 1))
  fi

  echo ""
  echo "self-test summary: ${pass} passed / ${fail} failed (4 cases)"

  if [[ "${fail}" -eq 0 ]]; then
    return 0
  fi
  return 2
}

# ----------------------------------------------------------------
# 引数 parser (long opts は手動)
# ----------------------------------------------------------------
MODE=""              # "single" / "all" / "self-test" / "help"
TASK_ID=""
AUDIT_DIR="${DEFAULT_AUDIT_DIR}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      MODE="help"
      shift
      ;;
    --self-test)
      MODE="self-test"
      shift
      ;;
    --all)
      MODE="all"
      shift
      ;;
    --audit-dir)
      if [[ $# -lt 2 ]]; then
        echo "--audit-dir requires a path argument" >&2
        usage >&2
        exit 64
      fi
      AUDIT_DIR="$2"
      shift 2
      ;;
    --audit-dir=*)
      AUDIT_DIR="${1#--audit-dir=}"
      shift
      ;;
    --)
      shift
      break
      ;;
    -*)
      echo "unknown option: $1" >&2
      usage >&2
      exit 64
      ;;
    *)
      if [[ -z "${TASK_ID}" ]]; then
        TASK_ID="$1"
        MODE="${MODE:-single}"
      else
        echo "unexpected extra argument: $1" >&2
        usage >&2
        exit 64
      fi
      shift
      ;;
  esac
done

# ----------------------------------------------------------------
# モードに応じてディスパッチ
# ----------------------------------------------------------------
if [[ "${MODE}" == "help" ]]; then
  usage
  exit 0
fi

if [[ "${MODE}" == "self-test" ]]; then
  self_test
  exit $?
fi

if [[ "${MODE}" == "all" ]]; then
  check_all "${AUDIT_DIR}"
  exit $?
fi

if [[ "${MODE}" == "single" ]]; then
  if [[ -z "${TASK_ID}" ]]; then
    echo "task_id is required" >&2
    usage >&2
    exit 64
  fi
  check_one "${TASK_ID}" "${AUDIT_DIR}"
  exit $?
fi

# モード未指定
echo "no mode specified" >&2
usage >&2
exit 64
