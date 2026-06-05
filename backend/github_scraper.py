# backend/github_scraper.py
import os
import httpx
from models import CandidateProfile, RepoInfo

GITHUB_API = "https://api.github.com"

class GitHubScraper:
    def __init__(self, token: str = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self.headers, timeout=15.0)

    async def search_users(self, query: str, client=None) -> list:
        """搜索 GitHub 用户，返回原始用户列表（最多30个）"""
        url = f"{GITHUB_API}/search/users"
        params = {"q": query, "per_page": 30, "sort": "followers"}
        close_client = client is None
        if client is None:
            client = self._make_client()
        try:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()
            return data.get("items", [])
        finally:
            if close_client:
                await client.aclose()

    async def fetch_candidate_profile(self, username: str, client=None) -> CandidateProfile:
        """抓取单个候选人的详细信息"""
        close_client = client is None
        if client is None:
            client = self._make_client()
        try:
            resp = await client.get(f"{GITHUB_API}/users/{username}")
            resp.raise_for_status()
            user = resp.json()

            resp = await client.get(
                f"{GITHUB_API}/users/{username}/repos",
                params={"sort": "stars", "per_page": 5}
            )
            resp.raise_for_status()
            repos_data = resp.json()

            languages = {}
            if repos_data:
                resp = await client.get(
                    f"{GITHUB_API}/repos/{username}/{repos_data[0]['name']}/languages"
                )
                resp.raise_for_status()
                languages = resp.json()

            top_repos = []
            for r in repos_data[:5]:
                top_repos.append(RepoInfo(
                    name=r.get("name", ""),
                    description=r.get("description") or "",
                    stars=r.get("stargazers_count", 0),
                    topics=r.get("topics", [])
                ))

            last_active = repos_data[0].get("pushed_at", "")[:10] if repos_data else ""

            return CandidateProfile(
                username=user.get("login", username),
                avatar_url=user.get("avatar_url", ""),
                html_url=user.get("html_url", ""),
                bio=user.get("bio") or "",
                location=user.get("location") or "",
                company=user.get("company") or "",
                blog=user.get("blog") or "",
                public_repos=user.get("public_repos", 0),
                followers=user.get("followers", 0),
                languages=languages,
                top_repos=top_repos,
                last_active=last_active
            )
        finally:
            if close_client:
                await client.aclose()

    async def fetch_candidates(self, parsed_jd) -> list:
        """完整流程：搜索 + 逐个抓取详情"""
        query = parsed_jd.build_github_query()
        users = await self.search_users(query)
        profiles = []
        async with self._make_client() as client:
            for user in users:
                try:
                    profile = await self.fetch_candidate_profile(user["login"], client=client)
                    profiles.append(profile)
                except Exception as e:
                    print(f"Warning: failed to fetch {user['login']}: {e}")
                    continue
        return profiles
