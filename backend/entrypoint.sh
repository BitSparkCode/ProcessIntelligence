#!/usr/bin/env bash
set -euo pipefail

echo "Waiting for database..."
python - <<'PY'
import os
import time

from sqlalchemy import create_engine, text

url = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg2://pi:pi@db:5432/process_intelligence",
)
for attempt in range(60):
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("Database is ready.")
        break
    except Exception as exc:  # noqa: BLE001
        print(f"  db not ready ({attempt + 1}/60): {exc}")
        time.sleep(2)
else:
    raise SystemExit("Database did not become ready in time")
PY

echo "Running migrations..."
alembic upgrade head

echo "Starting API server..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
