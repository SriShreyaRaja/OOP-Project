"""
Persistence contract: plain-data RECORDS + the one interface Member 3 implements.

How it works ("write-through"): the domain keeps live objects in memory for speed and calls
save_…() every time something changes, so the database is always up to date. At startup,
desk.attach_storage(adapter) calls load_…() and rebuilds everything.

Only users, incidents and services are required; the rest have do-nothing defaults.
Wrap every database error in PersistenceError so the API answers 503 instead of crashing.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from .catalog import Category, ITService
from .common import Role
from .exceptions import ValidationError
from .users import Administrator, Employee, ITManager, PasswordHash, TeamLead, Technician, User


class Codec:
    """Tiny text encoders so small collections fit in one database column (no JSON library needed)."""

    @staticmethod
    def encode_int_map(m: dict[str, int]) -> str:
        return ",".join(f"{k}={v}" for k, v in sorted(m.items()))

    @staticmethod
    def decode_int_map(s: str | None) -> dict[str, int]:
        if not s:
            return {}
        return {k.strip(): int(v) for k, v in (pair.split("=", 1) for pair in s.split(","))}

    @staticmethod
    def encode_list(items) -> str:
        return ",".join(items)

    @staticmethod
    def decode_list(s: str | None) -> list[str]:
        return [x.strip() for x in (s or "").split(",") if x.strip()]


@dataclass(frozen=True)
class UserRecord:
    """One row of the users table."""
    user_id: str
    name: str
    email: str
    role: Role
    password_hash: str
    active: bool
    department: str | None = None
    skills: dict[str, int] = field(default_factory=dict)
    max_workload_points: int = 0
    years_experience: float = 0.0
    available: bool = False

    @classmethod
    def from_user(cls, u: User) -> "UserRecord":
        if isinstance(u, Technician):
            return cls(u.user_id, u.name, u.email, u.role, u.encoded_password_hash(), u.is_active,
                       None, u.skills, u.max_workload_points, u.years_experience, u.is_available())
        dept = u.department if isinstance(u, Employee) else None
        return cls(u.user_id, u.name, u.email, u.role, u.encoded_password_hash(), u.is_active, dept)

    def to_user(self) -> User:
        h = PasswordHash.decode(self.password_hash)
        if self.role == Role.EMPLOYEE:
            u = Employee(self.user_id, self.name, self.email, h, self.department)
        elif self.role == Role.TECHNICIAN:
            u = Technician(self.user_id, self.name, self.email, h, self.skills, self.max_workload_points, self.years_experience)
        elif self.role == Role.TEAM_LEAD:
            u = TeamLead(self.user_id, self.name, self.email, h, self.skills, self.max_workload_points, self.years_experience)
        elif self.role == Role.SYSTEM_ADMIN:
            u = Administrator(self.user_id, self.name, self.email, h)
        elif self.role == Role.IT_MANAGER:
            u = ITManager(self.user_id, self.name, self.email, h)
        else:
            raise ValidationError("The SYSTEM account is never stored.")
        if not self.active:
            u.deactivate()
        if isinstance(u, Technician):
            u.set_available(self.available)
        return u


@dataclass(frozen=True)
class ServiceRecord:
    service_id: str
    name: str
    business_criticality: int
    default_category: str
    keywords: tuple[str, ...] = ()
    depends_on: tuple[str, ...] = ()
    owner: str = "Unassigned"

    @classmethod
    def from_service(cls, s: ITService) -> "ServiceRecord":
        return cls(s.service_id, s.name, s.business_criticality, s.default_category,
                   tuple(sorted(s.keywords)), tuple(s.depends_on), s.owner)

    def to_service_without_dependencies(self) -> ITService:
        """Dependencies are added by the desk once every service exists."""
        s = ITService(self.service_id, self.name, self.business_criticality, self.default_category, *self.keywords)
        s.owner = self.owner
        return s


@dataclass(frozen=True)
class IncidentRecord:
    """
    Plain-data version of an Incident: maps directly onto database tables.
      incidents(...one column per scalar field...)
      incident_notes(incident_id, author_id, text, at, internal)
      incident_resolutions(incident_id, description, root_cause, preventive_action, technician_id, at)
    Save with incident.to_record(); rebuild with desk.attach_storage(...).
    """
    incident_id: str
    title: str
    description: str
    reporter_id: str
    service_id: str
    impact: str
    urgency: str
    affected_users: int
    created_at: datetime
    status: str
    category: str | None
    category_confidence: float | None
    priority: str | None
    priority_explanation: dict[str, Any]
    assignee_id: str | None
    previous_assignee_id: str | None
    assignment_reason: str
    resolved_at: datetime | None
    closed_at: datetime | None
    feedback_rating: int | None
    feedback_comment: str | None
    feedback_at: datetime | None
    escalation_level: int
    escalated_to: str | None
    related_incidents: tuple[str, ...]
    reopen_count: int
    sla_paused_since: datetime | None
    sla_paused_seconds: float
    sla_responded_at: datetime | None
    sla_resolved_at: datetime | None
    sla_response_breached: bool
    sla_resolution_breached: bool
    sla_warning_sent: bool
    sla_breach_notified: bool
    notes: tuple = ()           # tuple[Note, ...]
    resolutions: tuple = ()     # tuple[Resolution, ...]


class StorageAdapter(ABC):
    """THE ONE INTERFACE MEMBER 3 IMPLEMENTS to give the system a real database."""

    @abstractmethod
    def save_user(self, user: UserRecord) -> None: ...
    @abstractmethod
    def load_users(self) -> list[UserRecord]: ...
    @abstractmethod
    def save_incident(self, incident: IncidentRecord) -> None: ...
    @abstractmethod
    def load_incidents(self) -> list[IncidentRecord]: ...
    @abstractmethod
    def save_service(self, service: ServiceRecord) -> None: ...
    @abstractmethod
    def load_services(self) -> list[ServiceRecord]: ...

    # Optional: defaults do nothing, so a first version can skip them.
    def save_audit_event(self, event) -> None: pass
    def load_audit_events(self) -> list: return []
    def save_category(self, category: Category) -> None: pass
    def load_categories(self) -> list[Category]: return []
    def save_sla_policy(self, policy) -> None: pass
    def load_sla_policies(self) -> list: return []


class NoStorage(StorageAdapter):
    """Used when no database is attached (tests, demo): saves nothing, loads nothing."""
    def save_user(self, user): pass
    def load_users(self): return []
    def save_incident(self, incident): pass
    def load_incidents(self): return []
    def save_service(self, service): pass
    def load_services(self): return []


class InMemoryStorage(StorageAdapter):
    """
    A complete StorageAdapter that keeps records in dicts. Used by the tests to prove
    save → restart → reload works, and as a worked example for Member 3's SQLite version.
    """

    def __init__(self):
        self._users: dict[str, UserRecord] = {}
        self._incidents: dict[str, IncidentRecord] = {}
        self._services: dict[str, ServiceRecord] = {}
        self._categories: dict[str, Category] = {}
        self._policies: dict[str, object] = {}
        self._audit: list = []

    def save_user(self, u): self._users[u.user_id] = u
    def load_users(self): return list(self._users.values())
    def save_incident(self, i): self._incidents[i.incident_id] = i
    def load_incidents(self): return list(self._incidents.values())
    def save_service(self, s): self._services[s.service_id] = s
    def load_services(self): return list(self._services.values())
    def save_audit_event(self, e): self._audit.append(e)
    def load_audit_events(self): return list(self._audit)
    def save_category(self, c): self._categories[c.name] = c
    def load_categories(self): return list(self._categories.values())
    def save_sla_policy(self, p): self._policies[f"{p.service_id}/{p.priority.name}"] = p
    def load_sla_policies(self): return list(self._policies.values())
