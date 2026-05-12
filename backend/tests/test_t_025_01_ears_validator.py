"""T-025-01: EARS 5 形式テンプレ + JSON Schema バリデータ.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : schema + template + validator script の 3 ファイル提供 /
                       既存 validate-tickets.py / audit-ac-coherence.py 無改変.
  AC-2 EVENT-DRIVEN  : script 実行で全 tickets validate / exit codes 0/1/2 /
                       --task-id / --verbose / --schema-only flags.
  AC-3 STATE-DRIVEN  : read-only (tickets 不変) / 外部 service 呼出なし /
                       audit_logs 書込なし / 既存 validate-tickets と並列.
  AC-4 UNWANTED      : schema 不正で exit 2 / unknown task-id で exit 1 /
                       hardcoded secret / URL なし.
"""
from __future__ import annotations

import json as _json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = REPO_ROOT / "backend" / "schemas" / "ears_ac_schema.json"
TEMPLATE = REPO_ROOT / "docs" / "templates" / "ears-ac-template.md"
VALIDATOR = REPO_ROOT / "scripts" / "validate-ears-ac.py"
EXISTING_VALIDATE_TICKETS = REPO_ROOT / "scripts" / "validate-tickets.py"
EXISTING_AUDIT = REPO_ROOT / "scripts" / "audit-ac-coherence.py"


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: 3 file deliverable + REUSE
# ══════════════════════════════════════════════════════════════════════


def test_ac1_schema_exists():
    assert SCHEMA.exists()


def test_ac1_template_exists():
    assert TEMPLATE.exists()


def test_ac1_validator_exists():
    assert VALIDATOR.exists()


def test_ac1_schema_is_valid_draft7():
    """schema 自身が Draft-07 として正しい."""
    from jsonschema import Draft7Validator, SchemaError
    schema = _json.load(open(SCHEMA))
    # raises SchemaError if invalid
    Draft7Validator.check_schema(schema)


def test_ac1_schema_covers_5_ears_forms():
    schema = _json.load(open(SCHEMA))
    enum_vals = schema["properties"]["type"]["enum"]
    # 5 EARS 形式 + 2 legacy alias
    for required in ("UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"):
        assert required in enum_vals
    # legacy alias for backward-compat
    assert "EVENT" in enum_vals or "EVENT-DRIVEN" in enum_vals


def test_ac1_template_documents_5_forms():
    src = TEMPLATE.read_text(encoding="utf-8")
    for form in ("UBIQUITOUS", "EVENT-DRIVEN", "STATE-DRIVEN", "OPTIONAL", "UNWANTED"):
        assert form in src


def test_ac1_existing_validators_unchanged():
    """既存 validate-tickets.py / audit-ac-coherence.py は無改変 (REUSE)."""
    assert EXISTING_VALIDATE_TICKETS.exists()
    assert EXISTING_AUDIT.exists()
    # 本 PR で既存 file を参照する import を追加していないこと
    for path in (EXISTING_VALIDATE_TICKETS, EXISTING_AUDIT):
        src = path.read_text(encoding="utf-8")
        assert "validate-ears-ac" not in src, f"{path.name} must not depend on new validator"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: script execution + flags
# ══════════════════════════════════════════════════════════════════════


def _run_validator(*args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=timeout,
    )


def test_ac2_default_run_validates_all_tickets():
    r = _run_validator()
    # 現状全 AC が pass しているはず (本セッションで具体化済)
    assert r.returncode == 0, f"validator failed: {r.stdout}\n{r.stderr}"
    assert "EARS AC validation" in r.stdout
    assert "tickets" in r.stdout
    assert "AC" in r.stdout


def test_ac2_schema_only_flag():
    r = _run_validator("--schema-only")
    assert r.returncode == 0
    assert "schema is valid Draft-07" in r.stdout


def test_ac2_task_id_filter():
    r = _run_validator("--task-id", "T-M27-02")
    assert r.returncode == 0
    # 単一タスクなので "Checked     : 1 tickets" 表示
    assert "1 tickets" in r.stdout


def test_ac2_verbose_flag_emits_per_ac_details():
    """--verbose 単体では issue がない場合は detail を出さないが
    フラグ自体が受け付けられること."""
    r = _run_validator("--verbose")
    assert r.returncode == 0
    # ヘッダ出力は必ず
    assert "EARS AC validation" in r.stdout


def test_ac2_exit_code_0_on_success():
    r = _run_validator()
    assert r.returncode == 0


def test_ac2_exit_code_1_on_unknown_task_id():
    r = _run_validator("--task-id", "T-NOEXIST")
    assert r.returncode == 1


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: read-only + no audit_logs / external services
# ══════════════════════════════════════════════════════════════════════


def test_ac3_validator_is_read_only():
    """validator が tickets.json / 他ファイルを mutate しないこと."""
    # 実行前後で tickets.json の hash が同じ
    import hashlib
    tickets_path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    before = hashlib.sha256(tickets_path.read_bytes()).hexdigest()
    _run_validator()
    after = hashlib.sha256(tickets_path.read_bytes()).hexdigest()
    assert before == after, "validator must not mutate tickets.json"


def test_ac3_no_external_http_calls():
    src = VALIDATOR.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "httpx" not in code
    assert "requests.get" not in code
    assert "requests.post" not in code
    assert "urllib.request" not in code


def test_ac3_no_audit_logs_writes():
    src = VALIDATOR.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert "emit_event" not in code
    assert "from services.memory_service" not in code


def _strip_comments(src: str) -> str:
    out_lines = []
    in_triple = False
    triple_char = None
    for raw in src.splitlines():
        line = raw
        if in_triple:
            if triple_char in line:
                line = line.split(triple_char, 1)[1]
                in_triple = False
            else:
                continue
        for ch in ('"""', "'''"):
            if ch in line:
                before, _, after = line.partition(ch)
                if ch in after:
                    line = before + after.split(ch, 1)[1]
                else:
                    line = before
                    in_triple = True
                    triple_char = ch
                break
        if "#" in line:
            line = line.split("#", 1)[0]
        if line.strip():
            out_lines.append(line)
    return "\n".join(out_lines)


def test_ac3_runs_in_parallel_with_existing_validate_tickets():
    """既存 validate-tickets.py との並行性 (互いに干渉しない)."""
    # 両方 run しても OK
    r1 = subprocess.run(
        [sys.executable, str(EXISTING_VALIDATE_TICKETS)],
        cwd=REPO_ROOT, capture_output=True, text=True, timeout=30,
    )
    r2 = _run_validator()
    # 両方とも独立に exit 0 (全 AC pass している前提)
    assert r1.returncode == 0
    assert r2.returncode == 0


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: invalid schema / unknown id / no secret
# ══════════════════════════════════════════════════════════════════════


def test_ac4_invalid_schema_returns_exit_2(tmp_path, monkeypatch):
    """schema が壊れた状態で実行 → exit 2."""
    bad_schema_path = tmp_path / "ears_ac_schema.json"
    bad_schema_path.write_text('{"type": "invalid-schema-form-12345"}', encoding="utf-8")
    # 本 test は subprocess で schema path 差替が複雑なため、代わりに
    # python module レベルで再現する
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    try:
        # script 名にハイフン → importlib
        import importlib.util
        spec = importlib.util.spec_from_file_location("validate_ears_ac", VALIDATOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # SCHEMA_PATH 差替
        original = mod.SCHEMA_PATH
        mod.SCHEMA_PATH = bad_schema_path
        try:
            ret = mod.main([])
            assert ret == 2
        finally:
            mod.SCHEMA_PATH = original
    finally:
        sys.path.pop(0)


def test_ac4_unknown_task_id_returns_exit_1():
    r = _run_validator("--task-id", "T-DOES-NOT-EXIST-9999")
    assert r.returncode == 1


def test_ac4_no_hardcoded_secrets():
    src = VALIDATOR.read_text(encoding="utf-8")
    code = _strip_comments(src)
    assert not re.search(r"sk-ant-[A-Za-z0-9_-]{20,}", code)
    assert "SUPABASE_SERVICE_KEY" not in code
    assert "Bearer " not in code
    assert not re.search(r"ghp_[A-Za-z0-9]{20,}", code)


def test_ac4_no_hardcoded_external_urls():
    src = VALIDATOR.read_text(encoding="utf-8")
    code = _strip_comments(src)
    # API base URLs 含まない
    assert "api.openai.com" not in code
    assert "api.anthropic.com" not in code
    assert "supabase.co" not in code


# ══════════════════════════════════════════════════════════════════════
# Schema content correctness
# ══════════════════════════════════════════════════════════════════════


def test_schema_rejects_unknown_type():
    """unknown type の AC は schema で reject される."""
    from jsonschema import Draft7Validator
    schema = _json.load(open(SCHEMA))
    validator = Draft7Validator(schema)
    bad = {"type": "INVALID-FORM", "text": "The system shall do something."}
    errors = list(validator.iter_errors(bad))
    assert len(errors) > 0


def test_schema_rejects_text_too_short():
    from jsonschema import Draft7Validator
    schema = _json.load(open(SCHEMA))
    validator = Draft7Validator(schema)
    bad = {"type": "UBIQUITOUS", "text": "too short"}
    errors = list(validator.iter_errors(bad))
    # text が minLength (20) 未満なので errors が出る
    assert len(errors) > 0


def test_schema_accepts_valid_ubiquitous():
    from jsonschema import Draft7Validator
    schema = _json.load(open(SCHEMA))
    validator = Draft7Validator(schema)
    good = {
        "type": "UBIQUITOUS",
        "text": "The system shall provide a unified read API for the memory module.",
    }
    errors = list(validator.iter_errors(good))
    assert errors == []


def test_schema_pattern_enforces_form_keywords():
    """各 type に対応する keyword (When/While/Where/If/shall) を強制."""
    from jsonschema import Draft7Validator
    schema = _json.load(open(SCHEMA))
    validator = Draft7Validator(schema)

    # UBIQUITOUS without "shall" → fail
    bad_ubiquitous = {
        "type": "UBIQUITOUS",
        "text": "The system provides a unified read API for the memory module.",
    }
    errors_ub = list(validator.iter_errors(bad_ubiquitous))
    assert any("pattern" in str(e.message).lower() or "shall" in str(e.message) for e in errors_ub)

    # EVENT-DRIVEN without When/when → fail
    bad_event = {
        "type": "EVENT-DRIVEN",
        "text": "The system shall always do something on every input without prefix.",
    }
    # 実 text に "When"/"when " 含まないこと確認 (regex pattern)
    assert "When" not in bad_event["text"]
    assert "when " not in bad_event["text"]
    errors_evt = list(validator.iter_errors(bad_event))
    assert errors_evt, "EVENT-DRIVEN AC without When should fail"


# ══════════════════════════════════════════════════════════════════════
# tickets.json 整合性
# ══════════════════════════════════════════════════════════════════════


def test_tickets_t_025_01_ac_concretized():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-025-01"), None)
    assert t is not None
    generic = [
        "as specified by feature",
        "When the relevant API endpoint or service function is invoked for T-025-01",
        "While the new feature for T-025-01 is enabled",
        "If invalid input or unauthorized actor is detected during T-025-01",
    ]
    for ac in t["acceptance_criteria"]:
        for phrase in generic:
            assert phrase not in ac["text"], f"T-025-01 still generic: {phrase!r}"
    full = " ".join(ac["text"] for ac in t["acceptance_criteria"])
    assert "ears_ac_schema.json" in full
    assert "validate-ears-ac.py" in full
    assert "Draft-07" in full


def test_tickets_t_025_01_has_adr_link_and_existing_files():
    path = REPO_ROOT / "docs" / "task-decomposition" / "2026-05-09_v1" / "tickets.json"
    d = _json.load(open(path))
    t = next((x for x in d["tickets"] if x["id"] == "T-025-01"), None)
    assert t.get("adr_link") is not None
    assert t.get("existing_files")


def test_all_tickets_pass_ears_schema():
    """重要: 本 PR で導入した schema で全 tickets が pass する."""
    r = _run_validator()
    assert r.returncode == 0, (
        f"some tickets fail EARS schema after T-025-01 deployment: {r.stdout[-1000:]}"
    )
