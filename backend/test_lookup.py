# backend/test_lookup.py
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch, MagicMock
from main import app
from models import CandidateProfile, RepoInfo

MOCK_PROFILE = CandidateProfile(
    username="gaearon",
    avatar_url="https://avatars.githubusercontent.com/u/810438",
    html_url="https://github.com/gaearon",
    bio="Working on React",
    location="London, UK",
    company="Meta",
    blog="https://overreacted.io",
    public_repos=50,
    followers=80000,
    languages={"JavaScript": 5000, "TypeScript": 3000},
    top_repos=[RepoInfo(name="react", description="The library", stars=200000, topics=["react"])],
    last_active="2024-01-01"
)

client = TestClient(app)

def test_lookup_known_username_no_jd():
    with patch("main.GitHubScraper") as MockScraper:
        instance = MockScraper.return_value
        instance._make_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        instance._make_client.return_value.__aexit__ = AsyncMock(return_value=False)
        instance.fetch_candidate_profile = AsyncMock(return_value=MOCK_PROFILE)
        resp = client.post("/api/lookup", json={"query": "gaearon", "jd_text": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "found"
    assert data["profile"]["username"] == "gaearon"
    assert data["score_result"] is None

def test_lookup_known_username_with_jd():
    jd = "React frontend engineer, 3 years experience, TypeScript required"
    mock_parsed = MagicMock()
    mock_parsed.required_skills = ["React"]
    mock_parsed.languages = ["JavaScript"]   # primary language matches
    mock_parsed.bonus_skills = []
    mock_parsed.min_years = 3
    mock_scored = MagicMock()
    mock_scored.score = 85
    mock_scored.reason = "Strong React evidence"
    mock_scored.strengths = ["React"]
    mock_scored.gaps = []
    mock_scored.languages = {"JavaScript": 5000, "TypeScript": 3000}
    mock_scored.followers = 100             # small follower count, no penalty
    mock_scored.last_active = "2025-12-01"  # recently active

    with patch("main.GitHubScraper") as MockScraper, \
         patch("main.parse_jd", return_value=mock_parsed), \
         patch("main.score_candidate", return_value=mock_scored):
        instance = MockScraper.return_value
        instance._make_client.return_value.__aenter__ = AsyncMock(return_value=MagicMock())
        instance._make_client.return_value.__aexit__ = AsyncMock(return_value=False)
        instance.fetch_candidate_profile = AsyncMock(return_value=MOCK_PROFILE)
        resp = client.post("/api/lookup", json={"query": "gaearon", "jd_text": jd})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "found"
    assert data["score_result"] is not None
    assert data["score_result"]["score"] >= 0

def test_lookup_not_found():
    import httpx
    mock_response = MagicMock()
    mock_response.status_code = 404

    with patch("main.GitHubScraper") as MockScraper:
        instance = MockScraper.return_value
        mock_gh_client = AsyncMock()
        mock_gh_client.get = AsyncMock(return_value=MagicMock(
            status_code=200,
            json=MagicMock(return_value={"items": []})
        ))
        mock_gh_client.get.return_value.raise_for_status = MagicMock()
        instance._make_client.return_value.__aenter__ = AsyncMock(return_value=mock_gh_client)
        instance._make_client.return_value.__aexit__ = AsyncMock(return_value=False)
        instance.fetch_candidate_profile = AsyncMock(
            side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
        )
        resp = client.post("/api/lookup", json={"query": "this-user-xyz999", "jd_text": ""})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "not_found"
