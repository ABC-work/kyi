# backend/models.py
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class JobStatus(str, Enum):
    PENDING = "pending"
    SEARCHING = "searching"
    SCORING = "scoring"
    DONE = "done"
    ERROR = "error"

@dataclass
class ParsedJD:
    required_skills: list[str]
    bonus_skills: list[str]
    languages: list[str]
    min_years: int
    search_keywords: list[str]

    def build_github_query(self) -> str:
        """构建 GitHub 用户搜索查询字符串。
        策略：framework关键词(React/Vue/Next.js等) + language:X，保证召回精准前端/特定栈候选人。
        """
        # ── 1. 从 required_skills 里找最有区分度的框架/工具词 ──────────────────
        # 跳过通用语言名（已由 language:X 覆盖）和纯通用词
        _generic = {
            "javascript", "typescript", "python", "java", "go", "golang", "rust",
            "css", "html", "sql", "git", "linux", "docker", "rest", "api", "apis",
            "web", "frontend", "backend", "fullstack", "mobile", "cloud",
        }
        framework_kw = None
        for skill in self.required_skills[:6]:
            word = skill.strip().split()[0]       # 取第一个单词（"Next.js" → "Next.js"）
            if word and word.isascii() and word.lower() not in _generic:
                framework_kw = word
                break

        # ── 2. 兜底：从 search_keywords 里取 ──────────────────────────────────
        if not framework_kw:
            for kw in self.search_keywords[:4]:
                word = (kw.strip().split()[0] if kw.strip() else "")
                if word and word.isascii() and word.lower() not in _generic:
                    framework_kw = word
                    break

        parts = []
        if framework_kw:
            parts.append(framework_kw)          # e.g. "React"
        if self.languages:
            parts.append(f"language:{self.languages[0]}")   # e.g. "language:TypeScript"
        parts.append("followers:10..5000")      # 过滤空壳账号 + 排除不可招募的技术名人
        parts.append("type:user")               # 只搜个人账号，排除 Organization
        print(f"[query] {' '.join(parts)}")
        return " ".join(parts)

@dataclass
class RepoInfo:
    name: str
    description: str
    stars: int
    topics: list[str]

@dataclass
class CandidateProfile:
    username: str
    avatar_url: str
    html_url: str
    bio: str = ""
    location: str = ""
    company: str = ""
    blog: str = ""
    public_repos: int = 0
    followers: int = 0
    languages: dict = field(default_factory=dict)
    top_repos: list = field(default_factory=list)
    last_active: str = ""

@dataclass
class ScoredCandidate(CandidateProfile):
    score: int = 0
    reason: str = ""
    strengths: list = field(default_factory=list)
    gaps: list = field(default_factory=list)

@dataclass
class Job:
    job_id: str
    status: JobStatus = JobStatus.PENDING
    found: int = 0
    scored: int = 0
    total: int = 0
    results: list = field(default_factory=list)
    error: Optional[str] = None
