# backend/gitee_scraper.py
import os
import httpx

GITEE_API = "https://gitee.com/api/v5"

_BOT_KEYWORDS = ("-bot", "-robot", "[bot]", "ci-robot", "dependabot", "renovate")


class GiteeScraper:
    def __init__(self, token: str = None):
        self.token = token or os.getenv("GITEE_TOKEN", "")
        self.headers = {"Accept": "application/json"}
        if self.token:
            self.headers["Authorization"] = f"token {self.token}"

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self.headers, timeout=15.0)

    async def search_users(self, query: str, client) -> list[dict]:
        """Search Gitee users by name/username. Returns candidate dicts with source='gitee'."""
        try:
            resp = await client.get(
                f"{GITEE_API}/search/users",
                params={"q": query, "per_page": 5}
            )
            resp.raise_for_status()
            items = resp.json() or []
        except Exception:
            return []

        results = []
        for u in items:
            login = u.get("login", "")
            if not login:
                continue
            if any(kw in login.lower() for kw in _BOT_KEYWORDS):
                continue
            results.append({
                "login": login,
                "avatar_url": u.get("avatar_url", ""),
                "html_url": u.get("html_url", f"https://gitee.com/{login}"),
                "bio": u.get("bio") or u.get("name") or "",
                "source": "gitee",
            })
        return results

    async def fetch_profile(self, username: str, client=None) -> dict | None:
        """Fetch a Gitee user profile. Returns a dict with CandidateProfile-compatible keys,
        or None on 404/error."""
        close_client = client is None
        if client is None:
            client = self._make_client()
        try:
            # Fetch user
            resp = await client.get(f"{GITEE_API}/users/{username}")
            resp.raise_for_status()
            user = resp.json()

            # Fetch repos (sorted by stars)
            resp2 = await client.get(
                f"{GITEE_API}/users/{username}/repos",
                params={"sort": "stargazers_count", "per_page": 5, "type": "owner"}
            )
            resp2.raise_for_status()
            repos = resp2.json() or []

            # Build languages dict: count repos per language
            languages: dict[str, int] = {}
            for r in repos:
                lang = r.get("language") or ""
                if lang:
                    languages[lang] = languages.get(lang, 0) + 1

            top_repos = [
                {
                    "name": r.get("name", ""),
                    "description": r.get("description") or "",
                    "stars": r.get("stargazers_count", 0),
                    "topics": [],
                }
                for r in repos[:5]
            ]

            last_active = ""
            if repos:
                pushed = repos[0].get("pushed_at", "")
                last_active = pushed[:10] if pushed else ""

            return {
                "username": user.get("login", username),
                "avatar_url": user.get("avatar_url", ""),
                "html_url": user.get("html_url", f"https://gitee.com/{username}"),
                "bio": user.get("bio") or "",
                "location": user.get("location") or "",
                "company": user.get("company") or "",
                "blog": user.get("blog") or "",
                "public_repos": user.get("public_repos", 0),
                "followers": user.get("followers_count", 0) or user.get("followers", 0),
                "languages": languages,
                "top_repos": top_repos,
                "last_active": last_active,
                "display_name": user.get("name") or "",
            }

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            return None
        except Exception:
            return None
        finally:
            if close_client:
                await client.aclose()
