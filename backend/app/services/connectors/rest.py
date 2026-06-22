"""Reference connector 2: REST / JSON API (Story 1.4).

Fetches a JSON document from an HTTP endpoint, walks an optional dot-path to the
array of records inside it, and maps each record's fields onto the event-log
schema. Field mapping accepts dot-paths too, so nested JSON works without
pre-flattening.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

import httpx

from app.schemas.event_log import ColumnMapping
from app.services.connectors.base import BaseConnector, ConnectorError


@dataclass
class RestConnectorConfig:
    url: str
    mapping: ColumnMapping
    method: str = "GET"
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    json_body: dict | None = None
    # Dot-path to the list of records, e.g. "data.events". Empty = response is the list.
    records_path: str = ""
    timeout_seconds: float = 30.0


def _dig(obj: object, path: str) -> object:
    """Follow a dot-path through nested dicts; return None if any hop misses."""
    if not path:
        return obj
    current = obj
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def _flatten(record: dict, mapping: ColumnMapping) -> dict:
    """Resolve each mapped field (which may be a dot-path) to a flat value."""
    fields = [
        mapping.case_id,
        mapping.activity,
        mapping.timestamp,
        mapping.resource,
        mapping.cost,
        mapping.lifecycle,
    ]
    flat: dict[str, object] = {}
    for key in fields:
        if key:
            flat[key] = _dig(record, key)
    return flat


class RestConnector(BaseConnector[dict]):
    key = "rest"
    source_name = "rest"

    def __init__(self, config: RestConnectorConfig) -> None:
        super().__init__(config.mapping)
        self.config = config

    def validate(self) -> None:
        if not self.config.url.strip():
            raise ConnectorError("url is required")
        if not self.config.url.lower().startswith(("http://", "https://")):
            raise ConnectorError("url must be http(s)")
        if self.config.method.upper() not in ("GET", "POST"):
            raise ConnectorError("method must be GET or POST")

    def extract(self) -> Iterable[dict]:
        try:
            response = httpx.request(
                self.config.method.upper(),
                self.config.url,
                headers=self.config.headers,
                params=self.config.params,
                json=self.config.json_body,
                timeout=self.config.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise ConnectorError(f"Request failed: {exc}") from exc
        except ValueError as exc:  # invalid JSON
            raise ConnectorError(f"Response is not valid JSON: {exc}") from exc

        records = _dig(payload, self.config.records_path)
        if not isinstance(records, list):
            raise ConnectorError(
                f"records_path '{self.config.records_path}' did not resolve to a list"
            )
        for record in records:
            if isinstance(record, dict):
                yield _flatten(record, self.config.mapping)
