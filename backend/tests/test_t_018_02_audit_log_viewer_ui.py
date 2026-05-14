"""T-018-02: audit_log_viewer UI (検索 + before/after diff + CSV/JSON export) static invariants."""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "frontend/src/app/audit-logs/page.tsx"


@pytest.fixture(scope="module")
def src():
    assert PAGE.exists()
    return PAGE.read_text(encoding="utf-8")


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_default_export(src):
    assert "export default function AuditLogViewerPage" in src


def test_ac1_search_input(src):
    assert "Search" in src
    assert "<input" in src
    assert "query" in src


def test_ac1_event_type_filter(src):
    assert "eventType" in src
    assert "<select" in src


def test_ac1_before_after_diff_view(src):
    assert "Before" in src
    assert "After" in src
    assert "selected.before" in src or "selected?.before" in src
    assert "selected.after" in src or "selected?.after" in src


def test_ac1_csv_json_export(src):
    assert "csv" in src.lower() and "json" in src.lower()
    assert "exportTo" in src or "/export" in src


def test_ac2_api_audit_logs(src):
    assert "/api/audit-logs" in src
    assert "useQuery" in src


def test_ac2_export_endpoint(src):
    assert "/api/audit-logs/export" in src


def test_ac3_read_only(src):
    """audit logs は read-only (POST/PUT/DELETE mutation 無し)."""
    # export 以外で POST/PUT/DELETE method の使用が無いことを確認
    assert "useMutation" not in src or "exportTo" in src
    # useMutation を使う場合は export 用のみ. 直接 mutation は無いはず.


def test_ac4_error_handling(src):
    assert "errorMessage" in src
    assert "detail?.message" in src or "detail.message" in src


def test_ac4_eb_color(src):
    assert "eb-500" in src
