"""The connector contract shared by every data source (Story 1.4).

A connector is responsible for three things and nothing else:

* :meth:`BaseConnector.validate` — cheap, side-effect-free check that the
  configuration is well-formed (raises :class:`ConnectorError` on problems).
* :meth:`BaseConnector.extract` — pull raw records from the source as an
  iterable of plain ``dict``s. This is the only part that talks to the outside
  world (a DB, an HTTP API, a file, ...).
* :meth:`BaseConnector.transform` — turn one raw record into a
  :class:`~app.services.csv_import.NormalizedEvent` (or ``None`` to drop it).

The base class wires these together in :meth:`run`, so the core import code can
treat every source identically and never needs to know how the data was fetched.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Generic, TypeVar

from app.schemas.event_log import ColumnMapping
from app.services.csv_import import NormalizedEvent, event_from_record

# Raw record type a concrete connector emits from ``extract`` (usually a dict).
RawRecord = TypeVar("RawRecord")


class ConnectorError(Exception):
    """Raised when a connector is misconfigured or the source is unreachable."""


@dataclass
class ConnectorResult:
    """Outcome of a connector run, before persistence."""

    events: list[NormalizedEvent]
    extracted: int
    skipped: int


class BaseConnector(ABC, Generic[RawRecord]):
    """Abstract base every connector implements.

    Subclasses take their own typed config and implement :meth:`validate`,
    :meth:`extract` and :meth:`transform`. They must also set
    :attr:`source_name` (stored on the resulting event log) and declare a
    unique :attr:`key` used by the registry / API.
    """

    #: Stable identifier used in the API (e.g. ``"sql"``, ``"rest"``).
    key: str = ""
    #: Value written to ``EventLog.source`` for logs created by this connector.
    source_name: str = "connector"

    def __init__(self, mapping: ColumnMapping) -> None:
        self.mapping = mapping

    @abstractmethod
    def validate(self) -> None:
        """Raise :class:`ConnectorError` if the configuration is invalid."""

    @abstractmethod
    def extract(self) -> Iterable[RawRecord]:
        """Yield raw records (dicts) from the underlying source."""

    def transform(self, record: RawRecord) -> NormalizedEvent | None:
        """Map one raw record to a NormalizedEvent via the column mapping.

        The default implementation works for any record that is a ``dict`` of
        field name -> value. Override it for sources that need custom shaping.
        """
        if not isinstance(record, dict):
            raise ConnectorError(
                "Default transform expects dict records; override transform()"
            )
        return event_from_record(record, self.mapping)

    def run(self) -> ConnectorResult:
        """Validate, extract and transform — the full pipeline for one import."""
        self.validate()
        events: list[NormalizedEvent] = []
        extracted = 0
        skipped = 0
        for record in self.extract():
            extracted += 1
            event = self.transform(record)
            if event is None:
                skipped += 1
            else:
                events.append(event)
        return ConnectorResult(events=events, extracted=extracted, skipped=skipped)

    def iter_events(self) -> Iterator[NormalizedEvent]:
        """Stream events without materializing the whole list (constant memory)."""
        self.validate()
        for record in self.extract():
            event = self.transform(record)
            if event is not None:
                yield event
