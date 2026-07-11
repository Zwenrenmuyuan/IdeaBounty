# Idea Bounty

商业点子收集器 MVP。当前后端已实现本地账号会话、个人投稿、AI 输入门禁、五维结构化评估、生产 Embedding、候选召回、LLM 查重和红包估值闭环，并提供登录用户可查询的脱敏点子摘要。管理员流程和前端仍待实现。

## 后端开发环境

后端使用 Python 3.12 和 [uv](https://docs.astral.sh/uv/) 管理 Python、虚拟环境与依赖。

```bash
docker compose up -d db
cd backend
uv sync
cp .env.example .env
uv run alembic upgrade head
```

PostgreSQL 容器首次启动时会创建 `idea_bounty` 开发数据库和独立的
`idea_bounty_test` 测试数据库。数据库配置包含本地开发默认值；真实投稿处理前必须在 `.env` 中填写 `AI_*` 和 `EMBEDDING_*` 配置。当前生产向量固定使用 `BAAI/bge-m3` 的 1024 维输出。

可以先用与生产契约相同的单次探测脚本验证模型服务，不会自动重试：

```bash
uv run python scripts/probe_ai_provider.py --show-output
```

查重判定复用相同的 `AI_*` 配置。固定九个中文案例会分别调用一次模型，检查
`duplicate / related / novel` 结构、关系组合和匹配候选，不会自动重试：

```bash
uv run python scripts/probe_duplicate_provider.py
uv run python scripts/probe_duplicate_provider.py --show-output
```

Embedding 服务使用独立的 `EMBEDDING_*` 配置。生产调用默认自动追加两次重试；能力探测脚本仍只进行显式请求，不自动重试。单次探测会批量检查向量结构和固定中文语义排序，比较稳定性时最多运行三次：

```bash
uv run python scripts/probe_embedding_provider.py
uv run python scripts/probe_embedding_provider.py --runs 3
```

生产配置要求 `EMBEDDING_DIMENSIONS=1024`。探测其他候选模型时可以临时不设置该项，让脚本报告实际维度；这不代表该模型可以直接写入当前数据库列。

## 启动 API

```bash
cd backend
uv run uvicorn idea_bounty.main:app --reload
```

启动后可以访问：

- 健康检查：<http://127.0.0.1:8000/api/health>
- API 文档：<http://127.0.0.1:8000/docs>

接受的投稿会同步完成 Embedding 和查重。精确原文命中直接判重，无候选直接判为
`novel`，存在语义候选时才调用生成模型。个人详情返回脱敏后的查重结论；登录用户可通过
`GET /api/ideas/{public_id}/summary` 核对匹配点子的公开摘要。
查重完成后，后端使用固定五维权重和 `Decimal` 二次曲线计算 `0–100` 商业分与 `0–100` 元估值；有效结论为 `duplicate` 时金额归零，客户端不能指定或修改金额。

## 后端质量检查

先确保根目录的 PostgreSQL 容器健康，再在 `backend` 目录分别运行：

```bash
docker compose ps
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests scripts/probe_ai_provider.py scripts/probe_embedding_provider.py scripts/probe_duplicate_provider.py
```
