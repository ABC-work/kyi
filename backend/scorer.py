import json
import re
import os
from openai import OpenAI
from models import CandidateProfile, ParsedJD, ScoredCandidate

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.1-8b-instant"

SCORE_PROMPT = """技术猎头打分。只输出JSON，无其他内容：
{"score":0-100,"reason":"候选人实际技术情况一句话，不引用规则编号","strengths":["最多2条，规则见下"],"gaps":["最多2条，规则见下"]}

分数 = 可见证据量（严格按下表，禁止因知名度/Star/年限上调）：
80-100 → ≥2个仓库/项目直接证明核心技能
60-79  → 1个相关仓库 或 Bio明确提及核心框架
40-59  → 主语言匹配但无框架直接证据
1-39   → 主语言不符合岗位语言要求

strengths规则：只填简短技术名词（如"React""TypeScript hooks"）；禁止复制岗位需求原文；禁止含冒号或百分比；找不到证据就填[]
gaps规则：只填完全缺失的技能；已在strengths里出现的禁止重复出现在gaps里

岗位：%required_skills% | 语言：%languages% | 加分：%bonus_skills%
@%username% | Bio：%bio% | 语言：%lang_summary% | 项目：%repos_summary%"""


# ── strengths 清洗 ──────────────────────────────────────────────────────────
_LANG_PCT_RE   = re.compile(r'\(\d+%\)')   # 只删 "(85%)" 括号，保留前面的语言名
_COLON_CONTENT = re.compile(r'.+:.+')                    # "repo-name: description"

def _clean_strengths(strengths: list, jd_required: list) -> list:
    """清理 strengths 中的格式污染：
    1. 去掉 Language(X%) 格式残留（来自 lang_summary 泄露）
    2. 去掉含冒号的条目（仓库名:描述 格式）
    3. 去掉直接复制多个 JD 需求词的逗号列表（需求原文粘贴）
    4. 去重（大小写不敏感）
    """
    # JD skills set，用于检测"多词粘贴"
    jd_set = {s.strip().lower() for s in jd_required}

    seen: set[str] = set()
    cleaned: list[str] = []
    for s in strengths:
        # 去掉 Language(X%) token
        s = _LANG_PCT_RE.sub('', s).strip()
        s = re.sub(r'\s+', ' ', s)
        if not s:
            continue
        # 含冒号 → 仓库名:描述格式，丢弃
        if _COLON_CONTENT.match(s):
            continue
        # 逗号分隔且多项命中 JD → 整段需求原文粘贴，丢弃
        parts = [p.strip().lower() for p in s.split(',')]
        if len(parts) >= 2 and sum(1 for p in parts if p in jd_set) >= 2:
            continue
        # 去重
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        cleaned.append(s)
    return cleaned


# ── gaps 清洗 ────────────────────────────────────────────────────────────────
# 正向动词模式：gap 条目若以这些词开头或包含此类断言，则是正向表述（不该出现在gaps里）
# 精确到正向动词，不误伤"缺少经验"/"无证据"这类合法缺失描述
_GAP_POSITIVE_RE = re.compile(
    r'(^|[,，；;])\s*(有|具备|掌握|熟悉|擅长|拥有)',
    re.UNICODE
)

def _clean_gaps(gaps: list, strengths: list) -> list:
    """清理 gaps 中混入的正向内容：
    1. 移除以正向动词（有/具备/掌握/熟悉/擅长）断言的条目
    2. 移除与 strengths 有技术词重叠的条目（同一技能不能两边都有）
    保留合法缺失描述：缺少X、未见X、无X项目、不具备X等
    """
    # 从 strengths 中提取技术关键词（ASCII长度>2，或中文词）
    strength_tokens: set[str] = set()
    for s in strengths:
        for w in re.split(r'[\s/\-\.，,；;]+', s.lower()):
            w = w.rstrip('.,;')
            if len(w) > 2:
                strength_tokens.add(w)

    cleaned = []
    for gap in gaps:
        # 规则1：以正向动词开头/断言 → 丢弃
        if _GAP_POSITIVE_RE.search(gap):
            continue
        # 规则2：与 strengths 技术词重叠（且该词长度>3，避免"go"等误判）→ 丢弃
        gap_tokens = {w.lower().rstrip('.,;') for w in re.split(r'[\s/\-\.，,；;]+', gap) if len(w) > 3}
        if gap_tokens & strength_tokens:
            continue
        # 去重（大小写不敏感）
        key = gap.lower().strip()
        if key not in {g.lower().strip() for g in cleaned}:
            cleaned.append(gap)
    return cleaned

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
        return "无"
    lines = []
    for r in repos[:3]:  # 只取前3个（原5个）
        # 描述截断到50字，不输出topics（节省token）
        desc = (r.description or "")[:50]
        lines.append(f"{r.name}(⭐{r.stars}){':'+desc if desc else ''}")
    return "; ".join(lines)

def score_candidate(candidate: CandidateProfile, parsed_jd: ParsedJD, client=None) -> ScoredCandidate:
    """调用 OpenAI 给单个候选人打分，返回 ScoredCandidate"""
    if client is None:
        client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url=GROQ_BASE_URL)

    prompt = (SCORE_PROMPT
        .replace("%required_skills%", ", ".join(parsed_jd.required_skills))
        .replace("%bonus_skills%", ", ".join(parsed_jd.bonus_skills))
        .replace("%languages%", ", ".join(parsed_jd.languages))
        .replace("%min_years%", str(parsed_jd.min_years))
        .replace("%username%", candidate.username)
        .replace("%bio%", (candidate.bio or "")[:120])   # 截断bio，节省token
        .replace("%lang_summary%", _format_languages(candidate.languages))
        .replace("%repos_summary%", _format_repos(candidate.top_repos))
    )

    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=200,   # 原512，输出只需score+reason+2strengths+2gaps
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.choices[0].message.content
    json_text = _extract_json(raw_text)
    # Sanitize control characters that cause json.loads to fail
    json_text = re.sub(r'(?<!\\)[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', json_text)
    json_text = re.sub(r'(?<!\\)\n', ' ', json_text)
    json_text = re.sub(r'(?<!\\)\r', ' ', json_text)
    data = json.loads(json_text)

    def _to_str_list(val):
        """确保返回字符串列表，兼容 LLM 偶发输出 dict 的情况"""
        if not isinstance(val, list):
            return []
        return [v if isinstance(v, str) else (list(v.values())[0] if isinstance(v, dict) and v else str(v))
                for v in val]

    raw_strengths   = _to_str_list(data.get("strengths", []))
    raw_gaps        = _to_str_list(data.get("gaps", []))
    clean_strengths = _clean_strengths(raw_strengths, parsed_jd.required_skills)
    clean_gaps      = _clean_gaps(raw_gaps, clean_strengths)

    # reason 兜底：LLM 偶发返回空字符串时，根据证据自动生成摘要
    reason = (data.get("reason") or "").strip()
    if not reason:
        score_val = int(data.get("score", 0))
        if clean_strengths:
            reason = f"具备 {clean_strengths[0]} 等技能证据" + (
                f"，但缺少 {clean_gaps[0]}" if clean_gaps else "，与岗位有一定匹配")
        elif candidate.languages:
            primary = max(candidate.languages.items(), key=lambda x: x[1])[0]
            match = "匹配" if score_val >= 40 else "不符"
            reason = f"主语言 {primary} 与岗位要求{match}，未见框架直接证据"
        else:
            reason = "资料不足，无法评估技能匹配度"

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
        reason=reason,
        strengths=clean_strengths,
        gaps=clean_gaps,
    )
