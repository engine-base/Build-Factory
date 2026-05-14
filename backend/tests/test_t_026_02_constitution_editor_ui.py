"""T-026-02: Constitution editor UI (content_md + version diff) static invariants."""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "frontend/src/app/workspaces/[id]/constitution/page.tsx"


@pytest.fixture(scope="module")
def src():
    assert PAGE.exists()
    return PAGE.read_text(encoding="utf-8")


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_default_export(src):
    assert "export default function ConstitutionEditorPage" in src


def test_ac1_uses_lucide(src):
    assert 'from "lucide-react"' in src


def test_ac1_content_md_editor_textarea(src):
    assert "<textarea" in src
    assert "content_md" in src


def test_ac1_version_diff_view(src):
    assert "GitCompare" in src
    assert "showDiff" in src
    assert "revisions" in src


def test_ac2_api_constitutions_fetch(src):
    assert "/api/constitutions" in src
    assert "useQuery" in src


def test_ac2_save_mutation(src):
    assert "saveMutation" in src
    assert "useMutation" in src
    assert 'method: "POST"' in src


def test_ac3_workspace_id_param(src):
    assert "workspaceId" in src or "workspace_id" in src
    assert "useParams" in src


def test_ac4_error_handling(src):
    assert "errorMessage" in src
    assert "detail?.message" in src or "detail.message" in src


def test_ac4_eb_color_used(src):
    assert "eb-500" in src or "var(--eb-" in src
