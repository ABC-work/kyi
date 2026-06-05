import json
import re
import os
from anthropic import Anthropic
from models import CandidateProfile, ParsedJD, ScoredCandidate

SCORE_PROMPT = """你是一个专业猎头，根据岗位要求给候选人打分（0-100）并说明理由。
严格以 JSON 格式输出，不要有任何额外说明：
{{
  "score": 0-100的整数,
  "reason": "一句话总结匹配情况",
  "strengths": ["优势1", "优势2"],
  "gaps": ["不足1", "不足2"]
}}

岗位要求：
- 必须技能：{required_skills}
- 加分技能：{bonus_skills}
- 编程语言：{languages}
- 最低年限：{min_years}年

候选人信息：
- 用户名：{username}
- Bio：{bio}
- 主要编程语言：{lang_summary}
- 代表项目（Top 5）：{repos_summary}
- 最近活跃：{last_active}
- Followers：{followers}"""

def _extract_json(text: str) -> str:
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return text

def _format_languages(languages: dict) -> str:
    if not languages:
        return "未知"
    total = sum(languages.values()) or 1
    parts = [f"{lang}({v*100//total}%)" for lang, v in sorted(languages.items(), key=lambda x: -x[1])[:3]]
    return ", ".join(parts)

def _format_repos(repos) -> str:
    if not repos:
        return "无公开仓库"
    lines = []
    for r in repos:
        topics = ", ".join(r.topics[:3]) if r.topics else "无"
        lines.append(f"- {r.name}（⭐{r.stars}）: {r.description or '无描述'} [topics: {topics}]")
    return "\n".join(lines)

def score_candidate(candidate: CandidateProfile, parsed_jd: ParsedJD, client=None) -> ScoredCandidate:
    """调用 Claude 给单个候选人打分，返回 ScoredCandidate"""
    if client is None:
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = SCORE_PROMPT.format(
        required_skills=", ".join(parsed_jd.required_skills),
        bonus_skills=", ".join(parsed_jd.bonus_skills),
        languages=", ".join(parsed_jd.languages),
        min_years=parsed_jd.min_years,
        username=candidate.username,
        bio=candidate.bio or "未填写",
        lang_summary=_format_languages(candidate.languages),
        repos_summary=_format_repos(candidate.top_repos),
        last_active=candidate.last_active or "未知",
        followers=candidate.followers
    )

    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=512,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.content[0].text
    json_text = _extract_json(raw_text)
    data = json.loads(json_text)

    return ScoredCandidate(
        username=candidate.username,
        avatar_url=candidate.avatar_url,
        html_url=candidate.html_url,
        bio=candidate.bio,
        location=candidate.location,
        company=candidate.company,
        blog=candidate.blog,
        public_repos=candidate.public_repos,
        followers=candidate.followers,
        languages=candidate.languages,
        top_repos=candidate.top_repos,
        last_active=candidate.last_active,
        score=int(data.get("score", 0)),
        reason=data.get("reason", ""),
        strengths=data.get("strengths", []),
        gaps=data.get("gaps", [])
    )
