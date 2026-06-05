# backend/tests/test_api.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from main import app

client = TestClient(app, raise_server_exceptions=False)

def test_post_search_returns_job_id():
    resp = client.post("/api/search", json={"jd_text": "需要 Go 工程师，3年经验"})
    assert resp.status_code == 200
    data = resp.json()
    assert "job_id" in data
    assert len(data["job_id"]) > 0

def test_get_status_pending():
    resp = client.post("/api/search", json={"jd_text": "需要 Go 工程师"})
    job_id = resp.json()["job_id"]
    resp = client.get(f"/api/status/{job_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["job_id"] == job_id
    assert "status" in data

def test_get_status_nonexistent_job_returns_404():
    resp = client.get("/api/status/nonexistent-id-xyz")
    assert resp.status_code == 404

def test_get_results_nonexistent_job_returns_404():
    resp = client.get("/api/results/nonexistent-id-xyz")
    assert resp.status_code == 404
