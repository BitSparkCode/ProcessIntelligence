# Process Intelligence

Open-source process &amp; task mining tool (MVP). Import event logs, discover and
visualize processes, and analyze performance. Built with **FastAPI + PM4Py**
(backend), **React + TypeScript** (frontend) and **PostgreSQL** (storage).

> This repository is being built incrementally, sprint by sprint, against the MVP
> backlog. **Sprint 1** delivers the foundation: the internal event-log data model,
> CSV import with column mapping, and a one-command Docker Compose deployment.

## Quickstart (Docker Compose)

Requirements: Docker + Docker Compose.

```bash
cp .env.example .env        # adjust secrets/ports as needed
docker compose up --build
```

Then open:

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

Default ports (overridable via `.env`): frontend `3000`, backend `8000`,
PostgreSQL `5432`.

## Features in this sprint

| Story | Description |
| ----- | ----------- |
| 1.3 | Internal event-log data model (Logs, Cases, Events, Activities, Resources, key-value Attributes) on PostgreSQL with Alembic migrations |
| 1.1 | CSV import with a column-mapping UI, preview (first 20 rows), validation (missing columns, bad timestamps, empty case IDs), streaming parser for large files |
| 5.1 | `docker compose up` starts backend + frontend + PostgreSQL; `/health` endpoint; secrets via environment variables |

## Importing a CSV

1. Open the frontend and choose a `.csv` file.
2. Map the **Case ID**, **Activity** and **Timestamp** columns (Resource, cost and
   lifecycle are optional). Sensible defaults are guessed from the header.
3. Review the preview and click **Import**. The log appears in the table below.

A sample log lives at [`samples/sample_log.csv`](samples/sample_log.csv).

## Local development

### Backend

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg2://pi:pi@localhost:5432/process_intelligence"
alembic upgrade head
uvicorn app.main:app --reload
```

Run checks:

```bash
ruff check .
mypy app
pytest
```

### Frontend

```bash
cd frontend
npm install
npm run dev        # http://localhost:5173 (proxies /api to localhost:8000)
```

## Architecture

```
frontend (React + Vite, nginx)  ──/api──▶  backend (FastAPI)  ──▶  PostgreSQL
                                              │
                                              └─ PM4Py mining engine (later sprints)
```

The internal event-log schema is import-source agnostic: every downstream mining
feature (discovery, performance, conformance) reads from it, regardless of whether
data came from CSV, XES, a database adapter or a workflow engine.
