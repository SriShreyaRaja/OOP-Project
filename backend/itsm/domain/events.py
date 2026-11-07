"""
OBSERVER PATTERN: events and the audit trail.

The Incident never sends emails or writes logs itself. It records DomainEvents; the
EventBus hands each one to every subscribed observer (AuditLog, NotificationService…).
A new reaction = a new observer, with zero changes to Incident.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime

from .common import EventType, both_times


@dataclass(frozen=True)
class DomainEvent:
    """Something important that happened. Also an audit record (who, what, when, before/after)."""
    type: EventType
    incident_id: str
    actor_id: str
    at: datetime
    description: str
    previous_state: str | None = None
    new_state: str | None = None
    recipients: tuple[str, ...] = ()
    urgent: bool = False

    def to_dict(self) -> dict:
        return {"event": self.type.name, "incidentId": self.incident_id, "actor": self.actor_id,
                "at": self.at.isoformat(), "atDisplay": both_times(self.at),
                "description": self.description, "previousState": self.previous_state,
                "newState": self.new_state}


class EventObserver(ABC):
    @abstractmethod
    def on_event(self, event: DomainEvent) -> None: ...


class EventBus:
    """The subject. Observers can listen to everything or only to some event types."""

    def __init__(self):
        self._global: list = []
        self._by_type: dict[EventType, list] = defaultdict(list)

    def subscribe(self, observer, *event_types: EventType) -> None:
        """observer = an EventObserver or any function taking a DomainEvent."""
        if event_types:
            for t in event_types:
                self._by_type[t].append(observer)
        else:
            self._global.append(observer)

    def publish(self, event: DomainEvent) -> None:
        for obs in self._global + self._by_type.get(event.type, []):
            (obs.on_event if isinstance(obs, EventObserver) else obs)(event)


class AuditLog(EventObserver):
    """Append-only, chronological history of every important action."""

    def __init__(self):
        self._entries: list[DomainEvent] = []

    def on_event(self, event: DomainEvent) -> None:
        self._entries.append(event)

    def restore(self, saved: list[DomainEvent]) -> None:
        """Reload saved history after a restart (does not re-publish anything)."""
        self._entries.extend(saved)

    def all(self) -> list[DomainEvent]:
        return list(self._entries)

    def for_incident(self, incident_id: str) -> list[DomainEvent]:
        return [e for e in self._entries if e.incident_id == incident_id]

    def timeline(self, incident_id: str) -> str:
        """Human-readable history, like the example in the project brief."""
        return "\n".join(f"{both_times(e.at)} – {e.incident_id} {e.description}"
                         for e in self.for_incident(incident_id))
