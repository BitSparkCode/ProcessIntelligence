# Contributing to Process Intelligence

Thanks for your interest in contributing! This project is an open-source,
AI-first process & task mining platform. Contributions of all kinds are welcome:
bug reports, features, docs, and connectors.

## Ways to contribute

- **Report a bug** — open a [Bug report](https://github.com/BitSparkCode/ProcessIntelligence/issues/new?template=bug_report.md).
- **Request a feature** — open a [Feature request](https://github.com/BitSparkCode/ProcessIntelligence/issues/new?template=feature_request.md).
- **Build a connector** — see the [Build your own connector](docs/connectors.md) guide.
- **Send a pull request** — see the workflow below.

## Development setup

Requirements: Docker + Docker Compose (for the full stack), or Python 3.12 and
Node 20 to run the backend and frontend directly.

```bash
# Full stack
cp .env.example .env
docker compose up --build

# Backend only (from backend/)
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload

# Frontend only (from frontend/)
npm install
npm run dev
```

See the [README](README.md#architecture) for the architecture overview.

## Code style

These are enforced in CI; please run them locally before pushing.

### Backend (Python)

- Formatting & linting: **ruff** (`ruff check .` and `ruff format .` from `backend/`).
- Types: **mypy** (`mypy app`). New code should be fully typed; avoid `Any`,
  `getattr`/`setattr` and other dynamic escape hatches.
- Tests: **pytest** (`pytest`). Add tests for new behavior; pure logic should be
  unit-testable without a database or HTTP layer where possible.
- Line length: 100. Imports sorted by ruff (isort rules).

### Frontend (TypeScript / React)

- Linting: **eslint** (`npm run lint`).
- Types: **tsc** (`npm run typecheck`). No `any`; prefer precise types.
- Build must pass: `npm run build`.
- Follow the existing component conventions (functional components, hooks,
  colocated styles in `src/index.css`).

## Commit & PR workflow

1. **Fork** the repo and create a branch off `main`
   (`git checkout -b feat/short-description`).
2. Make focused changes. Keep PRs small and scoped to one logical change.
3. Run the full check suite locally:
   ```bash
   cd backend && ruff check . && mypy app && pytest
   cd ../frontend && npm run lint && npm run typecheck && npm run build
   ```
4. **Open a pull request** against `main` and fill in the PR template. Link the
   issue it closes (`Closes #123`).
5. CI (GitHub Actions) runs linting + type checks + tests on every PR. All checks
   must be green before review.
6. A maintainer reviews; address feedback with follow-up commits (don't
   force-push over review history unless asked).

## Reporting security issues

Please do **not** open public issues for security vulnerabilities. Instead, email
the maintainers (see the repository owner's profile) with details so we can
address it responsibly.

## License

By contributing, you agree that your contributions will be licensed under the
[Apache License 2.0](LICENSE).
