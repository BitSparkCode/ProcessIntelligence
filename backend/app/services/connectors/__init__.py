"""Pluggable data-source connector framework (Story 1.4).

New data sources (databases, REST APIs, workflow engines) plug in by
implementing :class:`~app.services.connectors.base.BaseConnector` without
touching the core import/storage code. Two reference connectors ship:

* :class:`~app.services.connectors.sql.SqlConnector` — any SQL database via a
  SQLAlchemy URL + query.
* :class:`~app.services.connectors.rest.RestConnector` — any REST/JSON API.

See ``docs/connectors.md`` for a "build your own connector" guide.
"""

from __future__ import annotations

from app.services.connectors.base import (
    BaseConnector,
    ConnectorError,
    ConnectorResult,
)
from app.services.connectors.registry import CONNECTORS, build_connector, get_connector
from app.services.connectors.rest import RestConnector, RestConnectorConfig
from app.services.connectors.sql import SqlConnector, SqlConnectorConfig

__all__ = [
    "BaseConnector",
    "ConnectorError",
    "ConnectorResult",
    "SqlConnector",
    "SqlConnectorConfig",
    "RestConnector",
    "RestConnectorConfig",
    "CONNECTORS",
    "build_connector",
    "get_connector",
]
