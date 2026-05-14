"""T-AI-MEM-02: Anthropic Context Editing config — 4 AC 1:1 spec test (dedicated).

Audit doc: docs/audit/2026-05-13_v2/T-AI-MEM-02.md

このファイルは tickets.json#T-AI-MEM-02 の 4 EARS AC × 30 sub-clause を
1:1 で検証する dedicated 仕様テスト. 既存の test_adr_012_anthropic_memory_tool.py
は context editing も扱うが mixed (Memory Tool 全体). 本 file は AC 1:1 のみに
集中して spec drift を機械的に検出する.

AC mapping:
  AC-1 UBIQUITOUS    : default_context_management_config() が anthropic-python
                       client.beta.messages.create(..., context_management=...)
                       互換 dict を返し, Memory tool が exclude_tools=['memory']
                       で保護されること.
  AC-2 EVENT-DRIVEN  : config 要求は 2 秒以内に return + 既定 beta headers
                       ('context-management-2025-06-27' + 'compact-2026-01-12')
                       同梱.
  AC-3 STATE-DRIVEN  : compact_20260112 trigger >= 50,000 input_tokens (公式制約) +
                       clear_thinking_20251015 (有効時) は edits[] 先頭.
  AC-4 UNWANTED      : (a) app code に server-side compaction / tool result clearing
                       自前実装があれば lint script fail. (b) invalid config
                       (compact <50K / 順序違反 / unknown strategy) は ContextEditingError
                       + persistent state mutate なし.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import anthropic_context_editing as ce


# ──────────────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS: default_context_management_config() returns SDK-compatible dict
#                   with Memory tool protected via exclude_tools=['memory']
# ══════════════════════════════════════════════════════════════════════


def test_ac1_default_config_callable_exists():
    """1.1: `default_context_management_config()` 公開関数として存在."""
    assert hasattr(ce, "default_context_management_config")
    assert callable(ce.default_context_management_config)


def test_ac1_returns_dict():
    """1.2: 戻り値は dict."""
    cfg = ce.default_context_management_config()
    assert isinstance(cfg, dict)


def test_ac1_dict_has_edits_key_for_sdk_compat():
    """1.3: dict に `edits` キー (anthropic-python `context_management=` shape)."""
    cfg = ce.default_context_management_config()
    assert "edits" in cfg, (
        "anthropic-python SDK は context_management={'edits': [...]} 形式を要求 "
        "(client.beta.messages.create context_management= に渡せる)"
    )
    assert isinstance(cfg["edits"], list)


def test_ac1_edits_each_item_has_type_and_trigger():
    """1.4: edits[] 各 item は type / trigger を持つ dict."""
    cfg = ce.default_context_management_config()
    assert len(cfg["edits"]) >= 1
    for i, e in enumerate(cfg["edits"]):
        assert isinstance(e, dict), f"edits[{i}] must be dict"
        assert "type" in e, f"edits[{i}].type missing"
        assert "trigger" in e, f"edits[{i}].trigger missing"
        assert isinstance(e["trigger"], dict), f"edits[{i}].trigger must be dict"


def test_ac1_memory_protected_in_exclude_tools():
    """1.5: Memory tool 保護 — clear_tool_uses の exclude_tools に 'memory' 必須."""
    cfg = ce.default_context_management_config()
    clears = [e for e in cfg["edits"] if e["type"] == ce.STRATEGY_CLEAR_TOOL_USES]
    assert len(clears) == 1, "既定で clear_tool_uses 1 件必須"
    excl = clears[0].get("exclude_tools")
    assert isinstance(excl, list)
    assert "memory" in excl, (
        "Memory tool 結果は clear_tool_uses 対象外 (ADR-012 Decision 2). "
        "永続記憶の clearing を防ぐ"
    )


def test_ac1_default_includes_clear_tool_uses_strategy():
    """1.6: 既定 config に clear_tool_uses_20250919 strategy 含む."""
    cfg = ce.default_context_management_config()
    types = [e["type"] for e in cfg["edits"]]
    assert ce.STRATEGY_CLEAR_TOOL_USES in types
    assert ce.STRATEGY_CLEAR_TOOL_USES == "clear_tool_uses_20250919"


def test_ac1_default_includes_compact_strategy():
    """1.7: 既定 config に compact_20260112 strategy 含む."""
    cfg = ce.default_context_management_config()
    types = [e["type"] for e in cfg["edits"]]
    assert ce.STRATEGY_COMPACT in types
    assert ce.STRATEGY_COMPACT == "compact_20260112"


def test_ac1_extra_protected_tools_merged_no_dup():
    """1.8: extra_protected_tools で 'memory' 重複防止 + 追加 tool マージ."""
    cfg = ce.default_context_management_config(
        extra_protected_tools=["web_search", "memory"],
    )
    clear = next(e for e in cfg["edits"] if e["type"] == ce.STRATEGY_CLEAR_TOOL_USES)
    excl = clear["exclude_tools"]
    assert "memory" in excl
    assert "web_search" in excl
    # memory が重複しない
    assert excl.count("memory") == 1, f"memory が重複: {excl}"


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN: config 要求は 2 秒以内 + recommended beta headers 同梱
# ══════════════════════════════════════════════════════════════════════


def test_ac2_default_config_returns_within_2sec():
    """2.1: factory は 2 秒以内に return (pure / 副作用なし設計)."""
    start = time.monotonic()
    cfg = ce.default_context_management_config()
    elapsed = time.monotonic() - start
    assert elapsed < 2.0, f"factory が {elapsed:.3f}s かかった (>2s = NG)"
    assert isinstance(cfg, dict)


def test_ac2_betas_include_context_management_2025_06_27():
    """2.2: recommended_beta_headers() に 'context-management-2025-06-27' 含む."""
    headers = ce.recommended_beta_headers()
    assert isinstance(headers, list)
    assert "context-management-2025-06-27" in headers
    # constant alias も一致していること
    assert ce.BETA_HEADER_CONTEXT_MANAGEMENT == "context-management-2025-06-27"


def test_ac2_betas_include_compact_2026_01_12():
    """2.3: recommended_beta_headers() に 'compact-2026-01-12' 含む."""
    headers = ce.recommended_beta_headers()
    assert "compact-2026-01-12" in headers
    assert ce.BETA_HEADER_COMPACT == "compact-2026-01-12"


def test_ac2_rest_endpoint_returns_betas_within_2sec(client):
    """2.4: REST endpoint `GET /api/anthropic-memory/context-editing` が
    betas 同梱で 2 秒以内 return."""
    start = time.monotonic()
    r = client.get("/api/anthropic-memory/context-editing")
    elapsed = time.monotonic() - start
    assert r.status_code == 200, r.text
    assert elapsed < 2.0, f"REST endpoint が {elapsed:.3f}s かかった (>2s = NG)"
    body = r.json()
    assert "context_management" in body
    assert "betas" in body
    assert "context-management-2025-06-27" in body["betas"]
    assert "compact-2026-01-12" in body["betas"]


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN: compact trigger >= 50,000 input_tokens +
#                    clear_thinking (when enabled) is first in edits[]
# ══════════════════════════════════════════════════════════════════════


def test_ac3_default_compact_trigger_meets_50k_floor():
    """3.1: 既定 compact trigger >= 50,000 input_tokens (公式制約)."""
    cfg = ce.default_context_management_config()
    compact = next(e for e in cfg["edits"] if e["type"] == ce.STRATEGY_COMPACT)
    assert compact["trigger"]["value"] >= 50_000, (
        f"compact trigger {compact['trigger']['value']} < 50,000 "
        "(公式 doc 制約違反)"
    )


def test_ac3_compact_trigger_type_is_input_tokens():
    """3.2: compact strategy の trigger.type == 'input_tokens' (公式型)."""
    cfg = ce.default_context_management_config()
    compact = next(e for e in cfg["edits"] if e["type"] == ce.STRATEGY_COMPACT)
    assert compact["trigger"]["type"] == "input_tokens"


def test_ac3_all_strategies_trigger_type_input_tokens():
    """3.3: 全 strategy の trigger.type == 'input_tokens' (validator 公式制約)."""
    cfg = ce.default_context_management_config(enable_clear_thinking=True)
    for i, e in enumerate(cfg["edits"]):
        assert e["trigger"]["type"] == "input_tokens", (
            f"edits[{i}] type={e['type']}: trigger.type={e['trigger']['type']!r} "
            "must be 'input_tokens'"
        )


def test_ac3_clear_thinking_when_enabled_is_first_in_edits():
    """3.4: clear_thinking 有効時, edits[0] (先頭) (公式制約)."""
    cfg = ce.default_context_management_config(enable_clear_thinking=True)
    assert len(cfg["edits"]) >= 1
    assert cfg["edits"][0]["type"] == ce.STRATEGY_CLEAR_THINKING, (
        f"clear_thinking 有効時 edits[0] = {cfg['edits'][0]['type']!r} "
        f"(must be {ce.STRATEGY_CLEAR_THINKING!r})"
    )


def test_ac3_clear_thinking_when_disabled_absent_from_edits():
    """3.5: clear_thinking 無効時 (既定), edits[] に含まれない (negative)."""
    cfg = ce.default_context_management_config()  # 既定 enable_clear_thinking=False
    types = [e["type"] for e in cfg["edits"]]
    assert ce.STRATEGY_CLEAR_THINKING not in types, (
        f"clear_thinking 無効時に含まれている: {types}"
    )


def test_ac3_full_strategy_order_thinking_clear_compact():
    """3.6: 全 strategy 有効時, 順序 = clear_thinking → clear_tool_uses → compact."""
    cfg = ce.default_context_management_config(
        enable_clear_thinking=True,
        enable_clear_tool_uses=True,
        enable_compact=True,
    )
    types = [e["type"] for e in cfg["edits"]]
    assert types == [
        ce.STRATEGY_CLEAR_THINKING,
        ce.STRATEGY_CLEAR_TOOL_USES,
        ce.STRATEGY_COMPACT,
    ], f"expected order [thinking, clear, compact], got {types}"


def test_ac3_validator_rejects_compact_below_50k():
    """3.7: validator が compact trigger < 50K を reject."""
    bad = {
        "edits": [{
            "type": ce.STRATEGY_COMPACT,
            "trigger": {"type": "input_tokens", "value": 49_999},
        }],
    }
    with pytest.raises(ce.ContextEditingError, match="compact_20260112"):
        ce.validate_config(bad)


def test_ac3_validator_rejects_misordered_clear_thinking():
    """3.8: validator が clear_thinking 非先頭を reject."""
    bad = {"edits": [
        {"type": ce.STRATEGY_CLEAR_TOOL_USES,
         "trigger": {"type": "input_tokens", "value": 1000},
         "keep": {"type": "tool_uses", "value": 1}},
        {"type": ce.STRATEGY_CLEAR_THINKING,
         "trigger": {"type": "input_tokens", "value": 1000},
         "keep": {"type": "thinking_uses", "value": 1}},
    ]}
    with pytest.raises(ce.ContextEditingError, match="must be placed first"):
        ce.validate_config(bad)


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED: lint guard for self-impl + ContextEditingError on invalid config +
#                NO mutate persistent state
# ══════════════════════════════════════════════════════════════════════


def test_ac4_lint_guard_no_self_tool_trim_in_repo(repo_root):
    """4.1: 既存 lint check `check_no_self_tool_trim` が tool result clearing
    自前実装の禁止語を検知する (lint script は repo 内 1 箇所も hit しない PASS 状態)."""
    script = repo_root / "scripts" / "lint-mock.sh"
    assert script.exists()
    result = subprocess.run(
        ["bash", str(script), "--no-self-tool-trim"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    assert result.returncode == 0, (
        f"lint --no-self-tool-trim 失敗: stdout={result.stdout} stderr={result.stderr}"
    )
    assert "OK" in result.stdout


def test_ac4_lint_guard_no_self_compaction_in_repo(repo_root):
    """4.2: 新 lint check `check_no_self_compaction` (#14, G11) が
    server-side compaction 自前実装の禁止語を検知する (repo は PASS 状態)."""
    script = repo_root / "scripts" / "lint-mock.sh"
    # script に #14 が定義されていることを確認
    src = script.read_text(encoding="utf-8")
    assert "check_no_self_compaction" in src, (
        "lint script に check_no_self_compaction が未定義 (G11 未閉鎖). "
        "AC-4 'application code re-implements server-side compaction → lint shall fail' を機械保証できない"
    )
    result = subprocess.run(
        ["bash", str(script), "--no-self-compaction"],
        capture_output=True, text=True, cwd=str(repo_root),
    )
    assert result.returncode == 0, (
        f"lint --no-self-compaction 失敗: stdout={result.stdout} stderr={result.stderr}"
    )
    assert "OK" in result.stdout


def test_ac4_factory_raises_on_compact_below_50k():
    """4.3: factory が compact_trigger < 50K で `ContextEditingError` raise."""
    with pytest.raises(ce.ContextEditingError, match=r">= 50,000|公式"):
        ce.default_context_management_config(compact_trigger=10_000)


def test_ac4_validator_raises_on_compact_below_50k():
    """4.4: validator が compact trigger < 50K で `ContextEditingError` raise."""
    bad = {"edits": [{
        "type": ce.STRATEGY_COMPACT,
        "trigger": {"type": "input_tokens", "value": 49_999},
    }]}
    with pytest.raises(ce.ContextEditingError):
        ce.validate_config(bad)


def test_ac4_validator_raises_on_misordered_clear_thinking():
    """4.5: validator が clear_thinking 非先頭で `ContextEditingError` raise."""
    bad = {"edits": [
        {"type": ce.STRATEGY_CLEAR_TOOL_USES,
         "trigger": {"type": "input_tokens", "value": 1000},
         "keep": {"type": "tool_uses", "value": 1}},
        {"type": ce.STRATEGY_CLEAR_THINKING,
         "trigger": {"type": "input_tokens", "value": 1000},
         "keep": {"type": "thinking_uses", "value": 1}},
    ]}
    with pytest.raises(ce.ContextEditingError):
        ce.validate_config(bad)


def test_ac4_validator_raises_on_unknown_strategy_type():
    """4.6: validator が unknown strategy type で `ContextEditingError` raise."""
    bad = {"edits": [{
        "type": "unknown_strategy_xyz_99999",
        "trigger": {"type": "input_tokens", "value": 100_000},
    }]}
    with pytest.raises(ce.ContextEditingError, match="must be one of"):
        ce.validate_config(bad)


def test_ac4_factory_raise_does_not_mutate_state():
    """4.7: factory raise 時 persistent state mutate なし.

    factory は pure (副作用なし) 設計. raise 後も module-level の状態が変化しない."""
    # baseline: 既存 module 属性のスナップショット
    snap_before = {
        "DEFAULT_COMPACT_TRIGGER_TOKENS": ce.DEFAULT_COMPACT_TRIGGER_TOKENS,
        "DEFAULT_CLEAR_TOOL_USES_TRIGGER_TOKENS": ce.DEFAULT_CLEAR_TOOL_USES_TRIGGER_TOKENS,
        "PROTECTED_TOOLS": ce.PROTECTED_TOOLS,
        "VALID_STRATEGY_TYPES": ce.VALID_STRATEGY_TYPES,
    }
    # invalid 呼出 → raise
    with pytest.raises(ce.ContextEditingError):
        ce.default_context_management_config(compact_trigger=100)
    # 状態が不変
    snap_after = {
        "DEFAULT_COMPACT_TRIGGER_TOKENS": ce.DEFAULT_COMPACT_TRIGGER_TOKENS,
        "DEFAULT_CLEAR_TOOL_USES_TRIGGER_TOKENS": ce.DEFAULT_CLEAR_TOOL_USES_TRIGGER_TOKENS,
        "PROTECTED_TOOLS": ce.PROTECTED_TOOLS,
        "VALID_STRATEGY_TYPES": ce.VALID_STRATEGY_TYPES,
    }
    assert snap_before == snap_after, (
        f"factory raise 後に module 状態が変化: before={snap_before} after={snap_after}"
    )
    # raise 後でも valid な再呼出が成功し既定 config が返る (副作用がない証左)
    cfg = ce.default_context_management_config()
    assert "edits" in cfg


def test_ac4_validator_raise_does_not_mutate_state():
    """4.8: validator raise 時 persistent state mutate なし."""
    snap_before = (
        ce.DEFAULT_COMPACT_TRIGGER_TOKENS,
        ce.PROTECTED_TOOLS,
        ce.VALID_STRATEGY_TYPES,
    )
    bad = {"edits": [{
        "type": "unknown_xyz",
        "trigger": {"type": "input_tokens", "value": 100_000},
    }]}
    with pytest.raises(ce.ContextEditingError):
        ce.validate_config(bad)
    snap_after = (
        ce.DEFAULT_COMPACT_TRIGGER_TOKENS,
        ce.PROTECTED_TOOLS,
        ce.VALID_STRATEGY_TYPES,
    )
    assert snap_before == snap_after
    # 既定 config 生成は引き続き正常動作
    cfg = ce.default_context_management_config()
    ce.validate_config(cfg)  # raise しない


def test_ac4_env_override_truthy_returns_none(monkeypatch):
    """4.9: env `CONTEXT_MGMT_DISABLE` truthy 値 → None (skip 指示)."""
    for truthy in ("1", "true", "TRUE", "yes", "YES", "on", "ON"):
        monkeypatch.setenv("CONTEXT_MGMT_DISABLE", truthy)
        assert ce.env_override_config() is None, (
            f"truthy={truthy!r} で None を期待 (skip 指示)"
        )


def test_ac4_env_override_falsy_returns_default(monkeypatch):
    """4.10: env `CONTEXT_MGMT_DISABLE` falsy/未設定 → 既定 config 返却."""
    for falsy in ("0", "false", "no", "off", ""):
        monkeypatch.setenv("CONTEXT_MGMT_DISABLE", falsy)
        cfg = ce.env_override_config()
        assert cfg is not None, f"falsy={falsy!r} で既定 config を期待"
        assert "edits" in cfg
    # 未設定でも default
    monkeypatch.delenv("CONTEXT_MGMT_DISABLE", raising=False)
    cfg = ce.env_override_config()
    assert cfg is not None
    assert "edits" in cfg


# ══════════════════════════════════════════════════════════════════════
# Audit doc traceability + lint script integration sanity
# ══════════════════════════════════════════════════════════════════════


def test_audit_doc_exists_and_links_to_this_file(repo_root):
    """audit doc が存在し本 test file を 1:1 で参照していること."""
    audit_path = repo_root / "docs" / "audit" / "2026-05-13_v2" / "T-AI-MEM-02.md"
    assert audit_path.exists(), (
        f"audit doc 未存在: {audit_path} (pre-flight workflow Step 1 違反)"
    )
    text = audit_path.read_text(encoding="utf-8")
    assert "T-AI-MEM-02" in text
    assert "test_t_ai_mem_02_context_editing_spec.py" in text or \
           "test_ac1_default_config_callable_exists" in text


def test_lint_script_exposes_no_self_compaction_flag(repo_root):
    """lint-mock.sh が `--no-self-compaction` flag を case 文に登録していること.

    G11 で追加した #14 check が CLI から起動可能であることの sanity."""
    script_text = (repo_root / "scripts" / "lint-mock.sh").read_text(encoding="utf-8")
    assert "--no-self-compaction" in script_text, (
        "scripts/lint-mock.sh の case 文に --no-self-compaction が未登録 (G11 未閉鎖)"
    )
    assert "check_no_self_compaction" in script_text


def test_lint_full_run_passes(repo_root):
    """lint-mock.sh `all` (既定) が exit 0 であること (regression なし)."""
    result = subprocess.run(
        ["bash", str(repo_root / "scripts" / "lint-mock.sh")],
        capture_output=True, text=True, cwd=str(repo_root),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"lint-mock.sh 失敗: stdout={result.stdout[-2000:]} stderr={result.stderr[-1000:]}"
    )
    # server-side compaction check が走っており最後の check (number=total) であることを確認
    # number/total は main の状態に応じて変動するため regex で柔軟 match
    import re
    m = re.search(r"\[(\d+)/(\d+)\] server-side compaction", result.stdout)
    assert m, (
        f"server-side compaction check が走っていない. stdout 末尾:\n{result.stdout[-2000:]}"
    )
    assert m.group(1) == m.group(2), (
        f"server-side compaction が最後の check として走っていない: {m.group(0)}"
    )
