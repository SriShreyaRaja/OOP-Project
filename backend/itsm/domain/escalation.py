"""
CHAIN OF RESPONSIBILITY: automatic escalation (Intelligent Feature C).

A P1/P2 incident that nobody has acknowledged climbs:
    Technician → Team Lead → System Administrator → IT Manager
Each handler knows its level and waiting threshold. If its threshold has passed it asks
the next (higher) level whether to take over; the highest level whose time has come wins.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from .common import Priority, Role
from .states import States


class EscalationHandler:
    def __init__(self, level: int, role: Role, after: timedelta):
        self.level = level
        self.role = role
        self.after = after
        self._next: EscalationHandler | None = None

    def set_next(self, handler: "EscalationHandler") -> "EscalationHandler":
        self._next = handler
        return handler

    def handle(self, waited: timedelta) -> "EscalationHandler | None":
        if waited < self.after:
            return None
        higher = self._next.handle(waited) if self._next else None
        return higher or self


class EscalationPolicy:
    WATCHED = {States.CLASSIFIED.name, States.ASSIGNED.name, States.REOPENED.name}   # not yet acknowledged

    def __init__(self):
        # minutes before escalating to (Team Lead, System Admin, IT Manager)
        self._thresholds = {Priority.P1: (5, 15, 30), Priority.P2: (15, 45, 90)}

    def configure(self, priority: Priority, team_lead_min: int, sys_admin_min: int, manager_min: int) -> None:
        self._thresholds[priority] = (team_lead_min, sys_admin_min, manager_min)

    def _chain_for(self, priority: Priority) -> EscalationHandler | None:
        t = self._thresholds.get(priority)
        if t is None:
            return None
        head = EscalationHandler(1, Role.TEAM_LEAD, timedelta(minutes=t[0]))
        head.set_next(EscalationHandler(2, Role.SYSTEM_ADMIN, timedelta(minutes=t[1]))) \
            .set_next(EscalationHandler(3, Role.IT_MANAGER, timedelta(minutes=t[2])))
        return head

    def evaluate(self, incident, now: datetime) -> EscalationHandler | None:
        """The level to escalate to now, or None if nothing should happen."""
        if incident.priority is None or incident.status not in self.WATCHED:
            return None
        chain = self._chain_for(incident.priority)
        target = chain.handle(now - incident.created_at) if chain else None
        return target if target and target.level > incident.escalation_level else None
