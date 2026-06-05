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
        """构建 GitHub 用户搜索查询字符串"""
        parts = []
        for kw in self.search_keywords[:3]:
            parts.append(kw)
        if self.languages:
            parts.append(f"language:{self.languages[0]}")
        parts.append("followers:>5")
        return "+".join(parts)

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
