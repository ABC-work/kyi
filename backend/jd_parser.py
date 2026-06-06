# backend/jd_parser.py
import json
import re
import os
from openai import OpenAI
from models import ParsedJD

GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_MODEL = "llama-3.1-8b-instant"

JD_PARSE_PROMPT = """你是一个 HR 助手，请从以下 JD 中提取关键信息，严格以 JSON 格式输出，不要有任何额外说明：
{
  "required_skills": ["必须技能1", "必须技能2"],
  "bonus_skills": ["加分技能1"],
  "languages": ["编程语言，小写，如 go/python/javascript"],
  "min_years": 0,
  "search_keywords": ["单个英文单词关键词，不能有空格，如 kubernetes/microservice/golang/redis/docker"]
}

注意：search_keywords 每项必须是单个英文单词，不能包含空格。

JD:
%JD_TEXT%"""

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
    """调用 OpenAI 解析 JD，返回 ParsedJD 对象"""
    if client is None:
        client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url=GROQ_BASE_URL)

    prompt = JD_PARSE_PROMPT.replace("%JD_TEXT%", jd_text)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}]
    )
    raw_text = response.choices[0].message.content
    json_text = _extract_json(raw_text)
    # Sanitize control characters that cause json.loads to fail
    json_text = re.sub(r'(?<!\\)[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', ' ', json_text)
    json_text = re.sub(r'(?<!\\)\n', ' ', json_text)
    json_text = re.sub(r'(?<!\\)\r', ' ', json_text)
    data = json.loads(json_text)

    return ParsedJD(
        required_skills=data.get("required_skills", []),
        bonus_skills=data.get("bonus_skills", []),
        languages=data.get("languages", []),
        min_years=int(data.get("min_years", 0)),
        search_keywords=data.get("search_keywords", [])
    )
