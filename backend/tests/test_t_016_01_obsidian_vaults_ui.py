"""T-016-01: obsidian_vaults 設定 UI (REFACTOR existing obsidian_sync) static invariants."""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "frontend/src/app/settings/obsidian/page.tsx"
EXISTING_SERVICE = REPO / "backend/services/obsidian_sync.py"


@pytest.fixture(scope="module")
def src():
    assert PAGE.exists()
    return PAGE.read_text(encoding="utf-8")


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_default_export(src):
    assert "export default function ObsidianVaultsPage" in src


def test_ac1_uses_folder_icon(src):
    assert "FolderOpen" in src
    assert 'from "lucide-react"' in src


def test_ac2_vaults_crud_endpoints(src):
    assert "/api/obsidian/vaults" in src
    assert "useQuery" in src
    assert "addMutation" in src
    assert "deleteMutation" in src


def test_ac2_sync_action(src):
    assert "syncMutation" in src
    assert "/sync" in src


def test_ac3_backwards_compat_existing_service():
    """REFACTOR invariant: 既存 obsidian_sync.py が repo に残る."""
    assert EXISTING_SERVICE.exists(), "obsidian_sync.py must remain (REUSE invariant)"


def test_ac4_error_handling(src):
    assert "errorMessage" in src
    assert "detail?.message" in src or "detail.message" in src


def test_ac4_eb_color(src):
    assert "eb-500" in src
