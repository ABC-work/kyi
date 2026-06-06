# backend/job_store.py
import uuid
from typing import Optional
from models import Job, JobStatus, ScoredCandidate

class JobStore:
    def __init__(self):
        self._jobs: dict = {}

    def create_job(self) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = Job(job_id=job_id)
        return job_id

    def get_job(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def update_status(self, job_id: str, status: JobStatus) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.status = status

    def update_progress(self, job_id: str, found: int = None, scored: int = None, total: int = None) -> None:
        job = self._jobs.get(job_id)
        if not job:
            return
        if found is not None:
            job.found = found
        if scored is not None:
            job.scored = scored
        if total is not None:
            job.total = total
        # 后端兜底：scored == total 时主动设为 done，防止 set_results 调用前的窗口期
        if job.total > 0 and job.scored >= job.total and job.status == JobStatus.SCORING:
            job.status = JobStatus.DONE

    def add_result(self, job_id: str, result) -> None:
        """实时追加单个打分结果"""
        job = self._jobs.get(job_id)
        if job:
            job.results.append(result)

    def set_results(self, job_id: str, results: list) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.results = results
            job.status = JobStatus.DONE

    def set_error(self, job_id: str, error: str) -> None:
        job = self._jobs.get(job_id)
        if job:
            job.error = error
            job.status = JobStatus.ERROR

# 全局单例，供 main.py 使用
job_store = JobStore()
