"""T-013-03: PR 自動作成 + HTML diff 注釈レビュー資料添付 — 4 AC 全網羅.

AC マッピング:
  AC-1 UBIQUITOUS    : F-013 HTML レビュー資料生成 service + endpoint
  AC-2 EVENT-DRIVEN  : 2 秒以内 + {detail:{code,message}}
  AC-3 STATE-DRIVEN  : audit emit + service は read-only (input 非破壊)
  AC-4 UNWANTED      : invalid input は 4xx + structured /
                       persistent state mutate しない
"""
from __future__ import annotations

import copy
import os
import time

import pytest
from fastapi.testclient import TestClient

from services import pr_review_annotator as pra
from services.pr_review_annotator import (
    DiffStats,
    FileDiff,
    Hunk,
    HunkLine,
    PRAnnotatorError,
    PRMeta,
    parse_unified_diff,
    render_review_html,
)


SAMPLE_DIFF = """\
diff --git a/foo.py b/foo.py
index 1111111..2222222 100644
--- a/foo.py
+++ b/foo.py
@@ -1,5 +1,6 @@
 def greet(name):
-    return f"Hello, {name}"
+    if not name:
+        raise ValueError("empty")
+    return f"Hello, {name}!"

 print(greet("alice"))
diff --git a/bar.py b/bar.py
new file mode 100644
index 0000000..3333333
--- /dev/null
+++ b/bar.py
@@ -0,0 +1,3 @@
+def add(a, b):
+    return a + b
+
"""


SAMPLE_DELETED = """\
diff --git a/old.py b/old.py
deleted file mode 100644
index 4444444..0000000
--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-print("old file")
-
"""


@pytest.fixture(scope="module")
def client():
    os.environ.setdefault("DISABLE_BACKGROUND_WORKERS", "1")
    from main import app
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture(autouse=True)
def _capture_audit(monkeypatch):
    captured: list[dict] = []

    async def fake_emit(event_type, *, session_id=None, user_id=None, detail=None):
        captured.append({
            "event_type": event_type, "user_id": user_id, "detail": detail or {},
        })
        return len(captured)

    import services.memory_service as ms
    monkeypatch.setattr(ms, "emit_event", fake_emit)
    yield captured


# ──────────────────────────────────────────────────────────────────────────
# Service 単体
# ──────────────────────────────────────────────────────────────────────────


def test_service_parse_basic_diff():
    files, stats = parse_unified_diff(SAMPLE_DIFF)
    assert stats.files == 2
    by_path = {f.path: f for f in files}
    assert "foo.py" in by_path
    assert "bar.py" in by_path
    assert by_path["bar.py"].is_new is True
    assert by_path["foo.py"].additions >= 3
    assert by_path["foo.py"].deletions >= 1


def test_service_parse_deleted_file():
    files, stats = parse_unified_diff(SAMPLE_DELETED)
    assert files[0].path == "old.py"
    assert files[0].is_deleted is True


def test_service_parse_empty_diff():
    files, stats = parse_unified_diff("")
    assert files == []
    assert stats.files == 0


def test_service_parse_truncates_huge_diff():
    huge = "diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -0,0 +1,1 @@\n+x\n"
    # MAX_DIFF_SIZE を超える文字列を作る
    diff = huge + ("+padding\n" * 1000_000)
    files, stats = parse_unified_diff(diff)
    assert stats.truncated is True


def test_service_parse_invalid_type():
    with pytest.raises(PRAnnotatorError):
        parse_unified_diff(12345)


def test_service_parse_does_not_mutate_input():
    original = SAMPLE_DIFF
    snap = copy.copy(original)
    parse_unified_diff(original)
    assert original == snap


def test_service_render_html_basic():
    files, stats = parse_unified_diff(SAMPLE_DIFF)
    meta = PRMeta(
        title="Test PR", body="body text", branch="claude/feat-1",
        author="alice",
    )
    out = render_review_html(meta, files, stats=stats)
    assert "<!doctype html>" in out.lower()
    assert "Test PR" in out
    assert "foo.py" in out
    assert "bar.py" in out
    assert "+3" in out or "+4" in out  # 加算行数 (foo:+3, bar:+3)


def test_service_render_escapes_xss():
    meta = PRMeta(title='<script>alert(1)</script>', branch="claude/x")
    out = render_review_html(meta, [])
    assert "<script>alert(1)</script>" not in out
    assert "&lt;script&gt;" in out


def test_service_render_escapes_diff_content():
    files = [
        FileDiff(
            path="x.py",
            hunks=[
                Hunk(
                    header="@@ -1,1 +1,1 @@", old_start=1, old_count=1,
                    new_start=1, new_count=1,
                    lines=[
                        HunkLine(kind="add", old_lineno=None,
                                  new_lineno=1, text="<img src=x>"),
                    ],
                ),
            ],
        ),
    ]
    out = render_review_html(PRMeta(title="x", branch="claude/x"), files)
    assert "<img src=x>" not in out
    assert "&lt;img" in out


def test_service_render_empty_title_raises():
    with pytest.raises(PRAnnotatorError):
        render_review_html(PRMeta(title="   ", branch="claude/x"), [])


def test_service_render_title_too_long():
    with pytest.raises(PRAnnotatorError):
        render_review_html(
            PRMeta(title="x" * (pra.MAX_TITLE_LEN + 1),
                   branch="claude/x"),
            [],
        )


def test_service_render_body_too_long():
    with pytest.raises(PRAnnotatorError):
        render_review_html(
            PRMeta(title="ok", body="x" * (pra.MAX_BODY_LEN + 1),
                   branch="claude/x"),
            [],
        )


def test_service_render_branch_too_long():
    with pytest.raises(PRAnnotatorError):
        render_review_html(
            PRMeta(title="ok", branch="x" * (pra.MAX_BRANCH_LEN + 1)),
            [],
        )


def test_service_render_includes_default_checklist():
    out = render_review_html(PRMeta(title="x", branch="claude/x"), [])
    assert "AC-1 UBIQUITOUS" in out
    assert "pre-commit-check" in out


def test_service_render_custom_checklist():
    out = render_review_html(
        PRMeta(title="x", branch="claude/x"),
        [],
        checklist=["custom item A", "custom item B"],
    )
    assert "custom item A" in out
    assert "custom item B" in out
    # default は含まれない
    assert "AC-1 UBIQUITOUS" not in out


def test_service_render_invalid_meta_type():
    with pytest.raises(PRAnnotatorError):
        render_review_html({"title": "x"}, [])


def test_service_to_dict_shapes():
    files, stats = parse_unified_diff(SAMPLE_DIFF)
    d = stats.to_dict()
    for k in ("files", "additions", "deletions", "truncated"):
        assert k in d
    f = files[0].to_dict()
    for k in ("path", "old_path", "is_new", "is_deleted",
               "additions", "deletions", "hunks"):
        assert k in f


# ──────────────────────────────────────────────────────────────────────────
# AC-1 UBIQUITOUS: endpoint
# ──────────────────────────────────────────────────────────────────────────


def test_ac1_parse_diff_endpoint(client):
    r = client.post(
        "/api/pr-review/parse-diff",
        json={"diff": SAMPLE_DIFF},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["stats"]["files"] == 2
    assert any(f["path"] == "foo.py" for f in body["files"])


def test_ac1_render_html_endpoint(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={
            "title": "Test PR",
            "body": "summary",
            "branch": "claude/feat-1",
            "base_branch": "main",
            "author": "alice",
            "diff": SAMPLE_DIFF,
        },
    )
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "Test PR" in r.text
    assert "foo.py" in r.text


def test_ac1_render_attaches_filename(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x", "diff": SAMPLE_DIFF},
    )
    cd = r.headers.get("content-disposition", "")
    assert 'filename="pr-review.html"' in cd


def test_ac1_render_custom_checklist(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={
            "title": "X", "branch": "claude/x", "diff": SAMPLE_DIFF,
            "checklist": ["AC-1 機械検証", "cov >= 70%"],
        },
    )
    assert r.status_code == 200
    assert "AC-1 機械検証" in r.text


# ──────────────────────────────────────────────────────────────────────────
# AC-2 EVENT-DRIVEN: 2 秒以内 + structured error
# ──────────────────────────────────────────────────────────────────────────


def test_ac2_render_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x", "diff": SAMPLE_DIFF},
    )
    elapsed = time.perf_counter() - t0
    assert r.status_code == 200
    assert elapsed < 2.0


def test_ac2_parse_within_2s(client):
    t0 = time.perf_counter()
    r = client.post(
        "/api/pr-review/parse-diff",
        json={"diff": SAMPLE_DIFF},
    )
    assert r.status_code == 200
    assert time.perf_counter() - t0 < 2.0


def test_ac2_error_uses_detail_code_message(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "  ", "branch": "claude/x", "diff": SAMPLE_DIFF},
    )
    assert r.status_code == 400
    body = r.json()
    assert isinstance(body["detail"], dict)
    assert body["detail"]["code"] == "pr_review.invalid_title"


# ──────────────────────────────────────────────────────────────────────────
# AC-3 STATE-DRIVEN: audit emit + service read-only
# ──────────────────────────────────────────────────────────────────────────


def test_ac3_render_emits_audit(client, _capture_audit):
    client.post(
        "/api/pr-review/render-html",
        json={
            "title": "Audit Test",
            "branch": "claude/audit",
            "diff": SAMPLE_DIFF,
            "actor_user_id": "alice",
        },
    )
    events = [e for e in _capture_audit if e["event_type"] == "pr_review.rendered"]
    assert len(events) >= 1
    assert events[0]["user_id"] == "alice"
    assert events[0]["detail"]["files"] == 2


def test_ac3_parse_does_not_emit_audit(client, _capture_audit):
    """parse-diff は read-only (audit emit なし)."""
    client.post(
        "/api/pr-review/parse-diff",
        json={"diff": SAMPLE_DIFF, "actor_user_id": "alice"},
    )
    events = [e for e in _capture_audit if e["event_type"] == "pr_review.rendered"]
    assert len(events) == 0


def test_ac3_service_input_unchanged(client):
    payload = {
        "title": "X",
        "branch": "claude/x",
        "diff": SAMPLE_DIFF,
        "actor_user_id": "alice",
    }
    snap = copy.deepcopy(payload)
    client.post("/api/pr-review/render-html", json=payload)
    assert payload == snap


# ──────────────────────────────────────────────────────────────────────────
# AC-4 UNWANTED: 4xx + structured + no mutation
# ──────────────────────────────────────────────────────────────────────────


def test_ac4_empty_title(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": " ", "branch": "claude/x", "diff": SAMPLE_DIFF},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "pr_review.invalid_title"


def test_ac4_long_title(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "x" * (pra.MAX_TITLE_LEN + 1),
               "branch": "claude/x", "diff": SAMPLE_DIFF},
    )
    assert r.status_code == 400


def test_ac4_long_body(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "body": "x" * (pra.MAX_BODY_LEN + 1),
               "branch": "claude/x", "diff": SAMPLE_DIFF},
    )
    assert r.status_code == 400


def test_ac4_long_branch(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X",
               "branch": "x" * (pra.MAX_BRANCH_LEN + 1),
               "diff": SAMPLE_DIFF},
    )
    assert r.status_code == 400


def test_ac4_empty_diff(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x", "diff": " "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "pr_review.invalid_diff"


def test_ac4_empty_actor(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF, "actor_user_id": " "},
    )
    assert r.status_code == 401


def test_ac4_invalid_author(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF, "author": " "},
    )
    assert r.status_code == 400
    assert r.json()["detail"]["code"] == "pr_review.invalid_author"


def test_ac4_long_author(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF, "author": "x" * 201},
    )
    assert r.status_code == 400


def test_ac4_invalid_checklist_type(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF, "checklist": "not-a-list"},
    )
    assert r.status_code in (400, 422)


def test_ac4_too_many_checklist_items(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF,
               "checklist": [f"item{i}" for i in range(51)]},
    )
    assert r.status_code == 400


def test_ac4_long_checklist_item(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF,
               "checklist": ["x" * 501]},
    )
    assert r.status_code == 400


def test_ac4_empty_checklist_item(client):
    r = client.post(
        "/api/pr-review/render-html",
        json={"title": "X", "branch": "claude/x",
               "diff": SAMPLE_DIFF, "checklist": ["valid", "  "]},
    )
    assert r.status_code == 400


def test_ac4_parse_empty_diff(client):
    r = client.post("/api/pr-review/parse-diff", json={"diff": " "})
    assert r.status_code == 400


def test_ac4_rejected_does_not_emit_audit(client, _capture_audit):
    client.post("/api/pr-review/render-html",
                 json={"title": " ", "branch": "claude/x", "diff": SAMPLE_DIFF})
    client.post("/api/pr-review/render-html",
                 json={"title": "x", "branch": "claude/x", "diff": " "})
    events = [e for e in _capture_audit if e["event_type"] == "pr_review.rendered"]
    assert len(events) == 0


# ──────────────────────────────────────────────────────────────────────────
# error contract shape consistency
# ──────────────────────────────────────────────────────────────────────────


def test_error_contract_shape_consistent(client):
    cases = [
        ("POST", "/api/pr-review/render-html",
         {"title": " ", "branch": "claude/x", "diff": SAMPLE_DIFF}),
        ("POST", "/api/pr-review/render-html",
         {"title": "X", "branch": "claude/x", "diff": " "}),
        ("POST", "/api/pr-review/render-html",
         {"title": "X", "branch": "claude/x",
          "diff": SAMPLE_DIFF, "actor_user_id": " "}),
        ("POST", "/api/pr-review/parse-diff", {"diff": " "}),
        ("POST", "/api/pr-review/render-html",
         {"title": "X", "branch": "claude/x",
          "diff": SAMPLE_DIFF,
          "checklist": [f"i{i}" for i in range(51)]}),
    ]
    for method, path, payload in cases:
        r = client.post(path, json=payload)
        assert 400 <= r.status_code < 500, f"{path}: {r.status_code}"
        body = r.json()
        if isinstance(body.get("detail"), dict):
            assert isinstance(body["detail"]["code"], str)
            assert isinstance(body["detail"]["message"], str)
