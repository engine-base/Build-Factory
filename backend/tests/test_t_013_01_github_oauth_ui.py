"""T-013-01: GitHub OAuth + repo 紐付け UI static invariants."""
from pathlib import Path
import pytest

REPO = Path(__file__).resolve().parent.parent.parent
PAGE = REPO / "frontend/src/app/settings/integrations/github/page.tsx"


@pytest.fixture(scope="module")
def src():
    assert PAGE.exists()
    return PAGE.read_text(encoding="utf-8")


def test_ac1_page_exists():
    assert PAGE.exists()


def test_ac1_default_export(src):
    assert "export default function GithubIntegrationPage" in src


def test_ac1_uses_github_lucide_icon(src):
    assert "Github" in src
    assert 'from "lucide-react"' in src


def test_ac2_oauth_authorize_endpoint(src):
    assert "/api/oauth/github/authorize" in src
    assert "/api/oauth/github/status" in src


def test_ac2_repos_endpoint(src):
    assert "/api/integrations/github/repos" in src


def test_ac2_link_unlink_mutation(src):
    assert "linkMutation" in src
    # URL template literal で `${...}/${link ? 'link' : 'unlink'}` のように構築されるので
    # 'link' / 'unlink' 文字列を直接 check.
    assert "'link'" in src or "'unlink'" in src or '"link"' in src or '"unlink"' in src


def test_ac3_repo_link_uses_post(src):
    assert 'method: "POST"' in src


def test_ac4_error_handling(src):
    assert "errorMessage" in src
    assert "detail?.message" in src or "detail.message" in src


def test_ac4_eb_color(src):
    assert "eb-500" in src
