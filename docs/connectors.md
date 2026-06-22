# Build your own connector

Process Intelligence ingests event logs through a small **connector framework**
(Story 1.4). A connector knows how to pull raw records from *one* kind of source
(a database, a REST API, a workflow engine, a file format, ...) and map them onto
the internal event-log schema. The rest of the platform — storage, discovery,
variants, performance — never needs to know where the data came from.

Two reference connectors ship in the box:

| Key    | Class           | Source                                            |
| ------ | --------------- | ------------------------------------------------- |
| `sql`  | `SqlConnector`  | Any SQL database via a SQLAlchemy URL + `SELECT`  |
| `rest` | `RestConnector` | Any JSON REST API                                 |

This guide shows how to add a third one. Budget: **under 2 hours** for someone
who has never seen the codebase.

## The contract

Every connector subclasses `BaseConnector` (`app/services/connectors/base.py`)
and implements three methods:

```python
class BaseConnector(ABC, Generic[RawRecord]):
    key: str = ""            # unique id, e.g. "csv-folder"
    source_name: str = ""    # stored on EventLog.source

    def validate(self) -> None:        # raise ConnectorError if misconfigured
        ...
    def extract(self) -> Iterable[RawRecord]:   # pull raw records (usually dicts)
        ...
    def transform(self, record) -> NormalizedEvent | None:   # map one record
        ...                            # default works for dict records
```

`BaseConnector.run()` wires them together: `validate()` → `extract()` →
`transform()` each record → collect the non-`None`
[`NormalizedEvent`](../backend/app/services/csv_import.py)s into a
`ConnectorResult(events, extracted, skipped)`.

A `NormalizedEvent` needs at minimum a `case_key`, an `activity` and a
`timestamp` (plus optional `resource`, `cost`, `lifecycle`). If your records are
plain dicts, you don't even need to write `transform` — the default maps fields
through a `ColumnMapping` for you via `event_from_record`.

## Example: a JSON Lines file connector

Say you want to import a `.jsonl` file where each line is one event.

```python
# app/services/connectors/jsonl.py
import json
from collections.abc import Iterable
from dataclasses import dataclass

from app.schemas.event_log import ColumnMapping
from app.services.connectors.base import BaseConnector, ConnectorError


@dataclass
class JsonlConnectorConfig:
    file_path: str
    mapping: ColumnMapping


class JsonlConnector(BaseConnector[dict]):
    key = "jsonl"
    source_name = "jsonl"

    def __init__(self, config: JsonlConnectorConfig) -> None:
        super().__init__(config.mapping)
        self.config = config

    def validate(self) -> None:
        if not self.config.file_path.endswith(".jsonl"):
            raise ConnectorError("file_path must point to a .jsonl file")

    def extract(self) -> Iterable[dict]:
        with open(self.config.file_path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    yield json.loads(line)

    # transform() is inherited — the default maps each dict via self.mapping.
```

That's the whole connector. Use it directly:

```python
from app.schemas.event_log import ColumnMapping
from app.services import log_storage
from app.services.connectors.jsonl import JsonlConnector, JsonlConnectorConfig

connector = JsonlConnector(
    JsonlConnectorConfig(
        file_path="/data/events.jsonl",
        mapping=ColumnMapping(case_id="order_id", activity="step", timestamp="at"),
    )
)
result = connector.run()
log_storage.persist_log(
    db,
    workspace_id=user.workspace_id,
    name="orders",
    source=connector.source_name,
    events=result.events,
)
```

## Registering it (optional, for the HTTP API)

To expose a connector over the API and have it appear in `GET /api/connectors`:

1. Add it to `CONNECTOR_CLASSES` and `CONNECTORS` in
   `app/services/connectors/registry.py`.
2. Add a request schema in `app/schemas/connectors.py`.
3. Add a `POST /api/connectors/<key>/import` route in
   `app/api/routes/connectors.py` (copy the `sql`/`rest` handlers — they're ~15
   lines each and reuse the shared `_import` helper).

## Tips

- **Keep `extract()` lazy.** Yield records one at a time so large sources stream
  with bounded memory; `BaseConnector.iter_events()` relies on this.
- **`validate()` must be cheap and side-effect-free** — it runs before any
  network/DB call so the API can reject bad config with a clear 422.
- **Raise `ConnectorError`** for anything the user can fix (bad URL, unreachable
  host, wrong mapping). The API turns it into a `422` with your message.
- **Dot-paths for nested data.** The REST connector resolves mapped fields like
  `case.id` through nested JSON; reuse that pattern (`_dig`) if your source is
  hierarchical.
- **Write a test.** See `backend/tests/test_connectors.py` — an in-memory SQLite
  DB or a monkeypatched `httpx.request` is enough to cover a connector fully.
