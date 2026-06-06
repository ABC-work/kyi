import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from unittest.mock import MagicMock
from scorer import score_candidate
from models import CandidateProfile, ParsedJD, ScoredCandidate, RepoInfo

MOCK_SCORE_RESPONSE = '''{
  "score": 82,
  "reason": "精通 Go，有 Kubernetes 实战项目",
  "strengths": ["Go 语言主力", "K8s operator 经验"],
  "gaps": ["缺少金融领域背景"]
}'''

def _make_openai_mock(text):
    mock_client = MagicMock()
    mock_msg = MagicMock()
    mock_msg.content = text
    mock_choice = MagicMock()
    mock_choice.message = mock_msg
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    mock_client.chat.completions.create.return_value = mock_response
    return mock_client

def _make_candidate():
    return CandidateProfile(
        username="johndoe",
        avatar_url="https://avatars.github.com/1",
        html_url="https://github.com/johndoe",
        bio="Go developer",
        languages={"Go": 85000, "Python": 10000},
        top_repos=[RepoInfo("k8s-op", "K8s operator", 234, ["kubernetes", "go"])],
        last_active="2024-01-15"
    )

def _make_parsed_jd():
    return ParsedJD(
        required_skills=["Go", "Kubernetes"],
        bonus_skills=["Docker"],
        languages=["go"],
        min_years=3,
        search_keywords=["kubernetes", "microservice"]
    )

def test_score_candidate_returns_scored_candidate():
    mock_client = _make_openai_mock(MOCK_SCORE_RESPONSE)
    result = score_candidate(_make_candidate(), _make_parsed_jd(), client=mock_client)
    assert isinstance(result, ScoredCandidate)
    assert result.score == 82
    assert result.username == "johndoe"
    assert len(result.strengths) == 2
    assert len(result.gaps) == 1

def test_score_candidate_preserves_profile_fields():
    mock_client = _make_openai_mock(MOCK_SCORE_RESPONSE)
    candidate = _make_candidate()
    result = score_candidate(candidate, _make_parsed_jd(), client=mock_client)
    assert result.html_url == candidate.html_url
    assert result.avatar_url == candidate.avatar_url
    assert result.bio == candidate.bio
