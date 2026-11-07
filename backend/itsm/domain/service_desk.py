"""
FACADE: ServiceDesk is the single entry point into the domain.

Member 3's API routes call ONLY these methods, e.g. with FastAPI:

    @app.post("/api/incidents", status_code=201)
    def report(body: ReportBody, user: User = Depends(current_user)):
        incident = desk.report_incident(user, IncidentRequest.builder(body.title, body.description)
                                              .impact(body.impact).urgency(body.urgency).build())
        return incident.to_dict(desk.now(), user)

report_incident() runs the full 14-step scenario from the project brief. Every public
method is thread-safe (one re-entrant lock), so a web server can share one ServiceDesk.
"""
from __future__ import annotations

import functools
import threading
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable

from .assignment import AssignmentStrategy, Candidate, SmartRecommendationAssignment, assignment_strategy_by_name
from .catalog import Category, CategoryRegistry, ITService, ServiceCatalog
from .common import (Clock, EventType, Impact, Permission, Priority, Role, ServiceHealth, SLAStatus,
                     SystemClock, Urgency)
from .escalation import EscalationPolicy
from .events import AuditLog, DomainEvent, EventBus
from .exceptions import (AuthenticationError, DuplicateIncidentError, IncidentNotFoundError,
                         TechnicianUnavailableError, UnauthorizedOperationError, UserNotFoundError,
                         ValidationError)
from .factory import IncidentFactory, parse_enum
from .incident import Incident
from .intelligence import (BlastRadius, Correlation, DuplicateDetector, IncidentCorrelator,
                           KeywordDuplicateDetector, ResolutionSuggester, SLARisk, SLARiskAnalyzer,
                           Suggestion, WhatIfSimulator)
from .notifications import EmailChannel, InAppChannel, Notification, NotificationChannel, NotificationService
from .persistence import NoStorage, ServiceRecord, StorageAdapter, UserRecord
from .priority import PriorityStrategy, WeightedScorePriorityStrategy, priority_strategy_by_name
from .repository import IncidentRepository, InMemoryIncidentRepository, InMemoryUserRepository, UserRepository
from .sla import SLAPolicy, SLAPolicyBook
from .users import SystemAccount, Technician, User


# ═════════════════════════════ request (BUILDER) ════════════════════════════════
@dataclass(frozen=True)
class IncidentRequest:
    """
    What a user submits. Build it fluently, setting only what you know:
        IncidentRequest.builder("Payment down", "Users cannot pay…").impact("ORGANIZATION")
                       .urgency("CRITICAL").affected_users(600).build()
    """
    title: str
    description: str
    service_id: str | None = None
    impact: str = "MEDIUM"
    urgency: str = "MEDIUM"
    affected_users: int = 1
    category: str | None = None
    block_duplicates: bool = False
    auto_assign: bool = True

    @staticmethod
    def builder(title: str, description: str) -> "IncidentRequest.Builder":
        return IncidentRequest.Builder(title, description)

    class Builder:
        def __init__(self, title: str, description: str):
            self._v = {"title": title, "description": description}

        def service(self, service_id: str | None): self._v["service_id"] = service_id; return self
        def impact(self, value: str): self._v["impact"] = value; return self
        def urgency(self, value: str): self._v["urgency"] = value; return self
        def affected_users(self, n: int): self._v["affected_users"] = n; return self
        def category(self, c: str | None): self._v["category"] = c; return self
        def block_duplicates(self): self._v["block_duplicates"] = True; return self
        def manual_assignment(self): self._v["auto_assign"] = False; return self

        def build(self) -> "IncidentRequest":
            return IncidentRequest(**self._v)


# ═════════════════════════════ search (BUILDER) ═════════════════════════════════
class SearchCriteria:
    """
    Search filters combined with AND, built fluently:
        SearchCriteria.where().priority("P1").category("NETWORK").open_only()
    Each method adds one predicate; criteria you don't set simply aren't applied.
    """

    def __init__(self):
        self._filters: list[Callable[[Incident], bool]] = []
        self._sla_status: str | None = None

    @classmethod
    def where(cls) -> "SearchCriteria":
        return cls()

    def _add(self, f) -> "SearchCriteria":
        self._filters.append(f)
        return self

    def incident_id(self, v): return self._add(lambda i: i.incident_id.upper() == v.upper())
    def status(self, v): return self._add(lambda i: i.status == v.upper())
    def priority(self, v): return self._add(lambda i: i.priority is not None and i.priority.name == v.upper())
    def category(self, v): return self._add(lambda i: (i.category or "") == v.upper())
    def service(self, sid): return self._add(lambda i: i.service.service_id == sid)
    def technician(self, tid): return self._add(lambda i: i.assignee is not None and i.assignee.user_id == tid)
    def reporter(self, uid): return self._add(lambda i: i.reporter.user_id == uid)
    def created_from(self, t: datetime): return self._add(lambda i: i.created_at >= t)
    def created_to(self, t: datetime): return self._add(lambda i: i.created_at <= t)
    def text(self, q): return self._add(lambda i: q.lower() in f"{i.title} {i.description}".lower())
    def open_only(self): return self._add(lambda i: i.is_open)
    def escalated(self): return self._add(lambda i: i.escalation_level > 0)

    def sla_status(self, v: str) -> "SearchCriteria":
        """SLA status depends on 'now', so the desk evaluates it at search time."""
        self._sla_status = v.upper()
        return self

    def matches(self, incident: Incident, now: datetime) -> bool:
        if not all(f(incident) for f in self._filters):
            return False
        if self._sla_status:
            return incident.sla is not None and incident.sla.status(now).name == self._sla_status
        return True


# ═════════════════════════════ reports ══════════════════════════════════════════
@dataclass(frozen=True)
class Overview:
    total_incidents: int
    open_incidents: int
    critical_open: int
    resolved_incidents: int
    sla_violations: int
    sla_compliance_percent: float
    mean_time_to_acknowledge_minutes: float
    mean_time_to_resolve_minutes: float
    average_feedback: float | None
    by_status: dict
    by_priority: dict


@dataclass(frozen=True)
class TechnicianWorkload:
    technician_id: str
    name: str
    active_incidents: int
    workload_points: int
    max_points: int
    resolved: int
    available: bool


@dataclass(frozen=True)
class ServiceAnalysis:
    service_id: str
    service_name: str
    total_incidents: int
    open_incidents: int
    health: ServiceHealth


@dataclass(frozen=True)
class MonitorResult:
    warnings: list = field(default_factory=list)
    breaches: list = field(default_factory=list)
    escalations: list = field(default_factory=list)     # (incident id, Role)
    auto_closed: list = field(default_factory=list)


def _synchronized(method):
    """Run the method while holding the desk's lock (safe for many web requests at once)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


# ═════════════════════════════ the facade ═══════════════════════════════════════
class ServiceDesk:
    MAX_FAILED_LOGINS = 5
    LOCKOUT_WINDOW = timedelta(minutes=15)

    def __init__(self, clock: Clock | None = None, incidents: IncidentRepository | None = None,
                 users: UserRepository | None = None):
        self._lock = threading.RLock()
        self._clock = clock or SystemClock()
        self._catalog = ServiceCatalog()
        self._categories = CategoryRegistry.with_defaults()
        self._sla_book = SLAPolicyBook.with_defaults()
        self._incidents = incidents or InMemoryIncidentRepository()
        self._users = users or InMemoryUserRepository()
        self._system = SystemAccount()
        self._factory = IncidentFactory(self._catalog, self._clock)
        self._storage: StorageAdapter = NoStorage()
        self._auto_close_after = timedelta(hours=72)
        self._failed_logins: dict[str, deque] = {}

        self._priority_strategy: PriorityStrategy = WeightedScorePriorityStrategy()
        self._assignment_strategy: AssignmentStrategy = SmartRecommendationAssignment()
        self._duplicates: DuplicateDetector = KeywordDuplicateDetector()
        self._escalation = EscalationPolicy()
        self._correlator = IncidentCorrelator(self._catalog)
        self._risk = SLARiskAnalyzer()
        self._resolution_suggester = ResolutionSuggester()
        self._what_if = WhatIfSimulator(self._catalog)

        # Observer wiring
        self._bus = EventBus()
        self._audit = AuditLog()
        self._notifier = NotificationService(self._lookup_user)
        self._notifier.register_channel(InAppChannel())
        self._notifier.register_channel(EmailChannel())
        self._bus.subscribe(self._audit)       # observer 1: audit trail
        self._bus.subscribe(self._notifier)    # observer 2: notifications

    # ─────────────────────────── infrastructure ───────────────────────────────
    def now(self) -> datetime:
        return self._clock.now()

    catalog = property(lambda s: s._catalog)
    categories = property(lambda s: s._categories)
    audit = property(lambda s: s._audit)
    factory = property(lambda s: s._factory)
    assignment_strategy = property(lambda s: s._assignment_strategy)
    priority_strategy = property(lambda s: s._priority_strategy)

    def subscribe(self, observer) -> None:
        """Extra observers, e.g. a WebSocket pusher. Any function taking a DomainEvent works."""
        self._bus.subscribe(observer)

    def add_notification_channel(self, channel: NotificationChannel) -> None:
        self._notifier.register_channel(channel)

    def channel(self, name: str) -> NotificationChannel:
        return self._notifier.channel(name)

    def set_duplicate_detector(self, detector: DuplicateDetector) -> None:
        self._duplicates = detector

    def _lookup_user(self, user_id: str) -> User | None:
        return self._system if user_id == SystemAccount.ID else self._users.find_by_id(user_id)

    @_synchronized
    def user(self, user_id: str) -> User:
        u = self._lookup_user(user_id)
        if u is None:
            raise UserNotFoundError(f"User '{user_id}' not found.")
        return u

    def _find(self, incident_id: str) -> Incident:
        inc = self._incidents.find_by_id(incident_id)
        if inc is None:
            raise IncidentNotFoundError(f"Incident '{incident_id}' not found.")
        return inc

    def _commit(self, incident: Incident) -> Incident:
        """Save, then publish pending events, so observers always see saved state."""
        self._incidents.save(incident)
        self._storage.save_incident(incident.to_record())
        for event in incident.pull_events():
            self._bus.publish(event)
        return incident

    def _ids_of(self, *roles: Role) -> list[str]:
        return [u.user_id for r in roles for u in self._users.by_role(r)]

    def _persist(self, user: User) -> None:
        self._storage.save_user(UserRecord.from_user(user))

    # ─────────────────────────── persistence ──────────────────────────────────
    @_synchronized
    def attach_storage(self, adapter: StorageAdapter) -> None:
        """
        Connect a database (Member 3's StorageAdapter) and reload everything saved in it.
        Call once at startup. From then on every change is saved automatically.
        Order matters: SLA → categories → services → users → incidents → workloads → audit.
        """
        self._storage = adapter
        for p in adapter.load_sla_policies():
            self._sla_book.add(p)
        for c in adapter.load_categories():
            self._categories.register(c)
        services = adapter.load_services()
        for r in services:
            self._catalog.add(r.to_service_without_dependencies())
        for r in services:
            for up in r.depends_on:
                self._catalog.add_dependency(r.service_id, up)
        for r in adapter.load_users():
            self._users.save(r.to_user())
        for r in adapter.load_incidents():
            inc = Incident.restore(r, self.user, self._catalog.get, self._sla_book)
            self._incidents.save(inc)
            self._factory.continue_after(inc.incident_id)
        self._rebuild_technician_stats()
        self._audit.restore(adapter.load_audit_events())
        self._bus.subscribe(adapter.save_audit_event)       # keep the audit trail flowing to the DB

    def _rebuild_technician_stats(self) -> None:
        """Workload and history are derived from incidents, so they never drift out of sync."""
        for t in self._users.technicians():
            history: Counter = Counter()
            resolved = 0
            for i in self._incidents.find_all():
                for r in i.resolutions:
                    if r.technician_id == t.user_id:
                        resolved += 1
                        history[i.service.service_id] += 1
            t.restore_history(resolved, dict(history))
        for i in self._incidents.find_open():
            if i.assignee:
                i.assignee.restore_workload(i.incident_id, i.priority)

    @_synchronized
    def is_empty(self) -> bool:
        """True on the very first run (use it to decide whether to seed sample data)."""
        return not self._users.find_all()

    # ─────────────────────────── authentication ───────────────────────────────
    @_synchronized
    def login(self, email: str, password: str) -> User:
        """
        Same error for "no such user" and "wrong password" (doesn't reveal which emails exist).
        After 5 failures in 15 minutes the account is temporarily locked.
        """
        key = (email or "").strip().lower()
        now = self.now()
        fails = self._failed_logins.setdefault(key, deque())
        while fails and fails[0] < now - self.LOCKOUT_WINDOW:
            fails.popleft()
        if len(fails) >= self.MAX_FAILED_LOGINS:
            raise AuthenticationError("Too many failed attempts. Try again in 15 minutes.")
        user = self._users.find_by_email(key)
        if user is None or not user.check_password(password):
            fails.append(now)
            raise AuthenticationError("Invalid email or password.")
        fails.clear()
        return user

    @_synchronized
    def change_password(self, user: User, old_password: str, new_password: str) -> None:
        user.change_password(old_password, new_password)
        self._persist(user)

    # ─────────────────────────── administration ───────────────────────────────
    @_synchronized
    def register_user_bootstrap(self, first_admin: User) -> None:
        """First-run setup: create the initial administrator when no users exist yet."""
        if self._users.find_all():
            raise UnauthorizedOperationError("Bootstrap is only allowed on an empty system.")
        first_admin.require(Permission.MANAGE_USERS)
        self._users.save(first_admin)
        self._persist(first_admin)

    @_synchronized
    def register_user(self, admin: User, new_user: User) -> User:
        admin.require(Permission.MANAGE_USERS)
        if self._users.find_by_id(new_user.user_id):
            raise ValidationError(f"User id {new_user.user_id} already exists.")
        if self._users.find_by_email(new_user.email):
            raise ValidationError(f"Email {new_user.email} is already registered.")
        self._users.save(new_user)
        self._persist(new_user)
        return new_user

    @_synchronized
    def deactivate_user(self, admin: User, user_id: str) -> None:
        admin.require(Permission.MANAGE_USERS)
        u = self.user(user_id)
        if u == admin:
            raise ValidationError("You cannot deactivate your own account.")
        u.deactivate()
        self._persist(u)

    def _technician(self, user_id: str) -> Technician:
        u = self.user(user_id)
        if not isinstance(u, Technician):
            raise ValidationError(f"{user_id} is not a technician.")
        return u

    @_synchronized
    def update_technician_skills(self, admin: User, technician_id: str, skills: dict[str, int]) -> None:
        """Admin "manage technicians": replace a technician's skills."""
        admin.require(Permission.MANAGE_USERS)
        t = self._technician(technician_id)
        t.replace_skills(skills)
        self._persist(t)

    @_synchronized
    def set_availability(self, actor: User, technician_id: str, available: bool) -> None:
        """A technician marks themselves away/back; admins and team leads can do it for anyone."""
        t = self._technician(technician_id)
        if actor != t and not actor.can(Permission.MANAGE_USERS) and not actor.can(Permission.REASSIGN_INCIDENT):
            raise UnauthorizedOperationError(f"You cannot change {technician_id}'s availability.")
        t.set_available(available)
        self._persist(t)

    @_synchronized
    def add_service(self, admin: User, service: ITService) -> None:
        admin.require(Permission.MANAGE_SERVICES)
        self._catalog.add(service)
        self._storage.save_service(ServiceRecord.from_service(service))

    @_synchronized
    def add_dependency(self, admin: User, service_id: str, depends_on_id: str) -> None:
        admin.require(Permission.MANAGE_SERVICES)
        self._catalog.add_dependency(service_id, depends_on_id)
        self._storage.save_service(ServiceRecord.from_service(self._catalog.get(service_id)))

    @_synchronized
    def add_category(self, admin: User, name: str, keywords, description: str = "") -> None:
        admin.require(Permission.CONFIGURE_CATEGORIES)
        c = Category(name, description, keywords)
        self._categories.register(c)
        self._storage.save_category(c)

    @_synchronized
    def configure_sla(self, admin: User, policy: SLAPolicy) -> None:
        admin.require(Permission.CONFIGURE_SLA)
        self._sla_book.add(policy)
        self._storage.save_sla_policy(policy)

    @_synchronized
    def configure_escalation(self, admin: User, priority: Priority, team_lead_min: int,
                             sys_admin_min: int, manager_min: int) -> None:
        admin.require(Permission.CONFIGURE_SLA)
        self._escalation.configure(priority, team_lead_min, sys_admin_min, manager_min)

    @_synchronized
    def set_auto_close_after(self, admin: User, after: timedelta) -> None:
        """Resolved incidents the reporter never verifies close automatically after this long."""
        admin.require(Permission.CONFIGURE_SLA)
        if after <= timedelta(0):
            raise ValidationError("Auto-close period must be positive.")
        self._auto_close_after = after

    @_synchronized
    def set_assignment_strategy(self, admin: User, strategy: str | AssignmentStrategy) -> None:
        admin.require(Permission.CONFIGURE_STRATEGY)
        self._assignment_strategy = (assignment_strategy_by_name(strategy) if isinstance(strategy, str)
                                     else strategy)

    @_synchronized
    def set_priority_strategy(self, admin: User, name: str) -> None:
        admin.require(Permission.CONFIGURE_STRATEGY)
        self._priority_strategy = priority_strategy_by_name(name)

    # ─────────────────────────── main workflow ────────────────────────────────
    @_synchronized
    def report_incident(self, reporter: User, req: IncidentRequest) -> Incident:
        """
        The 14-step scenario: create → classify → identify service → business impact →
        priority → SLA → find technicians → assign → notify → (track) → (monitor SLA) →
        record everything → (close) → (reports).
        """
        reporter.require(Permission.REPORT_INCIDENT)
        now = self.now()
        if req.category:
            self._categories.get(req.category)      # validate BEFORE consuming an ID

        # Steps 1, 3, 4: create; affected service given or guessed; impact captured
        inc = self._factory.create(reporter, req.title, req.description, req.service_id,
                                   req.impact, req.urgency, req.affected_users)

        # Duplicate check before spending a technician on it
        dupes = self._duplicates.find_duplicates(inc, self._incidents.find_open())
        if dupes and req.block_duplicates:
            self._factory.discard(inc.incident_id)
            raise DuplicateIncidentError(dupes[0].incident_id, dupes[0].score)
        inc.record_creation(now)

        # Step 2: classify (user's choice → auto-suggestion → service default)
        if req.category:
            inc.classify(req.category, reporter, now)
        else:
            s = self._categories.suggest(f"{req.title} {req.description}")
            if s:
                inc.classify(s.category, self._system, now, s.confidence)
            else:
                inc.classify(inc.service.default_category, self._system, now)

        # Steps 5, 6: priority + SLA
        self._apply_priority(inc, now)

        # Link likely duplicates both ways
        for d in dupes:
            inc.link_related(d.incident_id, self._system, now, f"possible duplicate, {d.reason} {d.score}")
            other = self._find(d.incident_id)
            other.link_related(inc.incident_id, self._system, now, "possible duplicate")
            self._commit(other)

        # Steps 7, 8, 9: find a technician, assign, notify (through events)
        if req.auto_assign:
            try:
                self._auto_assign(inc, now)
            except TechnicianUnavailableError as e:
                inc.record_system_event(EventType.SYSTEM_NOTICE, f"auto-assignment failed: {e.message}",
                                        self._system, now, self._ids_of(Role.TEAM_LEAD), True)
        return self._commit(inc)            # step 12: every step above is now in the audit trail

    def _apply_priority(self, inc: Incident, now: datetime) -> None:
        r = self._priority_strategy.calculate(inc.impact, inc.urgency, inc.service, inc.affected_users)
        policy = self._sla_book.policy_for(r.priority, inc.service.service_id)
        inc.apply_priority(r.priority, r.explanation, policy, self._system, now)

    def _auto_assign(self, inc: Incident, now: datetime) -> None:
        c = self._assignment_strategy.select(inc, self._users.technicians())
        inc.assign(c.technician, self._system, now,
                   f"{self._assignment_strategy.name} strategy: " + ", ".join(c.reasons))

    @_synchronized
    def get_incident(self, viewer: User, incident_id: str) -> Incident:
        inc = self._find(incident_id)
        mine = inc.reporter == viewer or (inc.assignee is not None and inc.assignee == viewer)
        if not mine and not viewer.can(Permission.VIEW_ALL_INCIDENTS):
            raise UnauthorizedOperationError(f"You cannot view {incident_id}.")
        return inc

    @_synchronized
    def recommend_technicians(self, viewer: User, incident_id: str, top: int = 3) -> list[Candidate]:
        inc = self.get_incident(viewer, incident_id)
        return self._assignment_strategy.rank(inc, self._users.technicians())[:top]

    @_synchronized
    def assign_manually(self, actor: User, incident_id: str, technician_id: str) -> Incident:
        actor.require(Permission.REASSIGN_INCIDENT)
        inc = self._find(incident_id)
        inc.assign(self._technician(technician_id), actor, self.now(), f"manual assignment by {actor.user_id}")
        return self._commit(inc)

    @_synchronized
    def reassess(self, actor: User, incident_id: str, impact: str | None = None,
                 urgency: str | None = None, affected_users: int | None = None) -> Incident:
        actor.require(Permission.REASSIGN_INCIDENT)
        inc = self._find(incident_id)
        inc.reassess(parse_enum(Impact, impact, "impact") if impact else None,
                     parse_enum(Urgency, urgency, "urgency") if urgency else None, affected_users)
        self._apply_priority(inc, self.now())
        return self._commit(inc)

    def _act(self, incident_id: str, action: Callable[[Incident, datetime], None]) -> Incident:
        inc = self._find(incident_id)
        action(inc, self.now())
        return self._commit(inc)

    @_synchronized
    def acknowledge(self, user: User, incident_id: str) -> Incident:
        return self._act(incident_id, lambda i, t: i.acknowledge(user, t))

    @_synchronized
    def start_work(self, user: User, incident_id: str) -> Incident:
        return self._act(incident_id, lambda i, t: i.start_work(user, t))

    @_synchronized
    def add_note(self, user: User, incident_id: str, text: str, internal: bool = False) -> Incident:
        return self._act(incident_id, lambda i, t: i.add_note(user, text, internal, t))

    @_synchronized
    def request_info(self, user: User, incident_id: str, question: str) -> Incident:
        return self._act(incident_id, lambda i, t: i.request_info(user, question, t))

    @_synchronized
    def provide_info(self, user: User, incident_id: str, answer: str) -> Incident:
        return self._act(incident_id, lambda i, t: i.provide_info(user, answer, t))

    @_synchronized
    def resolve(self, user: User, incident_id: str, fix: str, root_cause: str,
                preventive_action: str | None = None) -> Incident:
        return self._act(incident_id, lambda i, t: i.resolve(user, fix, root_cause, preventive_action, t))

    @_synchronized
    def verify(self, user: User, incident_id: str) -> Incident:
        return self._act(incident_id, lambda i, t: i.verify(user, t))

    @_synchronized
    def close(self, user: User, incident_id: str) -> Incident:
        return self._act(incident_id, lambda i, t: i.close(user, t))

    @_synchronized
    def give_feedback(self, user: User, incident_id: str, rating: int, comment: str = "") -> Incident:
        return self._act(incident_id, lambda i, t: i.give_feedback(user, rating, comment, t))

    @_synchronized
    def reopen(self, user: User, incident_id: str, reason: str) -> Incident:
        """
        Reopen, then STICKY REASSIGNMENT: the technician who knows the incident gets it back if
        they have capacity; otherwise the normal strategy picks someone else.
        """
        inc = self._find(incident_id)
        now = self.now()
        inc.reopen(user, reason, now)
        prev = inc.previous_assignee
        try:
            if prev and prev.has_capacity_for(inc.priority):
                inc.assign(prev, self._system, now, "sticky reassignment: worked on it before")
            else:
                self._auto_assign(inc, now)
        except TechnicianUnavailableError as e:
            inc.record_system_event(EventType.SYSTEM_NOTICE, f"reassignment failed: {e.message}",
                                    self._system, now, self._ids_of(Role.TEAM_LEAD), True)
        return self._commit(inc)

    # ─────────────────────────── background monitoring ────────────────────────
    @_synchronized
    def run_monitor(self) -> MonitorResult:
        """
        Call every minute from a background job (Member 3: APScheduler or a FastAPI
        background task). Sends each SLA warning/breach once, escalates, and auto-closes.
        """
        now = self.now()
        result = MonitorResult()
        managers = self._ids_of(Role.TEAM_LEAD, Role.IT_MANAGER)

        for inc in self._incidents.find_all():
            if inc.status == "RESOLVED" and inc.resolved_at and inc.resolved_at + self._auto_close_after <= now:
                inc.close(self._system, now)
                result.auto_closed.append(inc.incident_id)
                self._commit(inc)

        for inc in self._incidents.find_open():
            sla = inc.sla
            if sla is None:
                continue
            status = sla.status(now)
            recipients = managers + ([inc.assignee.user_id] if inc.assignee else [])
            if status == SLAStatus.AT_RISK and not sla.warning_sent:
                sla.mark_warning_sent()
                inc.record_system_event(EventType.SLA_WARNING,
                                        f"SLA warning: {sla.used_fraction(now):.0%} of resolution time used",
                                        self._system, now, recipients, False)
                result.warnings.append(inc.incident_id)
            elif status == SLAStatus.BREACHED and not sla.breach_notified:
                sla.mark_breach_notified()
                inc.record_system_event(EventType.SLA_BREACHED, f"SLA VIOLATED for {inc.priority.name}",
                                        self._system, now, recipients, True)
                result.breaches.append(inc.incident_id)
            target = self._escalation.evaluate(inc, now)
            if target:
                inc.escalate(target.level, target.role, self._ids_of(target.role), self._system, now)
                result.escalations.append((inc.incident_id, target.role))
            self._commit(inc)
        return result

    # ─────────────────────────── intelligence ─────────────────────────────────
    @_synchronized
    def correlations(self, viewer: User) -> list[Correlation]:
        viewer.require(Permission.VIEW_REPORTS)
        return self._correlator.correlate(self._incidents.find_open())

    @_synchronized
    def sla_risks(self, viewer: User) -> list[SLARisk]:
        viewer.require(Permission.VIEW_REPORTS)
        now = self.now()
        risks = [r for i in self._incidents.find_open() if (r := self._risk.assess(i, now))]
        return sorted(risks, key=lambda r: -r.risk)

    @_synchronized
    def suggest_resolutions(self, viewer: User, incident_id: str) -> list[Suggestion]:
        inc = self.get_incident(viewer, incident_id)
        history = [i for i in self._incidents.find_all() if i.resolutions]
        return self._resolution_suggester.suggest(inc, history)

    @_synchronized
    def simulate_failure(self, viewer: User, service_id: str) -> BlastRadius:
        viewer.require(Permission.VIEW_REPORTS)
        return self._what_if.simulate_failure(service_id)

    # ─────────────────────────── search, views & reports ──────────────────────
    @_synchronized
    def search(self, viewer: User, criteria: SearchCriteria) -> list[Incident]:
        now = self.now()
        see_all = viewer.can(Permission.VIEW_ALL_INCIDENTS)
        hits = [i for i in self._incidents.find_all()
                if (see_all or i.reporter == viewer or (i.assignee is not None and i.assignee == viewer))
                and criteria.matches(i, now)]
        return sorted(hits, key=lambda i: (i.priority.rank if i.priority else 9, i.created_at))

    @_synchronized
    def my_queue(self, technician: Technician) -> list[Incident]:
        """Technician workspace: my open incidents, most urgent first (priority, then SLA time left)."""
        now = self.now()
        mine = [i for i in self._incidents.find_open() if i.assignee is not None and i.assignee == technician]
        return sorted(mine, key=lambda i: (i.priority.rank, i.sla.time_remaining(now) if i.sla else timedelta(0)))

    @_synchronized
    def my_incidents(self, reporter: User) -> list[Incident]:
        """Employee portal: everything I reported, newest first."""
        return sorted((i for i in self._incidents.find_all() if i.reporter == reporter),
                      key=lambda i: i.created_at, reverse=True)

    @_synchronized
    def sla_violations(self, viewer: User) -> list[Incident]:
        viewer.require(Permission.VIEW_REPORTS)
        return self.search(viewer, SearchCriteria.where().sla_status("BREACHED"))

    @_synchronized
    def all_audit_logs(self, viewer: User) -> list[DomainEvent]:
        """Admin: the system-wide audit log, newest first."""
        viewer.require(Permission.VIEW_AUDIT)
        return list(reversed(self._audit.all()))

    @_synchronized
    def audit_trail(self, viewer: User, incident_id: str) -> list[DomainEvent]:
        inc = self._find(incident_id)
        involved = inc.reporter == viewer or (inc.assignee is not None and inc.assignee == viewer)
        if not involved and not viewer.can(Permission.VIEW_AUDIT):
            raise UnauthorizedOperationError(f"You cannot view the audit trail of {incident_id}.")
        return self._audit.for_incident(incident_id)

    @_synchronized
    def notification_failures(self, viewer: User) -> list[str]:
        viewer.require(Permission.VIEW_REPORTS)
        return self._notifier.delivery_failures

    @_synchronized
    def inbox(self, user: User) -> list[Notification]:
        return self.channel("in_app").inbox(user.user_id)

    @_synchronized
    def overview(self, viewer: User) -> Overview:
        viewer.require(Permission.VIEW_REPORTS)
        now = self.now()
        everything = self._incidents.find_all()
        with_sla = [i for i in everything if i.sla]
        breached = sum(1 for i in with_sla if i.sla.status(now) == SLAStatus.BREACHED)
        resolved = [i for i in everything if i.resolved_at]
        acked = [i for i in with_sla if i.sla.responded_at]
        ratings = [i.feedback.rating for i in everything if i.feedback]

        def avg_minutes(items, end):
            return round(sum((end(i) - i.created_at).total_seconds() / 60 for i in items) / len(items), 1) if items else 0.0

        return Overview(
            total_incidents=len(everything),
            open_incidents=sum(1 for i in everything if i.is_open),
            critical_open=sum(1 for i in everything if i.is_open and i.priority == Priority.P1),
            resolved_incidents=len(resolved),
            sla_violations=breached,
            sla_compliance_percent=round(100 * (len(with_sla) - breached) / len(with_sla), 1) if with_sla else 100.0,
            mean_time_to_acknowledge_minutes=avg_minutes(acked, lambda i: i.sla.responded_at),
            mean_time_to_resolve_minutes=avg_minutes(resolved, lambda i: i.resolved_at),
            average_feedback=round(sum(ratings) / len(ratings), 2) if ratings else None,
            by_status=dict(sorted(Counter(i.status for i in everything).items())),
            by_priority=dict(sorted(Counter(i.priority.name for i in everything if i.priority).items())),
        )

    @_synchronized
    def technician_workload(self, viewer: User) -> list[TechnicianWorkload]:
        viewer.require(Permission.VIEW_REPORTS)
        techs = sorted(self._users.technicians(), key=lambda t: (-t.workload_points, t.user_id))
        return [TechnicianWorkload(t.user_id, t.name, t.active_count, t.workload_points,
                                   t.max_workload_points, t.resolved_count, t.is_available()) for t in techs]

    @_synchronized
    def service_analysis(self, viewer: User) -> list[ServiceAnalysis]:
        """Per-service counts + live health: DOWN if an open P1 hits it, DEGRADED if anything is open."""
        viewer.require(Permission.VIEW_REPORTS)
        everything = self._incidents.find_all()
        rows = []
        for s in self._catalog.all():
            mine = [i for i in everything if i.service is s]
            open_ = [i for i in mine if i.is_open]
            health = (ServiceHealth.DOWN if any(i.priority == Priority.P1 for i in open_)
                      else ServiceHealth.DEGRADED if open_ else ServiceHealth.OPERATIONAL)
            rows.append(ServiceAnalysis(s.service_id, s.name, len(mine), len(open_), health))
        return sorted(rows, key=lambda r: (-r.total_incidents, r.service_id))
