"""
Shared basics: fixed vocabularies (enums), the clock, time formatting and JSON output.

Incident CATEGORIES are deliberately NOT an enum: they live in CategoryRegistry so an
admin can add a new one at runtime without a code change (Open/Closed Principle).
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import fields, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum


class NamedEnum(Enum):
    """An Enum that prints as just its name (e.g. SYSTEM_ADMIN), for readable output."""

    def __repr__(self) -> str:
        return self.name


class Role(NamedEnum):
    EMPLOYEE = "EMPLOYEE"
    TECHNICIAN = "TECHNICIAN"
    TEAM_LEAD = "TEAM_LEAD"
    SYSTEM_ADMIN = "SYSTEM_ADMIN"
    IT_MANAGER = "IT_MANAGER"
    SYSTEM = "SYSTEM"


class Impact(NamedEnum):
    """How widely the problem is felt. Higher = worse."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    ORGANIZATION = 4

    @property
    def weight(self) -> int:
        return self.value


class Urgency(NamedEnum):
    """How quickly the business needs it fixed. Higher = more urgent."""
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def weight(self) -> int:
        return self.value


class Priority(NamedEnum):
    """value = (label, workload points it costs a technician)."""
    P1 = ("Critical", 8)
    P2 = ("High", 5)
    P3 = ("Medium", 3)
    P4 = ("Low", 1)

    @property
    def label(self) -> str:
        return self.value[0]

    @property
    def workload_points(self) -> int:
        return self.value[1]

    @property
    def rank(self) -> int:
        """1 = most important; handy for sorting queues."""
        return int(self.name[1])

    def __str__(self) -> str:
        return f"{self.name} - {self.label}"


class SLAStatus(NamedEnum):
    ON_TRACK = "ON_TRACK"
    AT_RISK = "AT_RISK"
    PAUSED = "PAUSED"
    BREACHED = "BREACHED"
    MET = "MET"


class ServiceHealth(NamedEnum):
    OPERATIONAL = "OPERATIONAL"
    DEGRADED = "DEGRADED"
    DOWN = "DOWN"


class EventType(NamedEnum):
    INCIDENT_CREATED = "INCIDENT_CREATED"
    INCIDENT_CLASSIFIED = "INCIDENT_CLASSIFIED"
    PRIORITY_CALCULATED = "PRIORITY_CALCULATED"
    PRIORITY_CHANGED = "PRIORITY_CHANGED"
    INCIDENT_ASSIGNED = "INCIDENT_ASSIGNED"
    STATUS_CHANGED = "STATUS_CHANGED"
    NOTE_ADDED = "NOTE_ADDED"
    INFO_REQUESTED = "INFO_REQUESTED"
    INFO_PROVIDED = "INFO_PROVIDED"
    SLA_WARNING = "SLA_WARNING"
    SLA_BREACHED = "SLA_BREACHED"
    INCIDENT_ESCALATED = "INCIDENT_ESCALATED"
    INCIDENT_RESOLVED = "INCIDENT_RESOLVED"
    INCIDENT_REOPENED = "INCIDENT_REOPENED"
    INCIDENT_CLOSED = "INCIDENT_CLOSED"
    FEEDBACK_GIVEN = "FEEDBACK_GIVEN"
    INCIDENT_LINKED = "INCIDENT_LINKED"
    SYSTEM_NOTICE = "SYSTEM_NOTICE"


class Permission(NamedEnum):
    REPORT_INCIDENT = "REPORT_INCIDENT"
    VIEW_OWN_INCIDENTS = "VIEW_OWN_INCIDENTS"
    ADD_INFO = "ADD_INFO"
    GIVE_FEEDBACK = "GIVE_FEEDBACK"
    VERIFY_RESOLUTION = "VERIFY_RESOLUTION"
    WORK_INCIDENT = "WORK_INCIDENT"
    RESOLVE_INCIDENT = "RESOLVE_INCIDENT"
    REQUEST_INFO = "REQUEST_INFO"
    REASSIGN_INCIDENT = "REASSIGN_INCIDENT"
    VIEW_ALL_INCIDENTS = "VIEW_ALL_INCIDENTS"
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_SERVICES = "MANAGE_SERVICES"
    CONFIGURE_SLA = "CONFIGURE_SLA"
    CONFIGURE_CATEGORIES = "CONFIGURE_CATEGORIES"
    CONFIGURE_STRATEGY = "CONFIGURE_STRATEGY"
    VIEW_REPORTS = "VIEW_REPORTS"
    VIEW_AUDIT = "VIEW_AUDIT"
    CLOSE_INCIDENT = "CLOSE_INCIDENT"


# ───────────────────────────── time ─────────────────────────────────────────
class Clock(ABC):
    """
    The domain never calls datetime.now() directly; it asks a Clock. Tests and the demo use
    FakeClock to fast-forward time and trigger SLA breaches instantly.
    """

    @abstractmethod
    def now(self) -> datetime:
        """Current time, timezone-aware, in UTC."""


class SystemClock(Clock):
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


class FakeClock(Clock):
    def __init__(self, start: datetime | None = None):
        self._now = start or datetime(2026, 11, 7, 4, 30, tzinfo=timezone.utc)   # 10:00 IST

    def now(self) -> datetime:
        return self._now

    def advance(self, **kwargs) -> None:
        """e.g. clock.advance(minutes=20) or clock.advance(hours=2)"""
        self._now += timedelta(**kwargs)


# Fixed offset (works on Windows without the tzdata package).
IST = timezone(timedelta(hours=5, minutes=30), "IST")


def both_times(t: datetime) -> str:
    """Every user-facing time is shown in UTC and IST: '2026-11-07 04:30 UTC / 10:00 IST'."""
    utc = t.astimezone(timezone.utc)
    return f"{utc:%Y-%m-%d %H:%M} UTC / {t.astimezone(IST):%H:%M} IST"


# ───────────────────────────── JSON ─────────────────────────────────────────
def _camel(name: str) -> str:
    head, *rest = name.split("_")
    return head + "".join(w.capitalize() for w in rest)


def to_plain(value):
    """
    Convert domain values (enums, datetimes, dataclasses, sets) into JSON-ready Python data.
    Dataclass fields become camelCase (technician_id → technicianId), so every API reply
    uses the same naming style as Incident.to_dict().
    """
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Enum):
        return value.name
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, timedelta):
        return value.total_seconds()
    if is_dataclass(value) and not isinstance(value, type):
        return {_camel(f.name): to_plain(getattr(value, f.name)) for f in fields(value)}
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [to_plain(v) for v in value]
    if hasattr(value, "to_dict"):
        return to_plain(value.to_dict())
    return str(value)


def to_json(value, indent: int | None = None) -> str:
    """What the API will send, e.g. to_json(incident.to_dict(desk.now()))."""
    return json.dumps(to_plain(value), ensure_ascii=False, indent=indent)
