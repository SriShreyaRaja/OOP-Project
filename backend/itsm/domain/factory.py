"""
FACTORY PATTERN: one place that knows how to build valid objects.

IncidentFactory  parses text input ("HIGH"), resolves or guesses the service, stamps the
                 time from the Clock, and issues gap-free IDs (INC1001, INC1002…).
UserFactory      builds the right User subclass from a role string (e.g. a signup form).
NotificationChannelFactory builds a channel from its configured name.
"""
from __future__ import annotations

import re
import threading
from enum import Enum
from typing import TypeVar

from .catalog import ServiceCatalog
from .common import Clock, Impact, Role, Urgency
from .exceptions import ValidationError
from .incident import Incident
from .notifications import (EmailChannel, InAppChannel, NotificationChannel, SmsChannelAdapter,
                            ThirdPartySmsGateway)
from .users import Administrator, Employee, ITManager, TeamLead, Technician, User

E = TypeVar("E", bound=Enum)


def parse_enum(enum_cls: type[E], value, field_name: str) -> E:
    if isinstance(value, enum_cls):
        return value
    try:
        return enum_cls[str(value).strip().upper()]
    except (KeyError, AttributeError):
        raise ValidationError(f"{field_name} must be one of {[m.name for m in enum_cls]}") from None


class IncidentFactory:
    def __init__(self, catalog: ServiceCatalog, clock: Clock, start_number: int = 1001):
        self._catalog = catalog
        self._clock = clock
        self._next_number = start_number
        self._lock = threading.Lock()

    def next_id(self) -> str:
        with self._lock:
            n = self._next_number
            self._next_number += 1
            return f"INC{n}"

    def discard(self, incident_id: str) -> None:
        """Give back the last ID if that incident was rejected, so IDs stay gap-free."""
        with self._lock:
            if incident_id == f"INC{self._next_number - 1}":
                self._next_number -= 1

    def continue_after(self, existing_id: str) -> None:
        """After reloading saved incidents, continue numbering after the highest ID."""
        digits = re.sub(r"\D", "", existing_id)
        if digits:
            with self._lock:
                self._next_number = max(self._next_number, int(digits) + 1)

    def peek_next_id(self) -> str:
        return f"INC{self._next_number}"

    def create(self, reporter: User, title: str, description: str, service_id: str | None,
               impact, urgency, affected_users: int) -> Incident:
        if service_id:
            service = self._catalog.get(service_id)
        else:
            service = self._catalog.guess_service(f"{title} {description}")
            if service is None:
                raise ValidationError("Could not determine the affected service; please choose one.")
        return Incident(self.next_id(), title, description, reporter, service,
                        parse_enum(Impact, impact, "impact"), parse_enum(Urgency, urgency, "urgency"),
                        affected_users, self._clock.now())


class UserFactory:
    @staticmethod
    def create(role, user_id: str, name: str, email: str, password: str, *, skills: dict | None = None,
               max_workload_points: int = 20, years_experience: float = 0, department: str | None = None) -> User:
        r = parse_enum(Role, role, "role")
        if r == Role.EMPLOYEE:
            return Employee(user_id, name, email, password, department)
        if r == Role.TECHNICIAN:
            return Technician(user_id, name, email, password, skills, max_workload_points, years_experience)
        if r == Role.TEAM_LEAD:
            return TeamLead(user_id, name, email, password, skills, max_workload_points, years_experience)
        if r == Role.SYSTEM_ADMIN:
            return Administrator(user_id, name, email, password)
        if r == Role.IT_MANAGER:
            return ITManager(user_id, name, email, password)
        raise ValidationError("The SYSTEM account cannot be created.")


class NotificationChannelFactory:
    @staticmethod
    def create(name: str, phone_book: dict[str, str] | None = None) -> NotificationChannel:
        name = name.lower()
        if name == "in_app":
            return InAppChannel()
        if name == "email":
            return EmailChannel()
        if name == "sms":
            return SmsChannelAdapter(ThirdPartySmsGateway(), phone_book)
        raise ValidationError(f"Unknown notification channel '{name}'.")
