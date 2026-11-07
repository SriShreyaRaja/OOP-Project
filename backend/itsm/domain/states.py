"""
STATE PATTERN: the incident lifecycle.

  NEW → CLASSIFIED → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → RESOLVED → VERIFIED → CLOSED
                       ↑  ↺ reassign               │    ↑        │          │
                       │                           ▼    │        └─reopen─┬─┘
                       │                    AWAITING_INFO               ▼
                       └─────────────────────────────────────────── REOPENED
                                            (SLA clock paused)

Every action defaults to "illegal" in the base class. Each concrete state overrides ONLY
the actions that are legal from it, so NEW → CLOSED is impossible by construction rather
than by a long if/else chain. A new state (e.g. PENDING_VENDOR) = one new class plus one
override in the state that leads to it.

States hold no data, so each is a shared instance (see `States`).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum

from .exceptions import InvalidStateTransitionError


class Action(Enum):
    CLASSIFY = "classify"
    ASSIGN = "assign"
    ACKNOWLEDGE = "acknowledge"
    START_WORK = "start_work"
    REQUEST_INFO = "request_info"
    PROVIDE_INFO = "provide_info"
    RESOLVE = "resolve"
    VERIFY = "verify"
    REOPEN = "reopen"
    CLOSE = "close"


class IncidentState(ABC):
    is_open = True        # counts as an open incident in reports and queues
    sla_running = True    # does the SLA clock tick in this state?

    @property
    @abstractmethod
    def name(self) -> str: ...

    def _illegal(self, action: Action):
        raise InvalidStateTransitionError(
            f"Cannot {action.value.replace('_', ' ')} an incident that is {self.name}.")

    # Default for every action: refuse.
    def classify(self) -> "IncidentState":     return self._illegal(Action.CLASSIFY)
    def assign(self) -> "IncidentState":       return self._illegal(Action.ASSIGN)
    def acknowledge(self) -> "IncidentState":  return self._illegal(Action.ACKNOWLEDGE)
    def start_work(self) -> "IncidentState":   return self._illegal(Action.START_WORK)
    def request_info(self) -> "IncidentState": return self._illegal(Action.REQUEST_INFO)
    def provide_info(self) -> "IncidentState": return self._illegal(Action.PROVIDE_INFO)
    def resolve(self) -> "IncidentState":      return self._illegal(Action.RESOLVE)
    def verify(self) -> "IncidentState":       return self._illegal(Action.VERIFY)
    def reopen(self) -> "IncidentState":       return self._illegal(Action.REOPEN)
    def close(self) -> "IncidentState":        return self._illegal(Action.CLOSE)

    def next(self, action: Action) -> "IncidentState":
        """Polymorphic dispatch from an Action to the matching method."""
        return getattr(self, action.value)()

    def allows(self, action: Action) -> bool:
        try:
            self.next(action)
            return True
        except InvalidStateTransitionError:
            return False

    def allowed_actions(self) -> list[Action]:
        """Exactly the actions legal from this stage, in a fixed order."""
        return [a for a in Action if self.allows(a)]

    def __repr__(self) -> str:
        return self.name


class NewState(IncidentState):
    name = "NEW"
    def classify(self): return States.CLASSIFIED


class ClassifiedState(IncidentState):
    """Category, priority and SLA known. Re-classification is allowed."""
    name = "CLASSIFIED"
    def classify(self): return States.CLASSIFIED
    def assign(self): return States.ASSIGNED


class AssignedState(IncidentState):
    name = "ASSIGNED"
    def assign(self): return States.ASSIGNED          # reassignment
    def acknowledge(self): return States.ACKNOWLEDGED


class AcknowledgedState(IncidentState):
    name = "ACKNOWLEDGED"
    def assign(self): return States.ASSIGNED
    def start_work(self): return States.IN_PROGRESS


class InProgressState(IncidentState):
    name = "IN_PROGRESS"
    def assign(self): return States.ASSIGNED          # escalation / hand-over
    def request_info(self): return States.AWAITING_INFO
    def resolve(self): return States.RESOLVED


class AwaitingInfoState(IncidentState):
    """Waiting for the reporter. The SLA clock is PAUSED here."""
    name = "AWAITING_INFO"
    sla_running = False
    def provide_info(self): return States.IN_PROGRESS


class ResolvedState(IncidentState):
    """Fix delivered. Reporter verifies or reopens; auto-close if they stay silent."""
    name = "RESOLVED"
    is_open = False
    sla_running = False
    def verify(self): return States.VERIFIED
    def reopen(self): return States.REOPENED
    def close(self): return States.CLOSED


class VerifiedState(IncidentState):
    name = "VERIFIED"
    is_open = False
    sla_running = False
    def reopen(self): return States.REOPENED
    def close(self): return States.CLOSED


class ReopenedState(IncidentState):
    """The fix did not hold. Must be (re)assigned before work restarts."""
    name = "REOPENED"
    def assign(self): return States.ASSIGNED


class ClosedState(IncidentState):
    """Terminal. A recurrence is a new incident linked to this one."""
    name = "CLOSED"
    is_open = False
    sla_running = False


class States:
    """One shared instance of every state, plus lookup by name for the database."""
    NEW = NewState()
    CLASSIFIED = ClassifiedState()
    ASSIGNED = AssignedState()
    ACKNOWLEDGED = AcknowledgedState()
    IN_PROGRESS = InProgressState()
    AWAITING_INFO = AwaitingInfoState()
    RESOLVED = ResolvedState()
    VERIFIED = VerifiedState()
    REOPENED = ReopenedState()
    CLOSED = ClosedState()

    @classmethod
    def from_name(cls, name: str) -> IncidentState:
        """Member 3: rebuild the state object from the status text stored in the database."""
        state = getattr(cls, name, None)
        if not isinstance(state, IncidentState):
            raise InvalidStateTransitionError(f"Unknown state '{name}'.")
        return state
