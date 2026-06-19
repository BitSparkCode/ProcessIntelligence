from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


class EventLog(Base):
    """A single imported event log with its metadata."""

    __tablename__ = "event_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source: Mapped[str] = mapped_column(String(64), nullable=False, default="csv")
    imported_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    row_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    cases: Mapped[list[Case]] = relationship(
        back_populates="log", cascade="all, delete-orphan", passive_deletes=True
    )
    activities: Mapped[list[Activity]] = relationship(
        back_populates="log", cascade="all, delete-orphan", passive_deletes=True
    )
    resources: Mapped[list[Resource]] = relationship(
        back_populates="log", cascade="all, delete-orphan", passive_deletes=True
    )
    events: Mapped[list[Event]] = relationship(
        back_populates="log", cascade="all, delete-orphan", passive_deletes=True
    )


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("log_id", "name", name="uq_activity_log_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    log_id: Mapped[str] = mapped_column(
        ForeignKey("event_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)

    log: Mapped[EventLog] = relationship(back_populates="activities")


class Resource(Base):
    __tablename__ = "resources"
    __table_args__ = (UniqueConstraint("log_id", "name", name="uq_resource_log_name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    log_id: Mapped[str] = mapped_column(
        ForeignKey("event_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)

    log: Mapped[EventLog] = relationship(back_populates="resources")


class Case(Base):
    __tablename__ = "cases"
    __table_args__ = (UniqueConstraint("log_id", "case_key", name="uq_case_log_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    log_id: Mapped[str] = mapped_column(
        ForeignKey("event_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_key: Mapped[str] = mapped_column(String(512), nullable=False)

    log: Mapped[EventLog] = relationship(back_populates="cases")
    events: Mapped[list[Event]] = relationship(
        back_populates="case", cascade="all, delete-orphan", passive_deletes=True
    )


class Event(Base):
    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_log_timestamp", "log_id", "timestamp"),
        Index("ix_events_case_timestamp", "case_id", "timestamp"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    log_id: Mapped[str] = mapped_column(
        ForeignKey("event_logs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    case_id: Mapped[str] = mapped_column(
        ForeignKey("cases.id", ondelete="CASCADE"), nullable=False, index=True
    )
    activity_id: Mapped[str] = mapped_column(
        ForeignKey("activities.id", ondelete="CASCADE"), nullable=False, index=True
    )
    resource_id: Mapped[str | None] = mapped_column(
        ForeignKey("resources.id", ondelete="SET NULL"), nullable=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lifecycle: Mapped[str | None] = mapped_column(String(64), nullable=True)
    cost: Mapped[float | None] = mapped_column(Float, nullable=True)

    log: Mapped[EventLog] = relationship(back_populates="events")
    case: Mapped[Case] = relationship(back_populates="events")
    activity: Mapped[Activity] = relationship()
    resource: Mapped[Resource | None] = relationship()
    attributes: Mapped[list[Attribute]] = relationship(
        back_populates="event", cascade="all, delete-orphan", passive_deletes=True
    )


class Attribute(Base):
    """Extensible key-value attribute attached to an event."""

    __tablename__ = "attributes"
    __table_args__ = (Index("ix_attributes_event_key", "event_id", "key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    event_id: Mapped[str] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    key: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str | None] = mapped_column(String, nullable=True)

    event: Mapped[Event] = relationship(back_populates="attributes")
