"""
People in the system.

Inheritance is used only for true "is-a" relationships:

    User (abstract)
     ├── Employee
     ├── Technician
     │     └── TeamLead        (a team lead IS a technician with extra rights)
     └── Administrator
           ├── ITManager       (an IT manager IS an administrator)
           └── SystemAccount   (the robot user for automatic actions)

Polymorphism: each subclass answers `permissions` differently, so the rest of the system
just asks `user.can(Permission.X)` without checking types.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
import uuid
from abc import ABC, abstractmethod

from .common import Permission, Priority, Role
from .exceptions import (TechnicianUnavailableError, UnauthorizedOperationError,
                         ValidationError, WorkloadExceededError)

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class PasswordHash:
    """A salted PBKDF2 hash. Plain-text passwords are never stored."""
    ITERATIONS = 65_536

    def __init__(self, salt: bytes, digest: bytes):
        self._salt = salt
        self._digest = digest

    @classmethod
    def of(cls, password: str) -> "PasswordHash":
        cls.validate_strength(password)
        salt = os.urandom(16)
        return cls(salt, cls._derive(password, salt))

    @classmethod
    def decode(cls, encoded: str) -> "PasswordHash":
        """Rebuild from the "salt:hash" string produced by encode() (read from the database)."""
        try:
            salt, digest = encoded.split(":")
            return cls(base64.b64decode(salt), base64.b64decode(digest))
        except (ValueError, AttributeError):
            raise ValidationError("Malformed stored password hash.") from None

    def encode(self) -> str:
        """'salt:hash' in Base64, safe to store in a text column."""
        return base64.b64encode(self._salt).decode() + ":" + base64.b64encode(self._digest).decode()

    def matches(self, password: str | None) -> bool:
        """Constant-time comparison, so response timing doesn't leak information."""
        return hmac.compare_digest(self._derive(password or "", self._salt), self._digest)

    @staticmethod
    def validate_strength(password: str | None) -> None:
        if (not password or len(password) < 8 or not any(c.isdigit() for c in password)
                or not any(c.isalpha() for c in password)):
            raise ValidationError("Password must be 8+ characters with letters and digits.")

    @classmethod
    def _derive(cls, password: str, salt: bytes) -> bytes:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, cls.ITERATIONS)

    def __repr__(self) -> str:
        return "PasswordHash(****)"


class User(ABC):
    """Abstract base for every person. `password` may be plain text or an existing PasswordHash."""

    def __init__(self, user_id: str, name: str, email: str, password: str | PasswordHash):
        if not user_id or not user_id.strip() or not name or not name.strip():
            raise ValidationError("User id and name are required.")
        if not email or not _EMAIL.match(email):
            raise ValidationError(f"Invalid email: {email}")
        self._user_id = user_id.strip()
        self._name = name.strip()
        self._email = email.strip().lower()
        self._password_hash = password if isinstance(password, PasswordHash) else PasswordHash.of(password)
        self._active = True

    # ---- encapsulated, read-only attributes ------------------------------------------
    @property
    def user_id(self) -> str:
        return self._user_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> str:
        return self._email

    @property
    def is_active(self) -> bool:
        return self._active

    def check_password(self, password: str | None) -> bool:
        return self._active and self._password_hash.matches(password)

    def change_password(self, old: str, new: str) -> None:
        if not self.check_password(old):
            raise UnauthorizedOperationError("Old password is incorrect.")
        self._password_hash = PasswordHash.of(new)

    def encoded_password_hash(self) -> str:
        """For persistence only (Member 3 stores this string)."""
        return self._password_hash.encode()

    def deactivate(self) -> None:
        self._active = False

    def activate(self) -> None:
        self._active = True

    # ---- polymorphic authorization -------------------------------------------------
    @property
    @abstractmethod
    def role(self) -> Role: ...

    @property
    @abstractmethod
    def permissions(self) -> frozenset[Permission]: ...

    def can(self, permission: Permission) -> bool:
        return self._active and permission in self.permissions

    def require(self, permission: Permission) -> None:
        if not self.can(permission):
            raise UnauthorizedOperationError(
                f"{self.role.name} {self.user_id} is not allowed to {permission.name}.")

    def to_dict(self) -> dict:
        return {"userId": self.user_id, "name": self.name, "email": self.email,
                "role": self.role.name, "active": self.is_active}

    def __eq__(self, other) -> bool:
        return isinstance(other, User) and other.user_id == self.user_id

    def __hash__(self) -> int:
        return hash(self.user_id)

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.user_id} {self.name})"


class Employee(User):
    _PERMS = frozenset({Permission.REPORT_INCIDENT, Permission.VIEW_OWN_INCIDENTS, Permission.ADD_INFO,
                        Permission.GIVE_FEEDBACK, Permission.VERIFY_RESOLUTION})

    def __init__(self, user_id, name, email, password, department: str | None = None):
        super().__init__(user_id, name, email, password)
        self._department = department or "General"

    @property
    def department(self) -> str:
        return self._department

    @property
    def role(self) -> Role:
        return Role.EMPLOYEE

    @property
    def permissions(self) -> frozenset[Permission]:
        return self._PERMS


class Technician(User):
    """
    A support engineer. Workload is measured in POINTS, not ticket count: a P1 costs 8
    points, a P4 costs 1 (see Priority.workload_points). Ten printer jams are not the
    same load as one payment outage.
    """
    _PERMS = frozenset({Permission.REPORT_INCIDENT, Permission.VIEW_OWN_INCIDENTS, Permission.WORK_INCIDENT,
                        Permission.RESOLVE_INCIDENT, Permission.REQUEST_INFO})

    def __init__(self, user_id, name, email, password, skills: dict[str, int] | None = None,
                 max_workload_points: int = 20, years_experience: float = 0.0):
        super().__init__(user_id, name, email, password)
        if max_workload_points < Priority.P1.workload_points:
            raise ValidationError("max_workload_points must allow at least one P1 incident.")
        if years_experience < 0:
            raise ValidationError("Experience cannot be negative.")
        self._skills: dict[str, int] = {c.upper(): self._check_level(l) for c, l in (skills or {}).items()}
        self._active_incidents: dict[str, Priority] = {}      # incident id → its priority
        self._service_history: dict[str, int] = {}            # service id → incidents resolved
        self._max_workload_points = max_workload_points
        self._years_experience = float(years_experience)
        self._available = True
        self._resolved_count = 0

    # ---- skills ---------------------------------------------------------------------
    @staticmethod
    def _check_level(level: int) -> int:
        if not 1 <= level <= 5:
            raise ValidationError("Skill level must be 1..5.")
        return level

    def set_skill(self, category: str, level: int) -> None:
        self._skills[category.upper()] = self._check_level(level)

    def replace_skills(self, skills: dict[str, int]) -> None:
        """Admin "manage technicians": replace all skills at once."""
        checked = {c.upper(): self._check_level(l) for c, l in skills.items()}
        self._skills = checked

    def skill_level(self, category: str | None) -> int:
        return self._skills.get(category.upper(), 0) if category else 0

    @property
    def skills(self) -> dict[str, int]:
        return dict(self._skills)          # defensive copy

    # ---- workload -------------------------------------------------------------------
    @property
    def workload_points(self) -> int:
        return sum(p.workload_points for p in self._active_incidents.values())

    @property
    def active_count(self) -> int:
        return len(self._active_incidents)

    @property
    def max_workload_points(self) -> int:
        return self._max_workload_points

    @property
    def load_ratio(self) -> float:
        return self.workload_points / self._max_workload_points

    @property
    def years_experience(self) -> float:
        return self._years_experience

    @property
    def resolved_count(self) -> int:
        return self._resolved_count

    @property
    def active_incident_ids(self) -> frozenset[str]:
        return frozenset(self._active_incidents)

    @property
    def service_history(self) -> dict[str, int]:
        return dict(self._service_history)

    def is_available(self) -> bool:
        return self.is_active and self._available

    def set_available(self, available: bool) -> None:
        self._available = available

    def has_capacity_for(self, priority: Priority) -> bool:
        return self.is_available() and self.workload_points + priority.workload_points <= self._max_workload_points

    def take_incident(self, incident_id: str, priority: Priority) -> None:
        if not self.is_available():
            raise TechnicianUnavailableError(f"Technician {self.user_id} is unavailable.")
        if incident_id in self._active_incidents:
            return
        if not self.has_capacity_for(priority):
            raise WorkloadExceededError(
                f"Technician {self.user_id} has {self.workload_points}/{self._max_workload_points} points; "
                f"a {priority.name} needs {priority.workload_points} more.")
        self._active_incidents[incident_id] = priority

    def update_priority(self, incident_id: str, priority: Priority) -> None:
        """Keeps points accurate if an assigned incident is re-prioritised."""
        if incident_id in self._active_incidents:
            self._active_incidents[incident_id] = priority

    def release_incident(self, incident_id: str) -> None:
        self._active_incidents.pop(incident_id, None)

    def record_resolution(self, incident_id: str, service_id: str) -> None:
        self.release_incident(incident_id)
        self._resolved_count += 1
        self._service_history[service_id] = self._service_history.get(service_id, 0) + 1

    def experience_with(self, service_id: str) -> int:
        return self._service_history.get(service_id, 0)

    # ---- persistence helpers (rebuilt from saved incidents after a restart) ----------
    def restore_history(self, resolved: int, history: dict[str, int]) -> None:
        self._resolved_count = resolved
        self._service_history = dict(history)

    def restore_workload(self, incident_id: str, priority: Priority) -> None:
        self._active_incidents[incident_id] = priority          # already accepted before

    @property
    def role(self) -> Role:
        return Role.TECHNICIAN

    @property
    def permissions(self) -> frozenset[Permission]:
        return self._PERMS

    def to_dict(self) -> dict:
        d = super().to_dict()
        d.update({"skills": self.skills, "workloadPoints": self.workload_points,
                  "maxWorkloadPoints": self._max_workload_points, "activeIncidents": self.active_count,
                  "available": self.is_available(), "yearsExperience": self._years_experience,
                  "resolvedCount": self._resolved_count})
        return d


class TeamLead(Technician):
    @property
    def role(self) -> Role:
        return Role.TEAM_LEAD

    @property
    def permissions(self) -> frozenset[Permission]:
        return super().permissions | {Permission.REASSIGN_INCIDENT, Permission.VIEW_ALL_INCIDENTS,
                                      Permission.VIEW_REPORTS}


class Administrator(User):
    _PERMS = frozenset({
        Permission.MANAGE_USERS, Permission.MANAGE_SERVICES, Permission.CONFIGURE_SLA,
        Permission.CONFIGURE_CATEGORIES, Permission.CONFIGURE_STRATEGY, Permission.VIEW_ALL_INCIDENTS,
        Permission.VIEW_REPORTS, Permission.VIEW_AUDIT, Permission.REASSIGN_INCIDENT,
        Permission.CLOSE_INCIDENT, Permission.REPORT_INCIDENT})

    @property
    def role(self) -> Role:
        return Role.SYSTEM_ADMIN

    @property
    def permissions(self) -> frozenset[Permission]:
        return self._PERMS


class ITManager(Administrator):
    @property
    def role(self) -> Role:
        return Role.IT_MANAGER


class SystemAccount(Administrator):
    """The actor for automatic actions (auto-assign, SLA scans, escalation). It can never log in."""
    ID = "SYSTEM"

    def __init__(self):
        super().__init__(self.ID, "I-ITSM Automation", "system@itsm.local", f"{uuid.uuid4()}x1")

    @property
    def role(self) -> Role:
        return Role.SYSTEM

    def check_password(self, password) -> bool:
        return False

    def can(self, permission: Permission) -> bool:
        return permission in self.permissions
