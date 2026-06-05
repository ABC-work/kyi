# Talent Hunter — 设计文档

**日期：** 2026-06-06  
**阶段：** 内部 Demo  
**作者：** oyzh888

---

## 1. 产品定位

一个面向企业的 AI 人才猎手工具。企业粘贴岗位描述（JD），系统自动从 GitHub 抓取候选人数据，通过 LLM 智能打分并输出排行榜，帮助企业快速筛选符合需求的技术人才。

**当前阶段目标：** 内部 Demo，验证核心链路可行性，不对外部署。

---

## 2. 核心数据流

```
用户粘贴 JD
     ↓
LLM 解析 JD → 提取技能关键词、编程语言、年限、领域
     ↓
GitHub API 搜索 → 返回候选用户列表（最多 30 人）
     ↓
逐个抓取候选人详情（bio、仓库、语言分布、活跃度）
     ↓
LLM 对每个候选人打分（0-100）+ 生成匹配理由
     ↓
前端展示排行榜，支持导出 CSV
```

整个流程异步执行，前端轮询进度直到完成。

---

## 3. 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 后端 | Python + FastAPI | 轻量，异步友好 |
| 前端 | 单页 HTML + Vanilla JS | 无框架，零依赖 |
| LLM | Anthropic Claude API | 解析 JD + 候选人打分 |
| 数据源 | GitHub REST API | 官方 API，带 Token 每小时 5000 次 |
| 存储 | 内存（Python 字典） | Demo 阶段无需数据库 |

---

## 4. 项目结构

```
talent-hunter/
├── backend/
│   ├── main.py              # FastAPI 入口，路由定义
│   ├── jd_parser.py         # LLM 解析 JD，提取搜索参数
│   ├── github_scraper.py    # GitHub API 抓取候选人信息
│   ├── scorer.py            # LLM 给候选人打分
│   ├── job_store.py         # 内存存储 job 状态和结果
│   └── requirements.txt
├── frontend/
│   └── index.html           # 单页应用（含 CSS + JS）
└── .env                     # ANTHROPIC_API_KEY, GITHUB_TOKEN
```

---

## 5. API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/search` | 接收 JD 文本，返回 `job_id`，异步开始处理 |
| GET  | `/api/status/{job_id}` | 返回当前进度（已找到 N 人 / 正在打分 X/N） |
| GET  | `/api/results/{job_id}` | 返回打分完毕的候选人排行榜 |
| GET  | `/api/export/{job_id}` | 下载候选人列表 CSV |

---

## 6. GitHub 抓取策略

**第一步：构建搜索查询**

LLM 解析 JD 后输出结构化参数，用于 GitHub 用户搜索：

```
示例 JD: "需要 Go 后端工程师，熟悉微服务、Kubernetes，3年以上经验"

→ 搜索语言: go
→ 关键词: kubernetes microservice
→ GitHub API: GET /search/users?q=kubernetes+microservice+language:go+followers:>10
```

**第二步：抓取候选人详情**

每个候选人抓取以下数据：
- 基本信息：bio、location、公司、博客链接
- 仓库语言分布（主要编程语言及占比）
- 最热仓库 Top 5（star 数、描述、topics）
- 账号活跃度（最近 push 时间、public repos 数量）

**限制说明：**
- GitHub API 带 Token 每小时 5000 次请求，Demo 完全够用
- 每次搜索最多返回 30 个候选人

---

## 7. LLM Prompt 设计

### 7.1 第一次调用——解析 JD

```
你是一个 HR 助手，请从以下 JD 中提取关键信息，以 JSON 格式输出：
{
  "required_skills": [...],    // 必须技能
  "bonus_skills": [...],       // 加分技能
  "languages": [...],          // 编程语言
  "min_years": 3,              // 最低工作年限
  "search_keywords": [...]     // 用于 GitHub 搜索的关键词
}

JD: {jd_text}
```

### 7.2 第二次调用——候选人打分

```
你是一个专业猎头，根据岗位要求给候选人打分（0-100）并说明理由。

岗位要求：{parsed_jd}

候选人信息：
- Bio: {bio}
- 主要编程语言: {languages}
- 代表项目（Top 5）: {top_repos}
- 活跃度: {activity}

请以 JSON 格式输出：
{
  "score": 85,
  "reason": "总体匹配度高，...",
  "strengths": ["精通 Go", "有 K8s 实战经验"],
  "gaps": ["缺少金融领域背景"]
}
```

---

## 8. 前端设计

单页应用，三个状态：

1. **输入态** — 大文本框粘贴 JD + 提交按钮
2. **处理态** — 进度条 + 状态文字（"已找到 23 人，正在打分 12/23..."）
3. **结果态** — 候选人卡片排行榜，每张卡片显示：
   - GitHub 头像 + 姓名 + 主页链接
   - 匹配分数（0-100，带颜色标识）
   - 匹配理由（一句话）
   - 优势标签 + 不足标签
   - 导出 CSV 按钮

---

## 9. 启动方式

```bash
# 1. 配置环境变量
cp .env.example .env
# 填入 ANTHROPIC_API_KEY 和 GITHUB_TOKEN

# 2. 安装依赖
cd backend
pip install -r requirements.txt

# 3. 启动服务
uvicorn main:app --reload

# 4. 浏览器访问
open http://localhost:8000
```

**核心依赖：**
```
fastapi
uvicorn
anthropic
httpx
python-dotenv
```

---

## 10. 设计原则

- **无数据库** — 内存存储，降低 Demo 复杂度
- **无前端框架** — 一个 HTML 文件搞定，便于快速迭代
- **两次 LLM 调用** — 成本可控，逻辑清晰
- **GitHub 官方 API** — 稳定、不封号、数据结构化
- **异步处理** — 抓取和打分耗时较长，不阻塞前端

---

## 11. 后续扩展方向（当前不做）

- 接入 LinkedIn、Boss直聘等更多数据源
- 候选人数据持久化（SQLite → PostgreSQL）
- 多岗位管理、历史搜索记录
- 企业账号系统，SaaS 化部署
