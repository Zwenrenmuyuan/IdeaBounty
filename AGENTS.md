# Repository Guidelines

## Project Structure & Module Organization

Backend code lives in `backend/src/idea_bounty/`, migrations in `backend/alembic/`, and tests in `backend/tests/`. Frontend code lives in `frontend/src/`; use `pages/` for routes, `api/` for FastAPI calls, `components/` for UI, and `types/` for public contracts. Root `compose.yaml` starts PostgreSQL. Treat `技术方案.md` as the source. The backend loop and responsive user frontend are implemented; the administrator frontend is not.

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

Run frontend commands from `frontend/`:

```bash
pnpm install
pnpm dev
pnpm lint
pnpm build
```

## Coding Style & Naming Conventions

Use Python 3.12, four-space indentation, and 100-character lines; Ruff controls formatting. TypeScript components use `PascalCase`, functions and modules use `camelCase` or kebab-case filenames following the existing frontend. Keep identifiers in English and comments/docstrings in concise Chinese. Prefer Tailwind responsive utilities over separate desktop/mobile components.

## Testing Guidelines

Use pytest and FastAPI TestClient. Name files `test_<feature>.py` and tests `test_<expected_behavior>`. Database fixtures reject names without `_test`; never target `idea_bounty`. Cover validation, constraints, migrations, authorization, idempotency and pipeline transitions. Automated AI and Embedding calls must use fakes or HTTP Mocks. Frontend changes must pass `pnpm lint` and `pnpm build`; manually check affected desktop and mobile layouts until browser tests are added.

## Database & Migration Rules

Never call `Base.metadata.create_all()`. Add an Alembic revision for every schema change; never rewrite a committed migration. Keep ORM metadata aligned and run migration round-trips plus `alembic check`. Enforce invariants such as one session per user, valid states, retry limits, and `(user_id, submission_key)` uniqueness in PostgreSQL.

## Commit & Pull Request Guidelines

Use Conventional Commits, for example `feat(backend): 实现点子投稿基础闭环`. Keep one reviewed milestone per commit. Pull requests describe the outcome, design choices, test evidence, and migration/configuration impact; include screenshots for UI changes.

## Security & Change Scope

Copy `backend/.env.example` to `.env`; never commit credentials, raw tokens, or machine paths. Compose credentials are local-only. Derive ownership from the authenticated user; never accept client-provided `user_id`. Do not expose password/token hashes, internal IDs, or content hashes.

Implement only the approved milestone. Explain scope before editing, leave changes uncommitted unless asked, and show the diff and checks afterward.
