# Process Intelligence

[![CI](https://github.com/BitSparkCode/ProcessIntelligence/actions/workflows/ci.yml/badge.svg)](https://github.com/BitSparkCode/ProcessIntelligence/actions/workflows/ci.yml)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

Open-source, **AI-first** process &amp; task mining tool (MVP). Import event logs,
discover and visualize processes on an n8n-style interactive canvas, and analyze
performance. Built with **FastAPI + PM4Py** (backend), **React + TypeScript +
React Flow** (frontend) and **PostgreSQL** (storage).

> This repository is being built incrementally, sprint by sprint, against the MVP
> backlog: **Sprint 1** the foundation (event-log model, CSV import, Docker
> Compose), **Sprint 2** multi-tenant auth + AI-assisted data linking + Heuristic
> Miner + interactive graph, **Sprint 3** Inductive Miner + BPMN export + variants
> + throughput, **Sprint 4** a pluggable connector framework, bottleneck detection
> and open-source scaffolding.

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

### Sprint 3 — inductive miner, variants & performance

| Story | Description |
| ----- | ----------- |
| 2.2 | Inductive Miner discovery (sound model) via PM4Py, with BPMN 2.0 XML export (`GET /api/discovery/{id}/bpmn`) and a Heuristic/Inductive toggle in the graph UI |
| 2.4 | Variant analysis: distinct case paths ranked by frequency with volume share (%) and average throughput; Top-N / min-frequency filters; click a variant to highlight its path on the graph |
| 3.1 | Throughput dashboard: avg/median/min/max case duration KPIs, per-activity and transition waiting times, a throughput-time histogram, and a time-window filter (30/90/365 days) |

### Sprint 4 — connectors, bottlenecks & OSS

| Story | Description |
| ----- | ----------- |
| 1.4 | Pluggable **connector framework** (`BaseConnector` + `validate`/`extract`/`transform`): import event logs directly from any SQL database or JSON REST API (`POST /api/connectors/{sql,rest}/import`). See the [build-your-own-connector guide](docs/connectors.md) |
| 3.2 | **Bottleneck detection**: flags transitions/activities whose mean waiting time exceeds a configurable percentile (default 90th), highlights them in red on the graph, and exports a Top-N text summary (`POST /api/analysis/{id}/bottlenecks`) |
| 5.3 | Open-source scaffolding: Apache 2.0 [LICENSE](LICENSE), [CONTRIBUTING](CONTRIBUTING.md) guide, issue/PR templates, and CI that runs lint + types + tests on every PR |

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

## Importing from a database or REST API

Besides CSV, logs can be imported through the connector framework. Example (SQL):

```bash
curl -X POST http://localhost:8000/api/connectors/sql/import \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "name": "orders",
    "connection_url": "postgresql+psycopg2://user:pw@host:5432/db",
    "query": "SELECT order_id, step, changed_at, agent FROM order_events",
    "mapping": {"case_id": "order_id", "activity": "step", "timestamp": "changed_at", "resource": "agent"}
  }'
```

`GET /api/connectors` lists the available connectors. See the
[build-your-own-connector guide](docs/connectors.md) to add your own.

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
   React Flow canvas, panels                  │
                                              ├─ services/
                                              │    csv_import, log_storage
                                              │    discovery, inductive (PM4Py)
                                              │    variants, performance, bottleneck
                                              │    connectors/ (sql, rest, ...)
                                              │    ai/ (provider-agnostic LLM)
                                              └─ PM4Py mining engine
```

- **`backend/app/api/routes`** — FastAPI routers (`auth`, `logs`, `discovery`,
  `analysis`, `connectors`, `health`).
- **`backend/app/services`** — the domain logic; each feature is a small,
  unit-testable module that reads from the internal event-log schema.
- **`backend/app/models` / `schemas`** — SQLAlchemy models and Pydantic
  request/response contracts.
- **`frontend/src`** — the React app; `ProcessGraph` hosts the canvas and the
  Variants / Performance / Bottlenecks side panels.

The internal event-log schema is import-source agnostic: every downstream mining
feature (discovery, performance, conformance) reads from it, regardless of whether
data came from CSV, a database, a REST API or a workflow engine. New sources plug
in via the [connector framework](docs/connectors.md) without touching core code.

## Contributing

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) for the dev
setup, code style, and PR workflow, and the
[connector guide](docs/connectors.md) to add a new data source. The project is
licensed under [Apache 2.0](LICENSE).
