"""T-012-04: red_line_approval キュー UI (REFACTOR existing approval page) static invariants.

既存 frontend/src/app/approval/page.tsx を REFACTOR で red-line filter + severity 表示を追加.
"""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "frontend/src/app/approval/page.tsx"


@pytest.fixture(scope="module")
def src():
    assert PAGE.exists()
    return PAGE.read_text(encoding="utf-8")


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_existing_approval_page_kept(src):
    """既存の ApprovalPage default export を保持 (REUSE invariant)."""
    assert "export default function ApprovalPage" in src


def test_ac1_red_line_metadata_type(src):
    """red_line_category type が追加されている."""
    assert "red_line_category" in src
    assert "api_key_leak" in src
    assert "db_destructive" in src


def test_ac1_severity_type(src):
    """severity type が追加されている (block / warn / log)."""
    assert "severity" in src
    assert '"block"' in src and '"warn"' in src and '"log"' in src


def test_ac1_red_line_filter_toggle(src):
    """red-line 専用フィルタ toggle がある."""
    assert "RedLineFilter" in src
    assert "red_line_only" in src


def test_ac2_filter_applied(src):
    """filter state で items を絞り込む."""
    assert "filteredItems" in src
    assert "filter === \"red_line_only\"" in src or "filter === 'red_line_only'" in src


def test_ac2_severity_badge(src):
    """severity badge を表示."""
    assert "severityClass" in src
    assert "ShieldAlert" in src


def test_ac3_backwards_compat_endpoint(src):
    """既存 endpoint /api/approval を変更していない (REFACTOR invariant)."""
    assert "/api/approval" in src
    assert "useQuery" in src
    # 既存 act mutation も保持
    assert "useMutation" in src


def test_ac4_error_message_state(src):
    """errorMessage state が追加されている."""
    assert "errorMessage" in src
    assert "setErrorMessage" in src


def test_ac1_uses_lucide(src):
    assert 'from "lucide-react"' in src
    assert "ShieldAlert" in src
    assert "Filter" in src
