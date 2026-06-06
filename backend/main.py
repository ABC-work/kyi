# backend/main.py
import asyncio
import csv
import io
import os
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI

from job_store import job_store
from jd_parser import parse_jd
from github_scraper import GitHubScraper
from scorer import score_candidate
from models import JobStatus, ScoredCandidate

load_dotenv(os.path.join(os.path.dirname(__file__), '..', '.env'))

app = FastAPI(title="Talent Hunter")

# 挂载前端静态文件
frontend_dir = os.path.join(os.path.dirname(__file__), '..', 'frontend')
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

class SearchRequest(BaseModel):
    jd_text: str

def _skill_gap_cap(result, parsed_jd) -> int:
    """核心技能缺失时强制压到 59 分以下（会被 ≥60 过滤掉）。
    触发条件（任一满足即降）：
      A. strengths 为空 —— LLM 找不到任何匹配优势
      B. gaps 中出现了 JD required_skills 的核心词 —— LLM 自己承认缺核心技能
    """
    score = result.score
    if score < 0:          # 仅跳过评分失败的，40-59 分段同样需要走盖帽逻辑
        return score

    # ── 条件 A：无任何优势 ───────────────────────────────────────────────────
    # 无论 LLM 给多少分，无证据上限50；有证据候选人上限59（备选）或更高（推荐）
    # 这样：有证据55分 > 无证据50分，自然排序无需额外次级键
    if not result.strengths:
        capped = min(score, 50)
        if capped != score:
            print(f"  [gap-cap/no-strengths] {result.username}: {score}→{capped}")
        return capped

    # ── 条件 B：gaps 包含 required_skills 核心词 ─────────────────────────────
    if parsed_jd.required_skills and result.gaps:
        # 取 required_skills 每项的第一个单词（去掉版本号/修饰词），长度 > 2
        req_tokens = set()
        for skill in parsed_jd.required_skills:
            token = skill.strip().split()[0].rstrip('.,/').lower()
            if len(token) > 2:
                req_tokens.add(token)

        for gap in result.gaps:
            gap_lower = gap.lower()
            for token in req_tokens:
                if token in gap_lower:
                    print(f"  [gap-cap/core-missing] {result.username}: {score}→59 "
                          f"(gap='{gap}' hits required='{token}')")
                    return 59

    return score


def _language_cap(candidate, parsed_jd) -> int:
    """后端硬盖帽：无论 LLM 打多高，主语言不符一律截断。
    防止 LLM 因项目知名度/经验年限等因素忽视语言不符规则。
    """
    score = candidate.score
    if score < 0 or not parsed_jd.languages or not candidate.languages:
        return score

    jd_langs = {l.lower() for l in parsed_jd.languages}
    # 按代码量排序，取前3语言
    sorted_langs = sorted(candidate.languages.items(), key=lambda x: -x[1])
    primary = sorted_langs[0][0].lower() if sorted_langs else ""
    top3 = {l.lower() for l, _ in sorted_langs[:3]}

    if primary in jd_langs:
        return score                    # 主语言命中，不限制
    elif top3 & jd_langs:
        return min(score, 65)          # 非主但前3语言有命中（全栈/副语言）
    else:
        return min(score, 40)          # 主语言完全不符，硬封顶40


def _adjusted_score(c) -> int:
    """在 LLM 原始分基础上调整可招募性权重：
    - 粉丝过多 → 负调整（技术名人往往不在找工作）
    - 近期活跃 → 正调整（最近有提交说明在活跃开发）
    ⚠ 关键约束：调整不得让 score 从 <60（备选/隐藏）越过 60（推荐）
    惩罚可以向下穿越（推荐→备选），但奖励不能向上穿越（备选→推荐）
    """
    s = c.score
    if s < 0:
        return s

    was_below_60 = s < 60   # 记录调整前的分层归属

    # ── 名人惩罚 ──────────────────────────────────────
    f = c.followers
    if f > 20_000:
        s -= 20
    elif f > 10_000:
        s -= 15
    elif f > 5_000:
        s -= 10
    elif f > 2_000:
        s -= 5

    # ── 活跃度奖惩 ────────────────────────────────────
    if c.last_active:
        try:
            from datetime import date
            idle_days = (date.today() - date.fromisoformat(c.last_active)).days
            if idle_days < 90:     s += 5   # 近3个月有提交
            elif idle_days < 180:  s += 3   # 近半年
            elif idle_days > 730:  s -= 8   # 超2年不活跃
        except Exception:
            pass

    result = max(0, min(100, s))

    # 分层锁定：奖励不得把备选/隐藏候选人推入推荐区
    if was_below_60 and result >= 60:
        result = 59

    return result


async def run_pipeline(job_id: str, jd_text: str):
    """核心异步流水线：解析JD → 抓取候选人 → 打分 → 存储结果"""
    try:
        anthropic_client = OpenAI(api_key=os.getenv("GROQ_API_KEY"), base_url="https://api.groq.com/openai/v1")
        scraper = GitHubScraper(token=os.getenv("GITHUB_TOKEN"))

        job_store.update_status(job_id, JobStatus.SEARCHING)
        # 用线程池运行同步 LLM 调用，避免阻塞事件循环
        parsed_jd = await asyncio.to_thread(parse_jd, jd_text, anthropic_client)

        profiles = await scraper.fetch_candidates(parsed_jd)
        job_store.update_progress(job_id, found=len(profiles), total=len(profiles))

        job_store.update_status(job_id, JobStatus.SCORING)

        # 串行打分，不加人工延迟
        # prompt 已压缩到 ~180 token，LLM响应 ~2s 是天然限流器
        # 30人 × 2s = ~60s，token消耗 30×180=5400 TPM，低于6000限制
        scored_count = 0

        async def score_one(profile):
            nonlocal scored_count
            result = None
            for attempt in range(3):
                try:
                    result = await asyncio.to_thread(score_candidate, profile, parsed_jd, anthropic_client)
                    break
                except Exception as e:
                    err_str = str(e)
                    if "429" in err_str and attempt < 2:
                        import re as _re
                        m = _re.search(r'try again in ([\d.]+)s', err_str)
                        wait = float(m.group(1)) + 1 if m else 10
                        print(f"Rate limited, waiting {wait:.1f}s for {profile.username}")
                        await asyncio.sleep(wait)
                    else:
                        print(f"Warning: scoring failed for {profile.username}: {err_str[:120]}")
                        break

            if result is None:
                result = ScoredCandidate(
                    username=profile.username, avatar_url=profile.avatar_url,
                    html_url=profile.html_url, bio=profile.bio,
                    location=profile.location, company=profile.company,
                    blog=profile.blog, public_repos=profile.public_repos,
                    followers=profile.followers, languages=profile.languages,
                    top_repos=profile.top_repos, last_active=profile.last_active,
                    score=-1, reason="评分失败，需人工审核",
                    strengths=[], gaps=[]
                )
            else:
                # ── 后端三道盖帽，按顺序应用 ────────────────────────────────
                # 1. 语言不符盖帽
                capped = _language_cap(result, parsed_jd)
                if capped != result.score:
                    primary_lang = next(iter(sorted(result.languages.items(), key=lambda x: -x[1])), ('?', 0))[0]
                    print(f"  [lang-cap] {result.username}: {result.score}→{capped} (primary={primary_lang})")
                    result.score = capped
                # 2. 核心技能缺失盖帽（strengths空 或 gaps含核心词 → 压到59以下）
                result.score = _skill_gap_cap(result, parsed_jd)

            job_store.add_result(job_id, result)
            scored_count += 1
            job_store.update_progress(job_id, scored=scored_count)

        for profile in profiles:
            await score_one(profile)

        # ── 打分完成后处理 ──────────────────────────────────────────────────
        # 分层阈值：推荐≥60 / 可备选40-59 / <40隐藏
        TIER_RECOMMEND = 60
        TIER_BACKUP    = 40
        MAX_RESULTS    = 15   # 推荐+备选总数上限

        job = job_store.get_job(job_id)
        if job:
            # 1. 可招募性调整（名人惩罚 + 活跃度加成）
            for c in job.results:
                if c.score >= 0:
                    c.score = _adjusted_score(c)

            # 2. 分层；次级键 bool(strengths) 确保同分时有证据者排前
            def _sort_key(c):
                return (c.score, bool(c.strengths))

            recommended = sorted([c for c in job.results if c.score >= TIER_RECOMMEND],
                                  key=_sort_key, reverse=True)
            backups     = sorted([c for c in job.results if TIER_BACKUP <= c.score < TIER_RECOMMEND],
                                  key=_sort_key, reverse=True)
            hidden      = [c for c in job.results if 0 <= c.score < TIER_BACKUP]
            failed      = [c for c in job.results if c.score < 0]

            print(f"[tier] recommended={len(recommended)}, backup={len(backups)}, "
                  f"hidden(score<{TIER_BACKUP})={len(hidden)}, failed={len(failed)}")

            # 3. 组装最终列表：推荐优先，备选补齐至 MAX_RESULTS
            #    若推荐为 0，全部用备选（保证不返回空 CSV）
            backup_slots = max(0, MAX_RESULTS - len(recommended))
            final = recommended + backups[:backup_slots]

            # 4. 兜底：推荐+备选都为空时，取所有有效候选按分数返回（不让 CSV 全空）
            if not final:
                all_valid = sorted([c for c in job.results if c.score >= 0],
                                   key=lambda x: x.score, reverse=True)
                final = all_valid[:10]
                print(f"[tier] fallback: returning top {len(final)} unfiltered candidates")
        else:
            final = []
        job_store.set_results(job_id, final)

    except Exception as e:
        job_store.set_error(job_id, str(e))
        raise

@app.post("/api/search")
async def post_search(req: SearchRequest, background_tasks: BackgroundTasks):
    job_id = job_store.create_job()
    background_tasks.add_task(run_pipeline, job_id, req.jd_text)
    return {"job_id": job_id}

def _candidate_tier(score: int) -> str:
    if score >= 60:  return "推荐"
    if score >= 40:  return "可备选"
    return "仅供参考"

def _format_candidate(c, rank):
    return {
        "rank": rank,
        "username": c.username,
        "avatar_url": c.avatar_url,
        "html_url": c.html_url,
        "bio": c.bio,
        "location": c.location,
        "company": c.company,
        "score": c.score,
        "tier": _candidate_tier(c.score),
        "reason": c.reason,
        "strengths": c.strengths,
        "gaps": c.gaps,
        "followers": c.followers,
        "public_repos": c.public_repos,
        "last_active": c.last_active
    }

@app.get("/api/status/{job_id}")
def get_status(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    # 实时返回已打分的候选人：展示 score >= 40（推荐+备选），隐藏 <40 的低分杂质
    live = sorted(
        [c for c in job.results if c.score >= 40],
        key=lambda x: x.score, reverse=True
    )
    return {
        "job_id": job.job_id,
        "status": job.status,
        "found": job.found,
        "scored": job.scored,
        "total": job.total,
        "error": job.error,
        "candidates": [_format_candidate(c, i+1) for i, c in enumerate(live)]
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
    writer.writerow(["排名", "匹配等级", "用户名", "分数", "匹配理由", "优势", "不足", "GitHub主页", "位置", "公司", "Followers"])
    for i, c in enumerate(job.results):
        writer.writerow([
            i + 1, _candidate_tier(c.score), c.username, c.score, c.reason,
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
