# backend/jd_parser.py
import json
import re
import os
from anthropic import Anthropic
from models import ParsedJD

JD_PARSE_PROMPT = """你是一个 HR 助手，请从以下 JD 中提取关键信息，严格以 JSON 格式输出，不要有任何额外说明：
{{
  "required_skills": ["必须技能1", "必须技能2"],
  "bonus_skills": ["加分技能1"],
  "languages": ["编程语言，小写，如 go/python/javascript"],
  "min_years": 0,
  "search_keywords": ["用于GitHub搜索的英文关键词"]
}}

JD:
{jd_text}"""

def _extract_json(text: str) -> str:
    """从 LLM 响应中提取 JSON，处理被 markdown 包裹的情况"""
    match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r'\{.*\}', text, re.DOTALL)
    if match:
        return match.group(0)
    return text

def parse_jd(jd_text: str, client=None) -> ParsedJD:
    """调用 Claude 解析 JD，返回 ParsedJD 对象"""
    if client is None:
        client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    prompt = JD_PARSE_PROMPT.format(jd_text=jd_text)
    response = client.messages.create(
        model="claude-3-5-haiku-20241022",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.content[0].text
    json_text = _extract_json(raw_text)
    data = json.loads(json_text)

    return ParsedJD(
        required_skills=data.get("required_skills", []),
        bonus_skills=data.get("bonus_skills", []),
        languages=data.get("languages", []),
        min_years=int(data.get("min_years", 0)),
        search_keywords=data.get("search_keywords", [])
    )
