"""T-008-02 + T-008-04: phase_management UI + phase delete dialog static invariants.

frontend/src/app/workspaces/[id]/phases/page.tsx を Python から構造検証.

AC マッピング (1:1):
  AC-1 UBIQUITOUS    : page.tsx 存在 + PhaseManagementPage default export
  AC-2 EVENT-DRIVEN  : useQuery で /api/phases fetch + invalidate
  AC-3 STATE-DRIVEN  : RLS は backend, UI 側は workspace_id query param
  AC-4 UNWANTED      : 4xx → body.detail.message を errorMessage に格納
"""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "frontend/src/app/workspaces/[id]/phases/page.tsx"


@pytest.fixture(scope="module")
def src():
    assert PAGE.exists(), f"page missing: {PAGE}"
    return PAGE.read_text(encoding="utf-8")


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_default_export(src):
    assert "export default function PhaseManagementPage" in src


def test_ac1_uses_lucide_only(src):
    assert 'from "lucide-react"' in src or "from 'lucide-react'" in src


def test_ac1_phase_delete_dialog_present(src):
    """T-008-04 delete dialog がある."""
    assert "Delete Phase?" in src
    assert "deleteTarget" in src
    assert 'role="dialog"' in src


def test_ac2_api_phases_fetch(src):
    assert "/api/phases" in src
    assert "useQuery" in src


def test_ac2_invalidate_on_delete(src):
    assert "invalidateQueries" in src
    assert "deleteMutation" in src or "useMutation" in src


def test_ac3_workspace_id_param(src):
    assert "workspace_id" in src or "workspaceId" in src
    assert "useParams" in src


def test_ac4_error_message_displayed(src):
    assert "errorMessage" in src
    assert "detail?.message" in src or 'detail.message' in src


def test_ac4_4xx_handled(src):
    """!r.ok 経由で 4xx body から message を取る."""
    assert "!r.ok" in src
    assert "body?.detail" in src or "body.detail" in src
