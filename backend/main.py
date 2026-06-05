# backend/main.py
import csv
import io
import os
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from anthropic import Anthropic

from job_store import job_store
from jd_parser import parse_jd
from github_scraper import GitHubScraper
from scorer import score_candidate
from models import JobStatus

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = FastAPI(title="Talent Hunter")

# 挂载前端静态文件
frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

class SearchRequest(BaseModel):
    jd_text: str

async def run_pipeline(job_id: str, jd_text: str):
    """核心异步流水线：解析JD → 抓取候选人 → 打分 → 存储结果"""
    try:
        anthropic_client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
        scraper = GitHubScraper(token=os.getenv("GITHUB_TOKEN"))

        job_store.update_status(job_id, JobStatus.SEARCHING)
        parsed_jd = parse_jd(jd_text, client=anthropic_client)

        profiles = await scraper.fetch_candidates(parsed_jd)
        job_store.update_progress(job_id, found=len(profiles), total=len(profiles))

        job_store.update_status(job_id, JobStatus.SCORING)
        scored = []
        for i, profile in enumerate(profiles):
            try:
                result = score_candidate(profile, parsed_jd, client=anthropic_client)
                scored.append(result)
            except Exception as e:
                print(f"Warning: scoring failed for {profile.username}: {e}")
            job_store.update_progress(job_id, scored=i + 1)

        scored.sort(key=lambda x: x.score, reverse=True)
        job_store.set_results(job_id, scored)

    except Exception as e:
        job_store.set_error(job_id, str(e))
        raise

@app.post("/api/search")
async def post_search(req: SearchRequest, background_tasks: BackgroundTasks):
    job_id = job_store.create_job()
    background_tasks.add_task(run_pipeline, job_id, req.jd_text)
    return {"job_id": job_id}

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job.job_id,
        "status": job.status,
        "found": job.found,
        "scored": job.scored,
        "total": job.total,
        "error": job.error
    }

@app.get("/api/results/{job_id}")
def get_results(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=202, detail=f"Job not done yet: {job.status}")
    return {
        "job_id": job_id,
        "total": len(job.results),
        "candidates": [
            {
                "rank": i + 1,
                "username": c.username,
                "avatar_url": c.avatar_url,
                "html_url": c.html_url,
                "bio": c.bio,
                "location": c.location,
                "company": c.company,
                "score": c.score,
                "reason": c.reason,
                "strengths": c.strengths,
                "gaps": c.gaps,
                "followers": c.followers,
                "public_repos": c.public_repos,
                "last_active": c.last_active
            }
            for i, c in enumerate(job.results)
        ]
    }

@app.get("/api/export/{job_id}")
def export_csv(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.DONE:
        raise HTTPException(status_code=202, detail="Job not done yet")

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["排名", "用户名", "分数", "匹配理由", "优势", "不足", "GitHub主页", "位置", "公司", "Followers"])
    for i, c in enumerate(job.results):
        writer.writerow([
            i + 1, c.username, c.score, c.reason,
            " | ".join(c.strengths), " | ".join(c.gaps),
            c.html_url, c.location, c.company, c.followers
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=talent-hunt-{job_id[:8]}.csv"}
    )

@app.get("/")
def serve_index():
    index_path = os.path.join(frontend_dir, "index.html")
    if os.path.exists(index_path):
        with open(index_path) as f:
            return HTMLResponse(f.read())
    return HTMLResponse("<h1>Talent Hunter API</h1><p>Frontend not found.</p>")
