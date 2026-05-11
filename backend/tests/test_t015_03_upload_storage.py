"""T-015-03: Storage upload + 共有リンク + Markdown 併記 AC 検証.

AC マッピング:
  AC-1 UBIQUITOUS: upload で url + share_url + markdown を返す
  AC-2 EVENT:     2 秒以内の応答 + 構造化 response or {detail: {code, message}}
  AC-3 STATE:     backwards compat (既存 url / bucket / path / size / storage 維持)
  AC-4 UNWANTED:  invalid input (size / mime / kind) → 400 + {detail: {code, message}}
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
import time
import types
from typing import Any

import pytest
from fastapi.testclient import TestClient

from services import upload_service as svc
from services.upload_service import (
    ALLOWED_MIME, MAX_BYTES,
    build_markdown_snippet, upload_image, _build_object_path,
)


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _isolated_local_upload_dir(tmp_path, monkeypatch):
    """LOCAL_FALLBACK_DIR を tmp に隔離 + Supabase 未設定で local fallback 経路を選択."""
    monkeypatch.setattr(svc, "LOCAL_FALLBACK_DIR", tmp_path)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_KEY", raising=False)
    monkeypatch.setattr(svc, "SUPABASE_URL", "")
    monkeypatch.setattr(svc, "SUPABASE_SERVICE_KEY", "")


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: url + share_url + markdown
# ──────────────────────────────────────────────────────────────────────────


def test_upload_returns_url_share_url_and_markdown() -> None:
    """AC-1: response に url / share_url / markdown を含む."""
    result = asyncio.run(upload_image(
        account_id=1, kind="logo", filename="brand.png",
        content=b"\x89PNG\r\n\x1a\n_test_bytes",
        content_type="image/png",
    ))
    assert "url" in result
    assert "share_url" in result
    assert "markdown" in result
    # markdown は `![alt](url)` 形式
    assert result["markdown"].startswith("![")
    assert "](" in result["markdown"]
    assert result["markdown"].endswith(")")


def test_markdown_snippet_format() -> None:
    md = build_markdown_snippet("https://example.com/foo.png", alt="hero")
    assert md == "![hero](https://example.com/foo.png)"


def test_markdown_snippet_escapes_brackets_in_alt() -> None:
    md = build_markdown_snippet("https://x/y.png", alt="img[v2]")
    # alt 内の [] は () にエスケープ (Markdown link 構文との衝突回避)
    assert "[" not in md.split("](")[0][2:]  # 先頭 '![' 以降
    assert "img(v2)" in md


def test_markdown_snippet_url_encodes_spaces() -> None:
    md = build_markdown_snippet("https://x/a b.png", alt="t")
    assert "a%20b.png" in md


def test_markdown_snippet_default_alt() -> None:
    md = build_markdown_snippet("https://x/y.png")
    assert md == "![image](https://x/y.png)"


# ──────────────────────────────────────────────────────────────────────────
# AC-1: 共有リンク (share_url)
# ──────────────────────────────────────────────────────────────────────────


def test_share_url_has_expires_at_for_local_fallback() -> None:
    """local fallback では share_url に expires_at が hint として付く."""
    result = asyncio.run(upload_image(
        account_id=1, kind="icon", filename="i.png",
        content=b"\x00" * 100, content_type="image/png",
    ))
    assert "expires_at=" in result["share_url"]


def test_share_url_default_ttl_7_days() -> None:
    """default share_ttl_seconds = 7 days = 604800."""
    result = asyncio.run(upload_image(
        account_id=1, kind="icon", filename="i.png",
        content=b"\x00" * 100, content_type="image/png",
    ))
    assert result["share_ttl_seconds"] == 7 * 24 * 3600


def test_share_url_custom_ttl() -> None:
    """ttl=3600 (1 時間) で share_url 生成."""
    result = asyncio.run(upload_image(
        account_id=1, kind="icon", filename="i.png",
        content=b"\x00" * 100, content_type="image/png",
        share_ttl_seconds=3600,
    ))
    assert result["share_ttl_seconds"] == 3600


# ──────────────────────────────────────────────────────────────────────────
# AC-1: Supabase Storage (signed URL) 経路 — httpx mock
# ──────────────────────────────────────────────────────────────────────────


def test_supabase_signed_url_when_configured(monkeypatch) -> None:
    """SUPABASE_URL + KEY 設定時は Supabase signed URL を取得."""
    monkeypatch.setattr(svc, "SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setattr(svc, "SUPABASE_SERVICE_KEY", "sb-secret-test")

    call_log: list[dict[str, Any]] = []

    class _Resp:
        status_code = 200

        def __init__(self, json_body=None):
            self._json = json_body or {}

        def raise_for_status(self):
            return None

        def json(self):
            return self._json

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

        async def post(self, url, headers=None, content=None, json=None):
            call_log.append({"url": url, "json": json, "headers": headers})
            if "object/sign/" in url:
                return _Resp({"signedURL": "/object/sign/bf-uploads/path?token=xyz"})
            return _Resp({})

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    result = asyncio.run(upload_image(
        account_id=2, kind="logo", filename="x.png",
        content=b"\x00" * 50, content_type="image/png",
    ))
    # signed URL が返る
    assert "token=xyz" in result["share_url"]
    # public URL は upload した bucket path
    assert "/storage/v1/object/public/" in result["url"]


def test_supabase_signed_url_fallback_to_public_on_sign_failure(monkeypatch) -> None:
    """signed URL 取得失敗 → public URL fallback (silent)."""
    monkeypatch.setattr(svc, "SUPABASE_URL", "https://demo.supabase.co")
    monkeypatch.setattr(svc, "SUPABASE_SERVICE_KEY", "sb-secret-test")

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None

        async def post(self, url, headers=None, content=None, json=None):
            if "object/sign/" in url:
                raise RuntimeError("signing service down")

            class _Ok:
                status_code = 200
                def raise_for_status(self): pass
                def json(self): return {}
            return _Ok()

    import httpx
    monkeypatch.setattr(httpx, "AsyncClient", _Client)

    result = asyncio.run(upload_image(
        account_id=3, kind="icon", filename="i.png",
        content=b"\x00" * 50, content_type="image/png",
    ))
    # signed url fail でも response は壊れない、 share_url = public URL fallback
    assert result["share_url"] == result["url"]


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE: backwards compat (既存 field 維持)
# ──────────────────────────────────────────────────────────────────────────


def test_legacy_fields_preserved() -> None:
    """既存 contract: url / bucket / path / size / storage."""
    result = asyncio.run(upload_image(
        account_id=1, kind="logo", filename="legacy.png",
        content=b"\xff" * 200, content_type="image/png",
    ))
    for key in ("url", "bucket", "path", "size", "storage"):
        assert key in result
    assert result["size"] == 200
    assert result["storage"] == "local"


def test_object_path_format() -> None:
    """account_id/kind/timestamp_hash.ext の path 構造."""
    path = _build_object_path(account_id=42, kind="logo", filename="brand.png")
    parts = path.split("/")
    assert parts[0] == "42"
    assert parts[1] == "logo"
    assert parts[2].endswith(".png")
    assert "_" in parts[2]


def test_object_path_strips_path_traversal() -> None:
    """filename の .. / / は escape される (security)."""
    path = _build_object_path(account_id=1, kind="logo", filename="../../etc/passwd")
    assert ".." not in path
    assert "etc_passwd" in path or "etc/passwd" not in path


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: invalid input → 400 + {detail: {code, message}}
# ──────────────────────────────────────────────────────────────────────────


def test_upload_too_large_raises_value_error() -> None:
    """MAX_BYTES (15MB) 超過 → ValueError (router で 400)."""
    huge = b"\x00" * (MAX_BYTES + 1)
    with pytest.raises(ValueError, match="too large"):
        asyncio.run(upload_image(
            account_id=1, kind="logo", filename="big.png",
            content=huge, content_type="image/png",
        ))


def test_upload_unsupported_mime_raises() -> None:
    """text/plain 等 → ValueError."""
    with pytest.raises(ValueError, match="unsupported content type"):
        asyncio.run(upload_image(
            account_id=1, kind="logo", filename="x.txt",
            content=b"text",
            content_type="text/plain",
        ))


def test_router_unknown_kind_returns_400_with_code(client) -> None:
    """AC-4: invalid kind → 400 / code=unknown_kind."""
    r = client.post(
        "/api/uploads",
        data={"account_id": "1", "kind": "BOGUS_KIND"},
        files={"file": ("x.png", b"\x89PNG", "image/png")},
    )
    assert r.status_code == 400
    body = r.json()
    detail = body.get("detail")
    assert isinstance(detail, dict)
    assert detail.get("code") == "unknown_kind"
    assert "message" in detail


def test_router_too_large_returns_400_with_code(client) -> None:
    """ファイルサイズ超過 → 400 / code=file_too_large."""
    huge = b"\x00" * (MAX_BYTES + 10)
    r = client.post(
        "/api/uploads",
        data={"account_id": "1", "kind": "logo"},
        files={"file": ("big.png", huge, "image/png")},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "file_too_large"


def test_router_unsupported_mime_returns_400_with_code(client) -> None:
    r = client.post(
        "/api/uploads",
        data={"account_id": "1", "kind": "logo"},
        files={"file": ("x.txt", b"plain text", "text/plain")},
    )
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail["code"] == "unsupported_content_type"


def test_router_happy_path_returns_full_response(client) -> None:
    """正常 upload → 200 + 全 field."""
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    r = client.post(
        "/api/uploads",
        data={"account_id": "1", "kind": "logo"},
        files={"file": ("brand.png", png_bytes, "image/png")},
    )
    assert r.status_code == 200
    body = r.json()
    for key in ("url", "share_url", "markdown", "bucket", "path", "size", "storage",
                "share_ttl_seconds"):
        assert key in body, f"missing key: {key}"


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT: 2s 以内の応答 (local fallback で latency 計測)
# ──────────────────────────────────────────────────────────────────────────


def test_upload_completes_within_2_seconds() -> None:
    """AC-2: local fallback で upload + share_url + markdown 生成が 2s 以内."""
    content = b"\x00" * (1024 * 100)  # 100KB
    t0 = time.monotonic()
    asyncio.run(upload_image(
        account_id=1, kind="logo", filename="speed.png",
        content=content, content_type="image/png",
    ))
    dt = time.monotonic() - t0
    assert dt < 2.0, f"upload took {dt*1000:.1f}ms (limit 2s)"


# ──────────────────────────────────────────────────────────────────────────
# ALLOWED_MIME boundary
# ──────────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("mime", sorted(ALLOWED_MIME))
def test_each_allowed_mime_accepted(mime: str) -> None:
    result = asyncio.run(upload_image(
        account_id=1, kind="other", filename="x.bin",
        content=b"\x00" * 10, content_type=mime,
    ))
    assert "url" in result


def test_ensure_bucket_no_op_when_not_configured(monkeypatch) -> None:
    """SUPABASE 未設定で ensure_bucket は no-op (例外を投げない)."""
    monkeypatch.setattr(svc, "SUPABASE_URL", "")
    monkeypatch.setattr(svc, "SUPABASE_SERVICE_KEY", "")
    asyncio.run(svc.ensure_bucket())  # no exception