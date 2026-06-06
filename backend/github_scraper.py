# backend/github_scraper.py
import os
import re
import httpx
from models import CandidateProfile, RepoInfo

GITHUB_API = "https://api.github.com"

# 通用词：不用作框架关键词（这些由 language:X 已覆盖）
_GENERIC_TERMS = {
    "javascript", "typescript", "python", "java", "go", "golang", "rust",
    "css", "html", "sql", "git", "linux", "docker", "api", "apis",
    "web", "frontend", "backend", "fullstack", "mobile", "cloud",
    "rest", "restful", "http", "json", "xml",
}

_BOT_KEYWORDS = ("-bot", "-robot", "[bot]", "ci-robot", "dependabot", "renovate")


class GitHubScraper:
    def __init__(self, token: str = None):
        self.token = token or os.getenv("GITHUB_TOKEN", "")
        self.headers = {
            "Authorization": f"token {self.token}",
            "Accept": "application/vnd.github.v3+json"
        }

    def _make_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(headers=self.headers, timeout=15.0)

    # ── 主搜索：通过仓库找开发者 ─────────────────────────────────────────────
    async def _find_users_via_repos(self, parsed_jd, client) -> list[str]:
        """仓库搜索策略（精准）：
        找仓库语言=TypeScript/JavaScript 且名称/描述/topic 含框架名的仓库，
        提取其个人账号 owner。比 user bio 搜索精准得多。
        """
        # 从 required_skills 提取最有区分度的框架词
        framework = None
        for skill in parsed_jd.required_skills[:6]:
            word = skill.strip().split()[0].rstrip(".,/")
            if word and word.isascii() and word.lower() not in _GENERIC_TERMS:
                framework = word
                break

        langs = parsed_jd.languages[:3] if parsed_jd.languages else [None]

        # topic 归一化："Next.js" → "nextjs", "Vue.js" → "vuejs"
        topic = re.sub(r'[^a-z0-9]', '', framework.lower()) if framework else None

        # ── 搜索策略（按信号强弱排序）────────────────────────────────────────
        # A. topic:{framework} + language:X   → 仓库 owner 明确 tagged，强信号
        # B. {framework_text} + language:X    → 仓库名/描述含框架词，中等信号
        # topic 只对主语言（langs[0]）跑，避免 API 调用过多
        queries: list[str] = []

        # A: topic 强匹配（主语言）
        if topic and langs[0]:
            queries.append(f"topic:{topic} language:{langs[0]} pushed:>2022-06-01")

        # B: 文本匹配 × 全部 JD 语言
        for lang in langs:
            parts = []
            if framework:
                parts.append(framework)
            if lang:
                parts.append(f"language:{lang}")
            parts.extend(["pushed:>2022-06-01", "stars:>0"])
            queries.append(" ".join(parts))

        seen: set[str] = set()
        usernames: list[str] = []

        for query in queries:
            print(f"[repo-search] {query}")
            try:
                resp = await client.get(
                    f"{GITHUB_API}/search/repositories",
                    params={"q": query, "sort": "updated", "per_page": 60},
                )
                resp.raise_for_status()
                repos = resp.json().get("items", [])
            except Exception as e:
                print(f"  failed: {e}")
                continue

            before = len(usernames)
            for repo in repos:
                owner = repo.get("owner", {})
                login = owner.get("login", "")
                if (
                    owner.get("type") == "User"
                    and login not in seen
                    and not any(kw in login.lower() for kw in _BOT_KEYWORDS)
                ):
                    seen.add(login)
                    usernames.append(login)
            print(f"  → {len(repos)} repos, +{len(usernames) - before} new owners")

        print(f"[repo-search] {len(usernames)} unique owners from {len(queries)} queries")
        return usernames

    # ── 备用搜索：user bio 搜索（兜底）──────────────────────────────────────
    async def _find_users_via_bio(self, parsed_jd, client) -> list[str]:
        """Bio/名称关键词搜索（兜底）。
        仓库搜索结果不足时使用。
        """
        query = parsed_jd.build_github_query()
        print(f"[user-search/fallback] {query}")

        resp = await client.get(
            f"{GITHUB_API}/search/users",
            params={"q": query, "per_page": 30},
        )
        resp.raise_for_status()
        users = resp.json().get("items", [])

        return [
            u["login"]
            for u in users
            if u.get("type") == "User"
            and not any(kw in u["login"].lower() for kw in _BOT_KEYWORDS)
        ]

    # ── 抓取单个用户详情 ─────────────────────────────────────────────────────
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
                params={"sort": "stars", "per_page": 5},
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

            top_repos = [
                RepoInfo(
                    name=r.get("name", ""),
                    description=r.get("description") or "",
                    stars=r.get("stargazers_count", 0),
                    topics=r.get("topics", []),
                )
                for r in repos_data[:5]
            ]

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
                last_active=last_active,
            )
        finally:
            if close_client:
                await client.aclose()

    # ── 完整候选人获取流程 ───────────────────────────────────────────────────
    async def fetch_candidates(self, parsed_jd) -> list:
        """仓库搜索 → （不足则补 bio 搜索）→ 过滤 followers → 抓取详情"""
        async with self._make_client() as client:
            # Phase 1: 仓库搜索（精准）
            usernames = await self._find_users_via_repos(parsed_jd, client)

            # Phase 2: 结果不足时补充 bio 搜索
            if len(usernames) < 10:
                fallback = await self._find_users_via_bio(parsed_jd, client)
                existing = set(usernames)
                for u in fallback:
                    if u not in existing:
                        usernames.append(u)
                        existing.add(u)
                print(f"[fallback] after merge: {len(usernames)} candidates")

            # Phase 3: 抓取详情，过滤 followers + 语言
            # JS/TS 互通：TypeScript 岗位接受 JavaScript 主语言候选人（反之亦然）
            jd_lang_set: set[str] = set()
            for lang in parsed_jd.languages:
                ll = lang.lower()
                jd_lang_set.add(ll)
                if ll == "typescript":  jd_lang_set.add("javascript")
                if ll == "javascript":  jd_lang_set.add("typescript")

            profiles: list[CandidateProfile] = []
            for username in usernames[:40]:   # 最多抓40个，过滤后确保够30
                try:
                    profile = await self.fetch_candidate_profile(username, client=client)

                    # followers 过滤
                    if not (10 <= profile.followers <= 5000):
                        print(f"  [skip/followers] {username}: {profile.followers}")
                        continue

                    # 语言过滤：候选人仓库语言须与JD至少有一个交集
                    if jd_lang_set and profile.languages:
                        candidate_langs = {l.lower() for l in profile.languages}
                        if not (candidate_langs & jd_lang_set):
                            print(f"  [skip/lang] {username}: {candidate_langs} ∩ {jd_lang_set} = ∅")
                            continue

                    profiles.append(profile)
                    if len(profiles) >= 30:
                        break
                except Exception as e:
                    print(f"Warning: failed to fetch {username}: {e}")

            print(f"[fetch] {len(profiles)} profiles passed followers+language filters")
            return profiles
