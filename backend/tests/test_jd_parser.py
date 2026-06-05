# backend/tests/test_jd_parser.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock
from jd_parser import parse_jd
from models import ParsedJD

MOCK_LLM_RESPONSE = '''{
  "required_skills": ["Go", "Kubernetes"],
  "bonus_skills": ["Docker", "gRPC"],
  "languages": ["go"],
  "min_years": 3,
  "search_keywords": ["kubernetes", "microservice", "golang"]
}'''

def test_parse_jd_returns_parsed_jd():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=MOCK_LLM_RESPONSE)]
    )
    result = parse_jd("需要 Go 后端工程师，熟悉 Kubernetes，3年经验", client=mock_client)
    assert isinstance(result, ParsedJD)
    assert "Go" in result.required_skills
    assert result.min_years == 3
    assert "kubernetes" in result.search_keywords

def test_parse_jd_calls_claude_once():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=MOCK_LLM_RESPONSE)]
    )
    parse_jd("some JD text", client=mock_client)
    assert mock_client.messages.create.call_count == 1

def test_parse_jd_builds_github_search_query():
    mock_client = MagicMock()
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=MOCK_LLM_RESPONSE)]
    )
    result = parse_jd("some JD text", client=mock_client)
    query = result.build_github_query()
    assert "language:go" in query
    assert "kubernetes" in query

def test_parse_jd_handles_json_with_extra_text():
    """LLM 有时会在 JSON 前后加上说明文字，确保能正确解析"""
    mock_client = MagicMock()
    response_with_extra = f"Sure, here is the JSON:\n```json\n{MOCK_LLM_RESPONSE}\n```"
    mock_client.messages.create.return_value = MagicMock(
        content=[MagicMock(text=response_with_extra)]
    )
    result = parse_jd("some JD text", client=mock_client)
    assert isinstance(result, ParsedJD)
    assert "Go" in result.required_skills
