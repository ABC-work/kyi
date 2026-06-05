# backend/tests/test_models.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from models import ParsedJD, CandidateProfile, ScoredCandidate, Job, JobStatus

def test_parsed_jd_defaults():
    jd = ParsedJD(
        required_skills=["Go", "Kubernetes"],
        bonus_skills=["Docker"],
        languages=["go"],
        min_years=3,
        search_keywords=["kubernetes", "microservice"]
    )
    assert jd.required_skills == ["Go", "Kubernetes"]
    assert jd.min_years == 3

def test_job_initial_status():
    job = Job(job_id="abc-123")
    assert job.status == JobStatus.PENDING
    assert job.found == 0
    assert job.scored == 0
    assert job.results == []

def test_scored_candidate_has_score():
    candidate = ScoredCandidate(
        username="johndoe",
        avatar_url="https://avatars.githubusercontent.com/u/1",
        html_url="https://github.com/johndoe",
        score=85,
        reason="精通 Go，有 K8s 经验",
        strengths=["Go expert"],
        gaps=["no finance background"]
    )
    assert candidate.score == 85
    assert len(candidate.strengths) == 1
