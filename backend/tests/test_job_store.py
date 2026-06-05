# backend/tests/test_job_store.py
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from job_store import JobStore
from models import JobStatus

def test_create_and_get_job():
    store = JobStore()
    job_id = store.create_job()
    job = store.get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.status == JobStatus.PENDING

def test_update_job_status():
    store = JobStore()
    job_id = store.create_job()
    store.update_status(job_id, JobStatus.SEARCHING)
    assert store.get_job(job_id).status == JobStatus.SEARCHING

def test_update_progress():
    store = JobStore()
    job_id = store.create_job()
    store.update_progress(job_id, found=10, total=10)
    store.update_progress(job_id, scored=5)
    job = store.get_job(job_id)
    assert job.found == 10
    assert job.total == 10
    assert job.scored == 5

def test_set_results():
    store = JobStore()
    job_id = store.create_job()
    store.set_results(job_id, [])
    assert store.get_job(job_id).status == JobStatus.DONE
    assert store.get_job(job_id).results == []

def test_set_error():
    store = JobStore()
    job_id = store.create_job()
    store.set_error(job_id, "GitHub API failed")
    job = store.get_job(job_id)
    assert job.status == JobStatus.ERROR
    assert job.error == "GitHub API failed"

def test_get_nonexistent_job_returns_none():
    store = JobStore()
    assert store.get_job("nonexistent-id") is None
