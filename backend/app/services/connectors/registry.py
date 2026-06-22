"""Registry of available connectors (Story 1.4).

Keeps a single source of truth for which connector keys exist, so the API can
list them and validate the ``{connector}`` path segment without importing each
implementation everywhere.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.connectors.base import BaseConnector
from app.services.connectors.rest import RestConnector
from app.services.connectors.sql import SqlConnector


@dataclass(frozen=True)
class ConnectorInfo:
    key: str
    title: str
    description: str


CONNECTOR_CLASSES: dict[str, type[BaseConnector]] = {
    SqlConnector.key: SqlConnector,
    RestConnector.key: RestConnector,
}

CONNECTORS: list[ConnectorInfo] = [
    ConnectorInfo(
        key="sql",
        title="SQL Database",
        description="Import an event log from any SQL database (PostgreSQL, "
        "MySQL, SQLite, ...) via a connection URL and a read-only SELECT query.",
    ),
    ConnectorInfo(
        key="rest",
        title="REST API",
        description="Import an event log from a JSON REST API; map nested fields "
        "via dot-paths and point at the records array with records_path.",
    ),
]


def get_connector(key: str) -> ConnectorInfo:
    for info in CONNECTORS:
        if info.key == key:
            return info
    raise KeyError(key)


def build_connector(key: str) -> type[BaseConnector]:
    """Return the connector class for a key (raises KeyError if unknown)."""
    return CONNECTOR_CLASSES[key]
