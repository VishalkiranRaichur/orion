# Repository Guidelines

## Project Structure & Module Organization

The Next.js 15 frontend lives in `apps/web/src`: routes are under `app/`, reusable UI under `components/`, and helpers under `lib/`. The FastAPI backend lives in `apps/api/app`, organized into `routers/`, `services/`, `models/`, and `schemas/`; tests belong in `apps/api/tests/`. Celery code is in `workers/celery/`. PostgreSQL, Redis, and MinIO configuration is maintained in `infra/`, while CI is in `.github/workflows/ci.yml`.

## Build, Test, and Development Commands

- `make install` creates `apps/api/.venv` and installs both Python and npm dependencies.
- `make infra-up` / `make infra-down` starts or stops PostgreSQL, Redis, and MinIO with Docker Compose.
- `make dev-api` runs FastAPI with reload at `http://localhost:8000`.
- `make dev` runs Next.js at `http://localhost:3000`.
- `npm run build` builds the web workspace for production.
- `cd apps/api && .venv/bin/pytest -q` runs the API test suite.
- `cd apps/api && .venv/bin/ruff check app tests` checks Python style; `npm run lint` checks the frontend.

## Coding Style & Naming Conventions

Use Python 3.11, four-space indentation, type annotations, and a 100-character line limit. Ruff enforces `E`, `F`, `I`, and `UP` rules; use snake_case for modules and functions and PascalCase for classes. TypeScript is strict. Follow the existing two-space indentation, semicolons, and double quotes; name React components in PascalCase and helpers in camelCase. Prefer the `@/` alias for frontend imports. Keep route handlers thin and place business logic in backend services.

## Testing Guidelines

Pytest and `pytest-asyncio` are configured in `apps/api/pyproject.toml`; tests are discovered from `apps/api/tests/`. Name files `test_*.py` and tests `test_<behavior>`. Cover new endpoints, error paths, and service behavior. Start required infrastructure and configure `apps/api/.env` before integration tests. There is no frontend test runner, so lint and production build are required for UI changes.

## Commit & Pull Request Guidelines

History favors short, imperative summaries such as `Add semantic search...` and `Fix API lint issues`; Conventional Commit messages such as `feat: ...` also appear. Keep commits focused. Pull requests should explain the change and verification, link issues, call out environment or schema changes, and include screenshots for visible UI updates. Ensure CI's lint, test, and build checks pass locally.

## Security & Configuration

Copy the provided `.env.example` files and keep real Clerk, database, S3, and other credentials out of Git. Never commit uploaded documents or generated local service data.
