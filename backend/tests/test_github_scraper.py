# backend/tests/test_github_scraper.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import AsyncMock, MagicMock
from github_scraper import GitHubScraper
from models import CandidateProfile

MOCK_SEARCH_RESPONSE = {
    "items": [
        {"login": "johndoe", "avatar_url": "https://avatars.github.com/1", "html_url": "https://github.com/johndoe"}
    ]
}

MOCK_USER_RESPONSE = {
    "login": "johndoe",
    "avatar_url": "https://avatars.github.com/1",
    "html_url": "https://github.com/johndoe",
    "bio": "Go developer at Google",
    "location": "San Francisco",
    "company": "Google",
    "blog": "https://johndoe.dev",
    "public_repos": 42,
    "followers": 500
}

MOCK_REPOS_RESPONSE = [
    {
        "name": "k8s-operator",
        "description": "Kubernetes operator for Go apps",
        "stargazers_count": 234,
        "topics": ["kubernetes", "go", "operator"],
        "pushed_at": "2024-01-15T10:00:00Z"
    }
]

MOCK_LANGUAGES_RESPONSE = {"Go": 85000, "Python": 10000, "Shell": 5000}

@pytest.mark.asyncio
async def test_search_users_returns_candidates():
    scraper = GitHubScraper(token="fake-token")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(
        json=MagicMock(return_value=MOCK_SEARCH_RESPONSE),
        raise_for_status=MagicMock()
    ))
    result = await scraper.search_users("kubernetes+language:go+followers:>5", client=mock_client)
    assert len(result) == 1
    assert result[0]["login"] == "johndoe"

@pytest.mark.asyncio
async def test_fetch_candidate_profile_returns_profile():
    scraper = GitHubScraper(token="fake-token")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[
        MagicMock(json=MagicMock(return_value=MOCK_USER_RESPONSE), raise_for_status=MagicMock()),
        MagicMock(json=MagicMock(return_value=MOCK_REPOS_RESPONSE), raise_for_status=MagicMock()),
        MagicMock(json=MagicMock(return_value=MOCK_LANGUAGES_RESPONSE), raise_for_status=MagicMock()),
    ])
    profile = await scraper.fetch_candidate_profile("johndoe", client=mock_client)
    assert isinstance(profile, CandidateProfile)
    assert profile.username == "johndoe"
    assert profile.bio == "Go developer at Google"
    assert "Go" in profile.languages
    assert len(profile.top_repos) == 1
    assert profile.top_repos[0].stars == 234
