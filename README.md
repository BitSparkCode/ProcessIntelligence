# Process Intelligence

Open-source, **AI-first** process &amp; task mining tool (MVP). Import event logs,
discover and visualize processes on an n8n-style interactive canvas, and analyze
performance. Built with **FastAPI + PM4Py** (backend), **React + TypeScript +
React Flow** (frontend) and **PostgreSQL** (storage).

> This repository is being built incrementally, sprint by sprint, against the MVP
> backlog. **Sprint 1** delivered the foundation (event-log model, CSV import,
> Docker Compose). **Sprint 2** adds multi-tenant auth, AI-assisted data linking,
> Heuristic Miner discovery, and the next-gen interactive process graph.

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

## Features

### Sprint 1 — foundation

| Story | Description |
| ----- | ----------- |
| 1.3 | Internal event-log data model (Logs, Cases, Events, Activities, Resources, key-value Attributes) on PostgreSQL with Alembic migrations |
| 1.1 | CSV import with a column-mapping UI, preview (first 20 rows), validation, streaming parser for large files |
| 5.1 | `docker compose up` starts backend + frontend + PostgreSQL; `/health` endpoint; secrets via environment variables |

### Sprint 2 — discovery, auth & AI

| Story | Description |
| ----- | ----------- |
| 5.2 | JWT auth (register/login), multi-tenant workspace isolation — every log is scoped to a workspace; cross-tenant access returns 404 (IDOR-safe) |
| 6.3 | Provider-agnostic LLM foundation (OpenAI / Anthropic / disabled) with structured-output validation and a safe deterministic fallback |
| 6.1 | AI-assisted data linking: the importer suggests a column mapping (LLM when configured, heuristic otherwise) |
| 2.1 | Heuristic Miner discovery via a directly-follows graph with dependency measure, frequencies, durations and configurable thresholds |
| 2.3 | n8n-style interactive process graph (React Flow): pannable/zoomable canvas, rich activity cards with inline KPIs, frequency/time-weighted edges, minimap, node detail panel |

### AI configuration

The product is AI-first but **runs fully offline by default**. With
`AI_PROVIDER=none` (the default), data linking uses deterministic heuristics. Set
`AI_PROVIDER=openai` (or `anthropic`) and the matching `OPENAI_API_KEY` /
`ANTHROPIC_API_KEY` to enable live AI suggestions. See `.env.example`.

## Importing a CSV

1. Register or sign in (each account gets its own isolated workspace).
2. Choose a `.csv` file. The importer proposes a column mapping (AI or heuristic).
3. Adjust the **Case ID**, **Activity** and **Timestamp** columns if needed
   (Resource, cost and lifecycle are optional), review the preview and **Import**.
4. Click **Discover** on a log to open the interactive process graph.

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
