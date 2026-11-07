"""
The Incident aggregate: the heart of the domain.

Encapsulation: every field is private (leading underscore) and exposed read-only. State
only changes through business methods, each of which
  1. checks the actor's permission,
  2. asks the current IncidentState for the next state (State pattern),
  3. updates its data,
  4. records a DomainEvent (later picked up by the audit log and notifications).

Composition: an Incident OWNS its notes, resolutions, SLA clock and feedback.
Association: it REFERENCES a reporter, a technician and a service, which live on their own.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Callable

from .catalog import ITService
from .common import EventType, Impact, Permission, Priority, Role, Urgency, both_times
from .events import DomainEvent
from .exceptions import InvalidStateTransitionError, UnauthorizedOperationError, ValidationError
from .persistence import IncidentRecord
from .sla import SLAClock, SLAPolicy, SLAPolicyBook
from .states import Action, IncidentState, States
from .users import Technician, User


@dataclass(frozen=True)
class Note:
    """A comment. Internal notes are visible to support staff only."""
    author_id: str
    text: str
    at: datetime
    internal: bool = False


@dataclass(frozen=True)
class Resolution:
    """What fixed it. Root cause + preventive action feed the 'suggested resolution' feature."""
    description: str
    root_cause: str
    preventive_action: str
    technician_id: str
    at: datetime

    def __post_init__(self):
        if not self.description or len(self.description.strip()) < 10:
            raise ValidationError("Resolution must describe the fix (min 10 characters).")
        if not self.root_cause or not self.root_cause.strip():
            raise ValidationError("Root cause is required.")


@dataclass(frozen=True)
class Feedback:
    rating: int
    comment: str
    at: datetime

    def __post_init__(self):
        if not 1 <= self.rating <= 5:
            raise ValidationError("Rating must be 1..5.")


def _require_text(value: str | None, what: str) -> str:
    if not value or not value.strip():
        raise ValidationError(f"{what} cannot be empty.")
    return value.strip()


class Incident:
    def __init__(self, incident_id: str, title: str, description: str, reporter: User,
                 service: ITService, impact: Impact, urgency: Urgency, affected_users: int,
                 created_at: datetime):
        if not title or len(title.strip()) < 5:
            raise ValidationError("Title must be at least 5 characters.")
        if not description or len(description.strip()) < 10:
            raise ValidationError("Description must be at least 10 characters.")
        if affected_users < 1:
            raise ValidationError("affected_users must be at least 1.")
        self._id = incident_id
        self._title = title.strip()
        self._description = description.strip()
        self._reporter = reporter
        self._service = service
        self._impact = impact
        self._urgency = urgency
        self._affected_users = affected_users
        self._created_at = created_at

        self._state: IncidentState = States.NEW
        self._category: str | None = None
        self._category_confidence: float | None = None
        self._priority: Priority | None = None
        self._priority_explanation: dict = {}
        self._sla: SLAClock | None = None
        self._assignee: Technician | None = None
        self._previous_assignee: Technician | None = None
        self._assignment_reason = ""
        self._notes: list[Note] = []
        self._resolutions: list[Resolution] = []
        self._resolved_at: datetime | None = None
        self._closed_at: datetime | None = None
        self._feedback: Feedback | None = None
        self._escalation_level = 0
        self._escalated_to: Role | None = None
        self._related: set[str] = set()
        self._reopen_count = 0
        self._pending: list[DomainEvent] = []

    # ═════════════════════════ read-only properties ═════════════════════════
    incident_id = property(lambda s: s._id)
    title = property(lambda s: s._title)
    description = property(lambda s: s._description)
    reporter = property(lambda s: s._reporter)
    service = property(lambda s: s._service)
    impact = property(lambda s: s._impact)
    urgency = property(lambda s: s._urgency)
    affected_users = property(lambda s: s._affected_users)
    created_at = property(lambda s: s._created_at)
    state = property(lambda s: s._state)
    status = property(lambda s: s._state.name)
    is_open = property(lambda s: s._state.is_open)
    category = property(lambda s: s._category)
    priority = property(lambda s: s._priority)
    priority_explanation = property(lambda s: dict(s._priority_explanation))
    sla = property(lambda s: s._sla)
    assignee = property(lambda s: s._assignee)
    previous_assignee = property(lambda s: s._previous_assignee)
    assignment_reason = property(lambda s: s._assignment_reason)
    notes = property(lambda s: list(s._notes))
    resolutions = property(lambda s: list(s._resolutions))
    resolved_at = property(lambda s: s._resolved_at)
    closed_at = property(lambda s: s._closed_at)
    feedback = property(lambda s: s._feedback)
    escalation_level = property(lambda s: s._escalation_level)
    related_incidents = property(lambda s: frozenset(s._related))
    reopen_count = property(lambda s: s._reopen_count)

    def current_resolution(self) -> Resolution | None:
        return self._resolutions[-1] if self._resolved_at and self._resolutions else None

    def allowed_actions(self) -> list[Action]:
        """What the current STAGE allows, for anyone."""
        return self._state.allowed_actions()

    def actions_for(self, viewer: User) -> list[Action]:
        """
        The buttons THIS viewer should see: what the stage allows AND what this person may do
        (an employee never sees RESOLVE; only the reporter sees VERIFY/REOPEN; only the
        assignee or a lead sees ACKNOWLEDGE).
        """
        is_reporter = self._reporter == viewer
        is_assignee = self._assignee is not None and self._assignee == viewer
        lead = viewer.can(Permission.REASSIGN_INCIDENT)
        admin = viewer.can(Permission.CLOSE_INCIDENT)
        allowed = {
            Action.CLASSIFY: lead, Action.ASSIGN: lead,
            Action.ACKNOWLEDGE: viewer.can(Permission.WORK_INCIDENT) and (is_assignee or lead),
            Action.START_WORK: viewer.can(Permission.WORK_INCIDENT) and (is_assignee or lead),
            Action.RESOLVE: viewer.can(Permission.WORK_INCIDENT) and (is_assignee or lead),
            Action.REQUEST_INFO: viewer.can(Permission.REQUEST_INFO) and (is_assignee or lead),
            Action.PROVIDE_INFO: is_reporter,
            Action.VERIFY: is_reporter or admin, Action.REOPEN: is_reporter or admin,
            Action.CLOSE: is_reporter or admin,
        }
        return [a for a in self.allowed_actions() if allowed[a]]

    def visible_notes(self, viewer: User) -> list[Note]:
        """Employees never see internal technician notes."""
        staff = viewer.can(Permission.WORK_INCIDENT) or viewer.can(Permission.VIEW_ALL_INCIDENTS)
        return [n for n in self._notes if staff or not n.internal]

    # ═════════════════════════ internal helpers ═════════════════════════════
    def _stakeholders(self, *extra: str) -> tuple[str, ...]:
        ids = [self._reporter.user_id]
        if self._assignee:
            ids.append(self._assignee.user_id)
        return tuple(ids) + extra

    def _emit(self, etype: EventType, actor: User, now: datetime, text: str, prev: str | None = None,
              new: str | None = None, recipients: tuple[str, ...] = (), urgent: bool = False) -> None:
        self._pending.append(DomainEvent(etype, self._id, actor.user_id, now, text, prev, new,
                                         tuple(recipients), urgent or self._priority == Priority.P1))

    def _checked_next(self, action: Action) -> IncidentState:
        if not self._state.allows(action):
            allowed = [a.name for a in self.allowed_actions()]
            raise InvalidStateTransitionError(
                f"Cannot {action.value.replace('_', ' ')} {self._id} while it is {self.status}. "
                f"Allowed now: {allowed}.")
        return self._state.next(action)

    def _transition(self, action: Action, actor: User, now: datetime, etype: EventType,
                    text: str, recipients: tuple[str, ...] = ()) -> None:
        """Ask the current state for the next one (raises if illegal); keep the SLA clock in sync."""
        prev = self._state
        self._state = self._checked_next(action)
        if self._sla:
            if self._state.sla_running:
                self._sla.resume(now)
            elif self._state is States.AWAITING_INFO:
                self._sla.pause(now)
        self._emit(etype, actor, now, text, prev.name, self._state.name, recipients)

    def _require_assignee_or_lead(self, actor: User) -> None:
        is_assignee = self._assignee is not None and self._assignee == actor
        if not is_assignee and not actor.can(Permission.REASSIGN_INCIDENT):
            raise UnauthorizedOperationError(f"Only the assigned technician can do this on {self._id}.")

    def _require_reporter_or_admin(self, actor: User) -> None:
        if actor != self._reporter and not actor.can(Permission.CLOSE_INCIDENT):
            raise UnauthorizedOperationError(f"Only the reporter or an administrator can do this on {self._id}.")

    def pull_events(self) -> list[DomainEvent]:
        """Hand pending events to the ServiceDesk, which publishes them after saving."""
        events, self._pending = self._pending, []
        return events

    # ═════════════════════════ lifecycle operations ═════════════════════════
    def record_creation(self, now: datetime) -> None:
        self._emit(EventType.INCIDENT_CREATED, self._reporter, now,
                   f"created by {self._reporter.role.name} {self._reporter.user_id}",
                   None, self._state.name, (self._reporter.user_id,))

    def classify(self, category: str, actor: User, now: datetime, confidence: float | None = None) -> None:
        cat = _require_text(category, "Category").upper()
        self._checked_next(Action.CLASSIFY)                  # validate before changing anything
        self._category, self._category_confidence = cat, confidence
        how = "" if confidence is None else f" (auto-suggested, {confidence:.0%} confidence)"
        self._transition(Action.CLASSIFY, actor, now, EventType.INCIDENT_CLASSIFIED, f"classified as {cat}{how}")

    def apply_priority(self, priority: Priority, explanation: dict, policy: SLAPolicy,
                       actor: User, now: datetime) -> None:
        """Sets priority and (first time) starts the SLA clock; later calls re-prioritise."""
        old = self._priority
        self._priority = priority
        self._priority_explanation = dict(explanation)
        if self._sla is None:
            self._sla = SLAClock(policy, self._created_at)
            self._emit(EventType.PRIORITY_CALCULATED, actor, now,
                       f"priority calculated as {priority.name} (score {explanation.get('score')})")
        elif old != priority:
            self._sla.reprioritize(policy)
            if self._assignee:
                self._assignee.update_priority(self._id, priority)
            self._emit(EventType.PRIORITY_CHANGED, actor, now, f"priority changed {old.name} → {priority.name}",
                       recipients=self._stakeholders())

    def reassess(self, impact: Impact | None = None, urgency: Urgency | None = None,
                 affected_users: int | None = None) -> None:
        """Correct the assessment (e.g. more users turned out to be affected). Caller re-runs priority."""
        if not self.is_open:
            raise ValidationError(f"Cannot reassess a {self.status} incident.")
        if affected_users is not None and affected_users < 1:
            raise ValidationError("affected_users must be at least 1.")
        self._impact = impact or self._impact
        self._urgency = urgency or self._urgency
        self._affected_users = affected_users or self._affected_users

    def assign(self, technician: Technician, actor: User, now: datetime, reason: str = "") -> None:
        if self._priority is None:
            raise ValidationError("Priority must be calculated before assignment.")
        if technician == self._assignee:
            return                                          # already theirs
        self._checked_next(Action.ASSIGN)                   # validate first
        technician.take_incident(self._id, self._priority)  # may raise workload/availability errors
        if self._assignee:
            self._assignee.release_incident(self._id)
            self._previous_assignee = self._assignee
        self._assignee = technician
        self._assignment_reason = reason or ""
        self._transition(Action.ASSIGN, actor, now, EventType.INCIDENT_ASSIGNED,
                         f"assigned to Technician {technician.user_id}" + (f" — {reason}" if reason else ""),
                         (self._reporter.user_id, technician.user_id))

    def acknowledge(self, actor: User, now: datetime) -> None:
        actor.require(Permission.WORK_INCIDENT)
        self._require_assignee_or_lead(actor)
        self._transition(Action.ACKNOWLEDGE, actor, now, EventType.STATUS_CHANGED,
                         f"acknowledged by {actor.user_id}", (self._reporter.user_id,))
        if self._sla:
            self._sla.mark_responded(now)

    def start_work(self, actor: User, now: datetime) -> None:
        actor.require(Permission.WORK_INCIDENT)
        self._require_assignee_or_lead(actor)
        self._transition(Action.START_WORK, actor, now, EventType.STATUS_CHANGED,
                         "investigation started", (self._reporter.user_id,))

    def add_note(self, actor: User, text: str, internal: bool, now: datetime) -> None:
        body = _require_text(text, "Note")
        if internal or actor != self._reporter:
            actor.require(Permission.WORK_INCIDENT)
        if not self.is_open:
            raise ValidationError(f"Cannot add notes to a {self.status} incident.")
        self._notes.append(Note(actor.user_id, body, now, internal))
        self._emit(EventType.NOTE_ADDED, actor, now, f"{'internal ' if internal else ''}note added by {actor.user_id}")

    def request_info(self, actor: User, question: str, now: datetime) -> None:
        actor.require(Permission.REQUEST_INFO)
        self._require_assignee_or_lead(actor)
        q = _require_text(question, "Question")
        self._checked_next(Action.REQUEST_INFO)
        self._notes.append(Note(actor.user_id, f"QUESTION: {q}", now))
        self._transition(Action.REQUEST_INFO, actor, now, EventType.INFO_REQUESTED,
                         f"more information requested (SLA paused): {q}", (self._reporter.user_id,))

    def provide_info(self, actor: User, info: str, now: datetime) -> None:
        if actor != self._reporter:
            raise UnauthorizedOperationError("Only the reporter can answer information requests.")
        a = _require_text(info, "Answer")
        self._checked_next(Action.PROVIDE_INFO)
        self._notes.append(Note(actor.user_id, f"ANSWER: {a}", now))
        self._transition(Action.PROVIDE_INFO, actor, now, EventType.INFO_PROVIDED,
                         "reporter provided information (SLA resumed)", self._stakeholders())

    def resolve(self, actor: User, fix: str, root_cause: str, preventive_action: str | None, now: datetime) -> None:
        actor.require(Permission.RESOLVE_INCIDENT)
        self._require_assignee_or_lead(actor)
        self._checked_next(Action.RESOLVE)
        r = Resolution(fix, root_cause, preventive_action or "", actor.user_id, now)
        self._resolutions.append(r)
        self._resolved_at = now
        self._transition(Action.RESOLVE, actor, now, EventType.INCIDENT_RESOLVED,
                         f"resolved — root cause: {r.root_cause}", self._stakeholders())
        if self._sla:
            self._sla.mark_resolved(now)
        if self._assignee:
            self._assignee.record_resolution(self._id, self._service.service_id)

    def verify(self, actor: User, now: datetime) -> None:
        self._require_reporter_or_admin(actor)
        self._transition(Action.VERIFY, actor, now, EventType.STATUS_CHANGED,
                         f"resolution verified by {actor.user_id}", self._stakeholders())

    def reopen(self, actor: User, reason: str, now: datetime) -> None:
        """The fix did not hold. The previous technician is remembered for sticky reassignment."""
        self._require_reporter_or_admin(actor)
        why = _require_text(reason, "Reopen reason")
        self._transition(Action.REOPEN, actor, now, EventType.INCIDENT_REOPENED, f"reopened: {why}",
                         self._stakeholders())
        self._reopen_count += 1
        self._resolved_at = None
        if self._sla:
            self._sla.reopen()
        self._previous_assignee, self._assignee = self._assignee, None   # workload was released at resolve

    def close(self, actor: User, now: datetime) -> None:
        self._require_reporter_or_admin(actor)
        self._transition(Action.CLOSE, actor, now, EventType.INCIDENT_CLOSED, "incident CLOSED", self._stakeholders())
        self._closed_at = now

    def give_feedback(self, actor: User, rating: int, comment: str | None, now: datetime) -> None:
        if actor != self._reporter:
            raise UnauthorizedOperationError("Only the reporter can give feedback.")
        if self.is_open:
            raise ValidationError("Feedback is only allowed after resolution.")
        self._feedback = Feedback(rating, comment or "", now)
        self._emit(EventType.FEEDBACK_GIVEN, actor, now, f"feedback {rating}/5 received")

    # ═════════════════════════ automation hooks ═════════════════════════════
    def link_related(self, other_id: str, actor: User, now: datetime, why: str) -> None:
        if other_id != self._id and other_id not in self._related:
            self._related.add(other_id)
            self._emit(EventType.INCIDENT_LINKED, actor, now, f"linked to {other_id} ({why})")

    def escalate(self, level: int, target: Role, target_users: list[str], actor: User, now: datetime) -> None:
        if level <= self._escalation_level:
            return
        self._escalation_level, self._escalated_to = level, target
        self._emit(EventType.INCIDENT_ESCALATED, actor, now, f"escalated to level {level} ({target.name})",
                   recipients=tuple(target_users) + self._stakeholders(), urgent=True)

    def record_system_event(self, etype: EventType, text: str, actor: User, now: datetime,
                            recipients: list[str], urgent: bool) -> None:
        self._emit(etype, actor, now, text, recipients=tuple(recipients), urgent=urgent)

    # ═════════════════════════ persistence ══════════════════════════════════
    def to_record(self) -> IncidentRecord:
        """Flatten to plain data for the database."""
        sla, fb = self._sla, self._feedback
        return IncidentRecord(
            self._id, self._title, self._description, self._reporter.user_id, self._service.service_id,
            self._impact.name, self._urgency.name, self._affected_users, self._created_at,
            self.status, self._category, self._category_confidence,
            self._priority.name if self._priority else None, dict(self._priority_explanation),
            self._assignee.user_id if self._assignee else None,
            self._previous_assignee.user_id if self._previous_assignee else None, self._assignment_reason,
            self._resolved_at, self._closed_at,
            fb.rating if fb else None, fb.comment if fb else None, fb.at if fb else None,
            self._escalation_level, self._escalated_to.name if self._escalated_to else None,
            tuple(sorted(self._related)), self._reopen_count,
            sla.paused_since if sla else None, sla.paused_total.total_seconds() if sla else 0.0,
            sla.responded_at if sla else None, sla.resolved_at if sla else None,
            bool(sla and sla.response_breached), bool(sla and sla.resolution_breached),
            bool(sla and sla.warning_sent), bool(sla and sla.breach_notified),
            tuple(self._notes), tuple(self._resolutions))

    @classmethod
    def restore(cls, r: IncidentRecord, users: Callable[[str], User],
                services: Callable[[str], ITService], sla_book: SLAPolicyBook) -> "Incident":
        """Rebuild from saved data. No events are emitted: nothing happened, we're just reloading."""
        i = cls(r.incident_id, r.title, r.description, users(r.reporter_id), services(r.service_id),
                Impact[r.impact], Urgency[r.urgency], r.affected_users, r.created_at)
        i._state = States.from_name(r.status)
        i._category, i._category_confidence = r.category, r.category_confidence
        i._priority = Priority[r.priority] if r.priority else None
        i._priority_explanation = dict(r.priority_explanation)
        if i._priority:
            i._sla = SLAClock.restore(sla_book.policy_for(i._priority, r.service_id), r.created_at,
                                      r.sla_paused_since, timedelta(seconds=r.sla_paused_seconds),
                                      r.sla_responded_at, r.sla_resolved_at, r.sla_response_breached,
                                      r.sla_resolution_breached, r.sla_warning_sent, r.sla_breach_notified)
        i._assignee = users(r.assignee_id) if r.assignee_id else None
        i._previous_assignee = users(r.previous_assignee_id) if r.previous_assignee_id else None
        i._assignment_reason = r.assignment_reason or ""
        i._resolved_at, i._closed_at = r.resolved_at, r.closed_at
        i._feedback = Feedback(r.feedback_rating, r.feedback_comment or "", r.feedback_at) if r.feedback_rating else None
        i._escalation_level = r.escalation_level
        i._escalated_to = Role[r.escalated_to] if r.escalated_to else None
        i._related = set(r.related_incidents)
        i._reopen_count = r.reopen_count
        i._notes = list(r.notes)
        i._resolutions = list(r.resolutions)
        return i

    # ═════════════════════════ API output ═══════════════════════════════════
    def to_dict(self, now: datetime, viewer: User | None = None) -> dict:
        """
        JSON-ready dict for the API. Pass the logged-in user as `viewer` to also get
        "yourActions" (the buttons THIS person may press).
        """
        res = self.current_resolution()
        d = {
            "incidentId": self._id, "title": self._title, "description": self._description,
            "reporterId": self._reporter.user_id, "serviceId": self._service.service_id,
            "serviceName": self._service.name, "category": self._category,
            "categoryConfidence": self._category_confidence, "impact": self._impact.name,
            "urgency": self._urgency.name, "affectedUsers": self._affected_users,
            "priority": self._priority.name if self._priority else None,
            "priorityExplanation": dict(self._priority_explanation), "status": self.status,
            "allowedActions": [a.name for a in self.allowed_actions()],
            "assignedTo": self._assignee.user_id if self._assignee else None,
            "assignmentReason": self._assignment_reason,
            "sla": self._sla.to_dict(now) if self._sla else None,
            "resolution": res.description if res else None, "rootCause": res.root_cause if res else None,
            "createdAt": both_times(self._created_at), "createdAtIso": self._created_at.isoformat(),
            "resolvedAt": both_times(self._resolved_at) if self._resolved_at else None,
            "closedAt": both_times(self._closed_at) if self._closed_at else None,
            "escalationLevel": self._escalation_level,
            "escalatedTo": self._escalated_to.name if self._escalated_to else None,
            "relatedIncidents": sorted(self._related), "reopenCount": self._reopen_count,
            "feedbackRating": self._feedback.rating if self._feedback else None,
        }
        if viewer is not None:
            d["yourActions"] = [a.name for a in self.actions_for(viewer)]
            if not viewer.can(Permission.WORK_INCIDENT) and not viewer.can(Permission.VIEW_ALL_INCIDENTS):
                d.pop("assignmentReason")                     # internal detail employees don't need
        return d

    def __repr__(self) -> str:
        return f"Incident({self._id} {self._priority.name if self._priority else '--'} {self.status} '{self._title}')"
