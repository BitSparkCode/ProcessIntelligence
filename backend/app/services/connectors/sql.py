"""Reference connector 1: generic SQL database (Story 1.4).

Reads an event stream from any database SQLAlchemy can reach (PostgreSQL,
MySQL, SQLite, ...) by running a user-supplied ``SELECT`` and mapping the
result columns onto the internal event-log fields.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.schemas.event_log import ColumnMapping
from app.services.connectors.base import BaseConnector, ConnectorError

# Read-only by intent: reject statements that could mutate the source.
_FORBIDDEN = (
    "insert ",
    "update ",
    "delete ",
    "drop ",
    "alter ",
    "truncate ",
    "create ",
    "grant ",
    "revoke ",
)


@dataclass
class SqlConnectorConfig:
    connection_url: str
    query: str
    mapping: ColumnMapping
    # Upper bound so a runaway query can't exhaust memory.
    max_rows: int = 1_000_000


class SqlConnector(BaseConnector[dict]):
    key = "sql"
    source_name = "sql"

    def __init__(self, config: SqlConnectorConfig) -> None:
        super().__init__(config.mapping)
        self.config = config

    def validate(self) -> None:
        if not self.config.connection_url.strip():
            raise ConnectorError("connection_url is required")
        query = self.config.query.strip()
        if not query:
            raise ConnectorError("query is required")
        lowered = f" {query.lower()} "
        if any(tok in lowered for tok in _FORBIDDEN):
            raise ConnectorError("Only read-only SELECT queries are allowed")
        if ";" in query.rstrip(";"):
            raise ConnectorError("Multiple statements are not allowed")

    def extract(self) -> Iterable[dict]:
        try:
            engine = create_engine(self.config.connection_url)
        except SQLAlchemyError as exc:  # invalid URL / missing driver
            raise ConnectorError(f"Cannot connect: {exc}") from exc
        try:
            with engine.connect() as conn:
                result = conn.execution_options(stream_results=True).execute(
                    text(self.config.query)
                )
                for i, row in enumerate(result.mappings()):
                    if i >= self.config.max_rows:
                        break
                    yield dict(row)
        except SQLAlchemyError as exc:
            raise ConnectorError(f"Query failed: {exc}") from exc
        finally:
            engine.dispose()
