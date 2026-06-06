# backend/test_lookup.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from main import app
from models import CandidateProfile, RepoInfo

MOCK_GH_PROFILE = CandidateProfile(
    username="gaearon",
    avatar_url="https://avatars.githubusercontent.com/u/810438",
    html_url="https://github.com/gaearon",
    bio="Working on React",
    location="London, UK",
    company="Meta",
    blog="https://overreacted.io",
    public_repos=50,
    followers=500,
    languages={"JavaScript": 5000, "TypeScript": 3000},
    top_repos=[RepoInfo(name="react", description="The library", stars=200000, topics=["react"])],
    last_active="2024-01-01"
)

MOCK_GT_PROFILE = {
    "username": "gaearon-gitee",
    "avatar_url": "https://gitee.com/avatars/gaearon",
    "html_url": "https://gitee.com/gaearon",
    "bio": "React developer",
    "location": "", "company": "", "blog": "",
    "public_repos": 5, "followers": 100,
    "languages": {"JavaScript": 2},
    "top_repos": [],
    "last_active": "2024-01-01",
    "display_name": "Dan"
}

client = TestClient(app)


def _make_gh_mock(profile=MOCK_GH_PROFILE):
    mock = MagicMock()
    mock_ctx = AsyncMock()
    mock.return_value._make_client.return_value.__aenter__ = AsyncMock(return_value=mock_ctx)
    mock.return_value._make_client.return_value.__aexit__ = AsyncMock(return_value=False)
    mock.return_value.fetch_candidate_profile = AsyncMock(return_value=profile)
    return mock


def _make_gt_mock(profile=None, search_results=None):
    mock = MagicMock()
    mock.return_value._make_client.return_value.__aenter__ = AsyncMock(return_value=AsyncMock())
    mock.return_value._make_client.return_value.__aexit__ = AsyncMock(return_value=False)
    mock.return_value.fetch_profile = AsyncMock(return_value=profile)
    mock.return_value.search_users = AsyncMock(return_value=search_results or [])
    return mock


def test_lookup_github_only_no_jd():
    with patch("main.GitHubScraper", _make_gh_mock()), \
         patch("main.GiteeScraper", _make_gt_mock()):
        resp = client.post("/api/lookup", json={"query": "gaearon", "jd_text": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "found"
    assert data["github"]["username"] == "gaearon"
    assert data["gitee"] is None
    assert data["score_result"] is None


def test_lookup_both_sources_found():
    with patch("main.GitHubScraper", _make_gh_mock()), \
         patch("main.GiteeScraper", _make_gt_mock(profile=MOCK_GT_PROFILE)):
        resp = client.post("/api/lookup", json={"query": "gaearon", "jd_text": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "found"
    assert data["github"] is not None
    assert data["gitee"] is not None


def test_lookup_not_found_both():
    import httpx
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("main.GitHubScraper") as MockGH, \
         patch("main.GiteeScraper", _make_gt_mock()):
        mock_gh_ctx = AsyncMock()
        mock_gh_ctx.get = AsyncMock(return_value=MagicMock(
            json=MagicMock(return_value={"items": []}),
            raise_for_status=MagicMock()
        ))
        MockGH.return_value._make_client.return_value.__aenter__ = AsyncMock(return_value=mock_gh_ctx)
        MockGH.return_value._make_client.return_value.__aexit__ = AsyncMock(return_value=False)
        MockGH.return_value.fetch_candidate_profile = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        )
        resp = client.post("/api/lookup", json={"query": "nobody-xyz999", "jd_text": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_found"


def test_lookup_with_jd_scores_github():
    jd = "React frontend engineer, TypeScript required"
    mock_parsed = MagicMock(required_skills=["React"], languages=["JavaScript"],
                             bonus_skills=[], min_years=3)
    mock_scored = MagicMock(score=85, reason="Strong React evidence",
                             strengths=["React"], gaps=[],
                             languages={"JavaScript": 5000}, followers=500,
                             last_active="2025-12-01")

    with patch("main.GitHubScraper", _make_gh_mock()), \
         patch("main.GiteeScraper", _make_gt_mock()), \
         patch("main.parse_jd", return_value=mock_parsed), \
         patch("main.score_candidate", return_value=mock_scored):
        resp = client.post("/api/lookup", json={"query": "gaearon", "jd_text": jd})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "found"
    assert data["score_result"] is not None
    assert data["score_result"]["score"] >= 0
