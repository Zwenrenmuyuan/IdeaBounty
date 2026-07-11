# Repository Guidelines

## Project Structure & Module Organization

Backend code lives in `backend/src/idea_bounty/`: `api/` exposes FastAPI routes and dependencies, `services/` owns transactions and deterministic bounty rules, `schemas/` defines Pydantic boundaries, `models/` contains SQLAlchemy entities, `ai/` owns generation-model calls, `embedding/` owns vector configuration and provider calls, and `db/` owns persistence. Migrations are in `backend/alembic/`; tests are in `backend/tests/`. Root `compose.yaml` starts PostgreSQL using `infra/postgres/`. Treat `技术方案.md` as the approved architecture source. Production vector generation, candidate recall, LLM deduplication, public summaries, and bounty estimation are implemented; admin review, simulated payout, and frontend are not.

## Build, Test, and Development Commands

Start PostgreSQL from the root; run Python commands from `backend/`:

```bash
docker compose up -d db
uv sync
uv run alembic upgrade head
uv run uvicorn idea_bounty.main:app --reload
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy src tests
uv run alembic check
```

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, and 100-character lines. Ruff controls formatting. Use `snake_case` for functions/modules, `PascalCase` for classes, and `UPPER_CASE` for constants. Keep identifiers in English and comments/docstrings in concise Chinese. Public functions require full type annotations.

## Testing Guidelines

Use pytest and FastAPI TestClient. Name files `test_<feature>.py` and tests `test_<expected_behavior>`. Database fixtures reject names without `_test`; never target `idea_bounty`. Cover success, validation failure, constraints, migrations, and authorization. Authentication tests include Cookie expiry/revocation and disabled users. Idea tests include ownership isolation, idempotency, AI/Embedding/deduplication transitions, retries, candidate filtering, and public-summary redaction. Update cleanup fixtures when adding tables; all automated generation-model and Embedding calls must use a fake provider or HTTP Mock.

## Database & Migration Rules

Never call `Base.metadata.create_all()`. Add an Alembic revision for every schema change; never rewrite a committed migration. Keep ORM metadata aligned and run migration round-trips plus `alembic check`. Enforce invariants such as one session per user, valid states, retry limits, and `(user_id, submission_key)` uniqueness in PostgreSQL.

## Commit & Pull Request Guidelines

Use Conventional Commits, for example `feat(backend): 实现点子投稿基础闭环`. Keep one reviewed milestone per commit. Pull requests describe the outcome, design choices, test evidence, and migration/configuration impact; include screenshots for UI changes.

## Security & Change Scope

Copy `backend/.env.example` to `.env`; never commit credentials, raw tokens, or machine paths. Compose credentials are local-only. Derive ownership from the authenticated user; never accept client-provided `user_id`. Do not expose password/token hashes, internal IDs, or content hashes.

Implement only the approved milestone. Explain files and acceptance criteria before editing, leave changes uncommitted unless asked, show the diff and checks afterward, and never continue automatically into later business sections.
