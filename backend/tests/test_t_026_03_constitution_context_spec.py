"""T-026-03: Constitution context 注入 (M-28 連携) — 1:1 spec test.

REFACTOR task. impl 無変更. M-28 Context Builder (services.context_builder)
と F-026 Constitution (services.constitution_engine) の連携 boundary が
要求通り動くことを 1:1 で test 化する.

## AC マッピング (tickets.json T-026-03)

  AC-1 UBIQUITOUS    : F-026 spec (全 AI session の初期 prompt に注入 /
                       env CONSTITUTION_TEXT 優先 / D-XXX.md 連結 /
                       include_constitution default=True / 違反は赤線エスカ)
  AC-2 EVENT-DRIVEN  : POST /api/context/build / GET /api/context/constitution
                       が 2 秒以内に structured response を返す
  AC-3 STATE-DRIVEN  : refactor 後も build_context シグネチャ / return keys /
                       endpoint contract が後方互換 (regression guard)
  AC-4 UNWANTED      : 不正入力で 4xx {detail:{code,message}} + state 不変

## 監査 doc

  docs/audit/2026-05-13_v2/T-026-03.md (gap G1-G9 着手前列挙)
"""
from __future__ import annotations

import asyncio
import inspect
import os
import subprocess
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services import context_builder as cb
from services.context_builder import (
    DECISION_REF_RE,
    build_context,
    is_secretary_active,
    preload_constitution,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def isolated_constitution_dir(tmp_path, monkeypatch):
    """CONSTITUTION_DIR を tmp_path に隔離し env もクリア."""
    monkeypatch.setenv("CONSTITUTION_DIR", str(tmp_path))
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    return tmp_path


# ══════════════════════════════════════════════════════════════════════
# AC-1 UBIQUITOUS — M-28 が F-026 を context として injects
# ══════════════════════════════════════════════════════════════════════


def test_ac1_build_context_injects_constitution_into_block(
    isolated_constitution_dir,
) -> None:
    """AC-1.1: M-28 build_context は F-026 spec に従い constitution を inject する.

    F-026 happy_path: "全 AI session の初期 prompt に注入".
    M-28 (build_context) が返す dict に constitution key が含まれ、
    CONSTITUTION_DIR の D-XXX.md 内容が反映される (M-28 ↔ F-026 boundary).
    """
    (isolated_constitution_dir / "D-026.md").write_text(
        "# F-026 boundary policy\n\n全 AI session に inject される.",
        encoding="utf-8",
    )
    result = asyncio.run(build_context(
        user_message="constitution boundary check",
        session_id=1, user_id="masato",
        include_constitution=True,
    ))
    assert "constitution" in result
    assert "全 AI session に inject" in result["constitution"]


def test_ac1_preload_constitution_env_takes_precedence(
    isolated_constitution_dir, monkeypatch,
) -> None:
    """AC-1.2: env CONSTITUTION_TEXT が CONSTITUTION_DIR より優先.

    `_constitution_dir()` の path 優先順位 (env > home > repo fallback) を
    1:1 で検証. CONSTITUTION_TEXT が設定されていれば DIR 内 D-XXX.md は無視.
    """
    monkeypatch.setenv("CONSTITUTION_TEXT", "ENV WIN")
    (isolated_constitution_dir / "D-001.md").write_text(
        "DIR LOSES", encoding="utf-8",
    )
    text = asyncio.run(preload_constitution())
    assert text == "ENV WIN"
    assert "DIR LOSES" not in text


def test_ac1_preload_constitution_concatenates_all_d_files(
    isolated_constitution_dir, monkeypatch,
) -> None:
    """AC-1.3: CONSTITUTION_DIR 内の D-*.md を全て読み込んで連結."""
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    (isolated_constitution_dir / "D-010.md").write_text("A10", encoding="utf-8")
    (isolated_constitution_dir / "D-011.md").write_text("B11", encoding="utf-8")
    (isolated_constitution_dir / "D-012.md").write_text("C12", encoding="utf-8")
    text = asyncio.run(preload_constitution())
    assert "A10" in text
    assert "B11" in text
    assert "C12" in text


def test_ac1_include_constitution_defaults_to_true() -> None:
    """AC-1.4: F-026 happy_path "全 AI session に inject" を保証するため
    build_context の include_constitution は default=True (suppress は明示要)."""
    sig = inspect.signature(build_context)
    assert sig.parameters["include_constitution"].default is True


def test_ac1_lint_check_12_constitution_self_inject_runs() -> None:
    """AC-1.5: F-026 happy_path "違反は赤線エスカ" → lint check #12 で
    Constitution 自前 inject を機械検知 (T-AI-04 と整合).
    現状の repo state で check が PASS することを smoke 確認.
    """
    script = REPO_ROOT / "scripts" / "lint-mock.sh"
    assert script.exists()
    out = subprocess.run(
        ["bash", str(script), "--no-self-constitution"],
        capture_output=True, text=True, cwd=str(REPO_ROOT),
    )
    # 自前 inject 関数が無い (現状) → PASS (exit 0)
    assert out.returncode == 0, (
        f"lint check #12 unexpectedly failed: {out.stdout}\n{out.stderr}"
    )
    assert "[12/14]" in out.stdout
    assert "Constitution" in out.stdout


# ══════════════════════════════════════════════════════════════════════
# AC-2 EVENT-DRIVEN — 2 秒以内に structured response
# ══════════════════════════════════════════════════════════════════════


def test_ac2_post_context_build_returns_within_2s(
    client, isolated_constitution_dir,
) -> None:
    """AC-2.1: POST /api/context/build は 2 秒以内に structured response."""
    (isolated_constitution_dir / "D-200.md").write_text(
        "# Quick\n\nbody", encoding="utf-8",
    )
    t0 = time.monotonic()
    r = client.post(
        "/api/context/build",
        json={
            "user_message": "hi",
            "session_id": 1,
            "user_id": "masato",
            "include_constitution": True,
        },
    )
    dt = time.monotonic() - t0
    assert r.status_code == 200
    body = r.json()
    # structured response: 既定 keys が dict で揃う
    for key in ("memory_block", "decisions", "constitution",
                "mem0_facts", "conflicts", "has_conflicts"):
        assert key in body, f"missing key {key} in build response"
    assert dt < 2.0, f"POST /api/context/build took {dt:.2f}s (limit 2s)"


def test_ac2_get_constitution_endpoint_returns_constitution_field(
    client, isolated_constitution_dir,
) -> None:
    """AC-2.2: GET /api/context/constitution は {"constitution": ...} 構造体を返す."""
    (isolated_constitution_dir / "D-300.md").write_text(
        "# Policy 300\n\nbe concise", encoding="utf-8",
    )
    t0 = time.monotonic()
    r = client.get("/api/context/constitution")
    dt = time.monotonic() - t0
    assert r.status_code == 200
    body = r.json()
    assert isinstance(body, dict)
    assert "constitution" in body
    assert isinstance(body["constitution"], str)
    assert dt < 2.0


def test_ac2_preload_constitution_within_2s(
    isolated_constitution_dir, monkeypatch,
) -> None:
    """AC-2.3: preload_constitution は read-only / no network → 2 秒余裕."""
    monkeypatch.delenv("CONSTITUTION_TEXT", raising=False)
    for i in range(20):
        (isolated_constitution_dir / f"D-{400 + i:03d}.md").write_text(
            f"# P{i}\n\n" + ("x" * 1000), encoding="utf-8",
        )
    t0 = time.monotonic()
    text = asyncio.run(preload_constitution())
    dt = time.monotonic() - t0
    assert len(text) > 0
    assert dt < 2.0, f"preload took {dt:.2f}s (limit 2s)"


# ══════════════════════════════════════════════════════════════════════
# AC-3 STATE-DRIVEN — 後方互換 (regression guard)
# ══════════════════════════════════════════════════════════════════════


def test_ac3_build_context_signature_kwargs_unchanged() -> None:
    """AC-3.1: build_context シグネチャ後方互換.
    refactor 後も既存 kwargs が default 付きで残っている (caller を壊さない)."""
    sig = inspect.signature(build_context)
    params = sig.parameters
    # 必須 positional/keyword
    assert "user_message" in params
    assert "session_id" in params
    # default 付き kwarg (caller が呼出形を壊さない)
    assert params["prior_session_id"].default is None
    assert params["user_id"].default is None
    assert params["top_k"].default == 5
    assert params["include_constitution"].default is True
    assert params["secretary_active"].default is None


def test_ac3_build_context_return_keys_unchanged(
    isolated_constitution_dir,
) -> None:
    """AC-3.2: build_context 戻り値 dict keys 後方互換.

    T-M28-01 で確定した keys (memory_block / decisions / constitution /
    mem0_facts / conflicts / has_conflicts / secretary_active) が
    全て揃っていることを 1:1 で固定.
    """
    result = asyncio.run(build_context(
        user_message="contract check",
        session_id=1, user_id="masato",
        include_constitution=False,
    ))
    required_keys = {
        "memory_block", "decisions", "constitution",
        "mem0_facts", "conflicts", "has_conflicts", "secretary_active",
    }
    assert required_keys.issubset(result.keys()), (
        f"missing keys: {required_keys - set(result.keys())}"
    )


def test_ac3_include_constitution_false_suppresses(
    isolated_constitution_dir, monkeypatch,
) -> None:
    """AC-3.3: include_constitution=False で constitution は空文字 (M-28 contract).

    F-026 spec は "全 session に inject" だが、M-28 boundary では caller が
    suppress を選べる (refactor で壊さない後方互換契約).
    """
    monkeypatch.setenv("CONSTITUTION_TEXT", "should be suppressed")
    result = asyncio.run(build_context(
        user_message="hi", session_id=1, user_id="masato",
        include_constitution=False,
    ))
    assert result["constitution"] == ""


def test_ac3_secretary_inactive_suppresses_constitution(
    isolated_constitution_dir, monkeypatch,
) -> None:
    """AC-3.4: secretary_active=False で constitution は空 (T-M28-01 G2 整合).

    M-28 ↔ F-026 boundary: 秘書 AI inactive のときは constitution を inject しない.
    """
    monkeypatch.setenv("CONSTITUTION_TEXT", "should be suppressed by inactive")
    result = asyncio.run(build_context(
        user_message="hi", session_id=1, user_id="masato",
        include_constitution=True,
        secretary_active=False,
    ))
    assert result["constitution"] == ""
    assert result["secretary_active"] is False


def test_ac3_existing_endpoints_contract_preserved(client) -> None:
    """AC-3.5: 既存 endpoint contract が現行のまま動く.

    refactor で route が消える / 引数が変わると caller (frontend / agents) を
    壊す → 1:1 で固定.
    """
    # /api/context/build (POST)
    r = client.post("/api/context/build", json={
        "user_message": "x", "session_id": 1, "include_constitution": False,
    })
    assert r.status_code == 200

    # /api/context/constitution (GET)
    r = client.get("/api/context/constitution")
    assert r.status_code == 200

    # /api/context/decisions/{id} (GET) — 404 を確認
    r = client.get("/api/context/decisions/D-99999")
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════
# AC-4 UNWANTED — 4xx {detail:{code,message}} + state 不変
# ══════════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("bad_message", ["", "   ", None])
def test_ac4_empty_user_message_returns_400_dict_detail(client, bad_message) -> None:
    """AC-4.1: 空 user_message は 400 で {detail:{code,message}}."""
    r = client.post(
        "/api/context/build",
        json={"user_message": bad_message, "session_id": 1},
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert "code" in detail
    assert "message" in detail
    assert detail["code"] == "context.invalid"


@pytest.mark.parametrize("bad_session_id", [0, -1, True, False, "1", None])
def test_ac4_invalid_session_id_returns_400_dict_detail(client, bad_session_id) -> None:
    """AC-4.2: invalid session_id (<=0 / bool / non-int / null) は 400 で
    {detail:{code,message}}."""
    r = client.post(
        "/api/context/build",
        json={"user_message": "hi", "session_id": bad_session_id},
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail["code"] == "context.invalid"


def test_ac4_invalid_include_constitution_returns_400(client) -> None:
    """AC-4.3: include_constitution が bool 以外なら 400."""
    r = client.post(
        "/api/context/build",
        json={
            "user_message": "hi", "session_id": 1,
            "include_constitution": "yes",  # bool ではなく str
        },
    )
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail["code"] == "context.invalid"


def test_ac4_empty_user_id_constitution_returns_400(client) -> None:
    """AC-4.4: /api/context/constitution の user_id が空文字 → 400 dict detail."""
    r = client.get("/api/context/constitution", params={"user_id": "   "})
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert "code" in detail
    assert "message" in detail
    assert detail["code"] == "context.invalid"


@pytest.mark.parametrize("bad_id", ["X-001", "D-12", "D-", "d-001"])
def test_ac4_invalid_decision_id_format_returns_400_dict_detail(client, bad_id) -> None:
    """AC-4.5: decision_id format 不正は 400 で {detail:{code,message}}."""
    r = client.get(f"/api/context/decisions/{bad_id}")
    assert r.status_code == 400
    detail = r.json().get("detail")
    assert isinstance(detail, dict)
    assert detail["code"] == "context.invalid"


def test_ac4_invalid_input_does_not_mutate_filesystem(
    isolated_constitution_dir, tmp_path, monkeypatch,
) -> None:
    """AC-4.6: 不正 input で persistent state (CONSTITUTION_DIR / OBSIDIAN_VAULT_DIR)
    の filesystem は mutate されない.

    build_context は validation で raise → write 経路には到達しない.
    """
    vault = tmp_path / "vault_should_not_be_touched"
    monkeypatch.setenv("OBSIDIAN_VAULT_DIR", str(vault))
    before_const = sorted(p.name for p in isolated_constitution_dir.glob("*"))

    # 不正 input
    with pytest.raises(cb.ContextBuilderError):
        asyncio.run(build_context(
            user_message="",   # invalid
            session_id=1, user_id="masato",
        ))
    with pytest.raises(cb.ContextBuilderError):
        asyncio.run(build_context(
            user_message="hi",
            session_id=0,      # invalid
            user_id="masato",
        ))

    after_const = sorted(p.name for p in isolated_constitution_dir.glob("*"))
    assert before_const == after_const
    # vault は最初から存在せず、build_context で作られていない
    assert not vault.exists()


# ══════════════════════════════════════════════════════════════════════
# Cross-module invariant — M-28 ↔ F-026 (constitution_engine) boundary
# ══════════════════════════════════════════════════════════════════════


def test_invariant_constitution_engine_is_canonical_inject_path() -> None:
    """ADR-012: Constitution の system prompt inject は services.constitution_engine
    inject_for_session() が canonical. M-28 (context_builder) は file-based
    preload_constitution path を持つが、 これは 「秘書 AI active 時の prompt 末尾追加」
    用途で、 DB-backed role/workspace-aware inject_for_session とは併存する.
    両者が import 可能であり、 lint check #12 で自前 inject が禁止されていることを
    確認 (boundary invariant).
    """
    # M-28 path
    from services.context_builder import preload_constitution as p28
    assert callable(p28)
    # F-026 path
    from services.constitution_engine import inject_for_session
    assert callable(inject_for_session)
    # lint check #12 が存在
    script_text = (REPO_ROOT / "scripts" / "lint-mock.sh").read_text(
        encoding="utf-8",
    )
    assert "check_no_self_constitution_inject" in script_text
    assert "[12/14]" in script_text
