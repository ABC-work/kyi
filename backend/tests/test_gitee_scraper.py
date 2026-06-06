# backend/tests/test_gitee_scraper.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
import httpx
from unittest.mock import AsyncMock, MagicMock
from gitee_scraper import GiteeScraper

MOCK_SEARCH_RESPONSE = [
    {
        "login": "zhangsan",
        "avatar_url": "https://gitee.com/avatars/zhangsan",
        "html_url": "https://gitee.com/zhangsan",
        "bio": "Go 开发工程师",
        "name": "张三"
    },
    {
        "login": "zhangsan-bot",
        "avatar_url": "",
        "html_url": "https://gitee.com/zhangsan-bot",
        "bio": "",
        "name": "bot"
    }
]

MOCK_USER_RESPONSE = {
    "login": "zhangsan",
    "avatar_url": "https://gitee.com/avatars/zhangsan",
    "html_url": "https://gitee.com/zhangsan",
    "bio": "Go 开发工程师",
    "name": "张三",
    "blog": "https://zhangsan.dev",
    "public_repos": 20,
    "followers_count": 150,
    "location": "北京",
    "company": "某科技公司"
}

MOCK_REPOS_RESPONSE = [
    {
        "name": "k8s-helper",
        "description": "Kubernetes 助手工具",
        "stargazers_count": 88,
        "language": "Go",
        "pushed_at": "2024-03-01T10:00:00+08:00"
    },
    {
        "name": "go-utils",
        "description": "常用 Go 工具集",
        "stargazers_count": 45,
        "language": "Go",
        "pushed_at": "2024-01-15T10:00:00+08:00"
    },
    {
        "name": "python-scripts",
        "description": "运维脚本",
        "stargazers_count": 12,
        "language": "Python",
        "pushed_at": "2023-06-01T10:00:00+08:00"
    }
]


@pytest.mark.asyncio
async def test_search_users_returns_candidates():
    scraper = GiteeScraper()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=MagicMock(
        json=MagicMock(return_value=MOCK_SEARCH_RESPONSE),
        raise_for_status=MagicMock()
    ))
    result = await scraper.search_users("张三", mock_client)
    logins = [r["login"] for r in result]
    assert "zhangsan" in logins
    assert "zhangsan-bot" not in logins
    assert all(r["source"] == "gitee" for r in result)


@pytest.mark.asyncio
async def test_fetch_profile_returns_dict():
    scraper = GiteeScraper()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=[
        MagicMock(json=MagicMock(return_value=MOCK_USER_RESPONSE), raise_for_status=MagicMock()),
        MagicMock(json=MagicMock(return_value=MOCK_REPOS_RESPONSE), raise_for_status=MagicMock()),
    ])
    profile = await scraper.fetch_profile("zhangsan", mock_client)
    assert profile is not None
    assert profile["username"] == "zhangsan"
    assert profile["bio"] == "Go 开发工程师"
    assert profile["languages"]["Go"] == 2
    assert profile["languages"]["Python"] == 1
    assert len(profile["top_repos"]) == 3
    assert profile["last_active"] == "2024-03-01"


@pytest.mark.asyncio
async def test_fetch_profile_returns_none_on_404():
    scraper = GiteeScraper()
    mock_response = MagicMock()
    mock_response.status_code = 404
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(
        side_effect=httpx.HTTPStatusError("404", request=MagicMock(), response=mock_response)
    )
    profile = await scraper.fetch_profile("nonexistent-xyz", mock_client)
    assert profile is None
