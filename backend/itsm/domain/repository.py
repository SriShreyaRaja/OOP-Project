"""
REPOSITORY PATTERN: where the domain keeps its live objects.

The ServiceDesk only talks to these abstract interfaces. The in-memory versions hold the
working set (dict lookups are O(1)); the database is kept in sync through StorageAdapter.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .common import Role
from .incident import Incident
from .users import Technician, User


class IncidentRepository(ABC):
    @abstractmethod
    def save(self, incident: Incident) -> None: ...

    @abstractmethod
    def find_by_id(self, incident_id: str) -> Incident | None: ...

    @abstractmethod
    def find_all(self) -> list[Incident]: ...

    def find_open(self) -> list[Incident]:
        return [i for i in self.find_all() if i.is_open]


class UserRepository(ABC):
    @abstractmethod
    def save(self, user: User) -> None: ...

    @abstractmethod
    def find_by_id(self, user_id: str) -> User | None: ...

    @abstractmethod
    def find_all(self) -> list[User]: ...

    def find_by_email(self, email: str) -> User | None:
        return next((u for u in self.find_all() if u.email == (email or "").strip().lower()), None)

    def technicians(self) -> list[Technician]:
        return [u for u in self.find_all() if isinstance(u, Technician)]

    def by_role(self, role: Role) -> list[User]:
        return [u for u in self.find_all() if u.role == role]


class InMemoryIncidentRepository(IncidentRepository):
    def __init__(self):
        self._items: dict[str, Incident] = {}

    def save(self, incident):
        self._items[incident.incident_id] = incident

    def find_by_id(self, incident_id):
        return self._items.get(incident_id)

    def find_all(self):
        return sorted(self._items.values(), key=lambda i: (i.created_at, i.incident_id))


class InMemoryUserRepository(UserRepository):
    def __init__(self):
        self._items: dict[str, User] = {}

    def save(self, user):
        self._items[user.user_id] = user

    def find_by_id(self, user_id):
        return self._items.get(user_id)

    def find_all(self):
        return list(self._items.values())
