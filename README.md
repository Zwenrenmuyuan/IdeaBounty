# Idea Bounty

商业点子收集器 MVP。当前仓库只建立了后端工程基线，业务功能尚未实现。

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
`idea_bounty_test` 测试数据库。`.env` 中的配置均有适合本地开发的默认值；复制配置文件是可选步骤。

## 启动 API

```bash
cd backend
uv run uvicorn idea_bounty.main:app --reload
```

启动后可以访问：

- 健康检查：<http://127.0.0.1:8000/api/health>
- API 文档：<http://127.0.0.1:8000/docs>

## 后端质量检查

先确保根目录的 PostgreSQL 容器健康，再在 `backend` 目录分别运行：

```bash
docker compose ps
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
```
