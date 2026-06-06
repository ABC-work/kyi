# Talent Hunter 🎯

AI 驱动的开发者人才搜索工具。粘贴岗位描述，自动从 GitHub 筛选匹配候选人并评分；或直接输入 GitHub 用户名查看技术画像。

## 功能

- **搜职位**：粘贴 JD → AI 解析技能要求 → GitHub 实时搜索 → LLM 逐人评分 → 分层展示（推荐 / 可备选）→ CSV 导出
- **查人**：输入 GitHub 用户名或真实姓名 → 查看技术画像（语言分布、代表项目、活跃度）→ 可选对照 JD 出匹配分

## 快速开始

### 1. 获取 API Key

| 服务 | 用途 | 获取地址 |
|------|------|---------|
| Groq | LLM 评分（免费） | https://console.groq.com/keys |
| GitHub | 搜索开发者（免费） | https://github.com/settings/tokens/new → 勾选 `public_repo` |

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入你的 key：
# GROQ_API_KEY=gsk_...
# GITHUB_TOKEN=ghp_...
```

### 3. 安装依赖并启动

```bash
pip install -r requirements.txt
cd backend
uvicorn main:app --reload --port 8000
```

打开浏览器：http://localhost:8000

## 技术栈

- **后端**：FastAPI + httpx + Groq API（llama-3.1-8b-instant）
- **前端**：原生 HTML/CSS/JS，无框架依赖
- **搜索**：GitHub Search API（仓库 topic/语言搜索 → 按 owner 聚合）

## 运行测试

```bash
cd backend
python3 -m pytest -v
```

## 目录结构

```
talent-hunter/
├── backend/
│   ├── main.py          # FastAPI 路由 + 评分流水线
│   ├── github_scraper.py # GitHub 搜索 + 抓取候选人
│   ├── jd_parser.py     # JD 解析（Groq LLM）
│   ├── scorer.py        # 候选人 LLM 评分
│   ├── models.py        # 数据模型
│   ├── job_store.py     # 内存任务存储
│   └── tests/           # 单元测试
├── frontend/
│   └── index.html       # 单页前端
├── .env.example         # 环境变量模板
└── requirements.txt
```

## 注意事项

- Groq 免费额度：6,000 TPM，30 人评分约需 1 分钟
- GitHub API 未认证：60 次/小时；认证后：5,000 次/小时（**强烈建议配置 token**）
- 搜索结果质量依赖 JD 中的框架关键词，建议明确写出框架名（如 React、Next.js、Kubernetes）
