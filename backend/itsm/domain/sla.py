"""
SLA management.

SLAPolicy     : targets for one priority (optionally for one service).
SLAPolicyBook : finds the applicable policy; a service-specific one beats the default.
SLAClock      : per-incident timer with PAUSE/RESUME. While the technician waits for the
                reporter (AWAITING_INFO) the clock stops and both deadlines move forward.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .common import Priority, SLAStatus, both_times
from .exceptions import SLAConfigurationError, ValidationError


@dataclass(frozen=True)
class SLAPolicy:
    priority: Priority
    response_target: timedelta
    resolution_target: timedelta
    warning_threshold: float = 0.75     # warn when 75% of the time is used
    service_id: str | None = None       # None = the default for every service

    def __post_init__(self):
        if self.response_target <= timedelta(0) or self.resolution_target <= timedelta(0):
            raise ValidationError("SLA targets must be positive.")
        if self.response_target > self.resolution_target:
            raise ValidationError("Response target cannot exceed resolution target.")
        if not 0 < self.warning_threshold < 1:
            raise ValidationError("warning_threshold must be between 0 and 1.")


class SLAPolicyBook:
    def __init__(self):
        self._policies: dict[tuple[str | None, Priority], SLAPolicy] = {}

    def add(self, policy: SLAPolicy) -> None:
        self._policies[(policy.service_id, policy.priority)] = policy

    def all(self) -> list[SLAPolicy]:
        return list(self._policies.values())

    def policy_for(self, priority: Priority, service_id: str | None = None) -> SLAPolicy:
        policy = self._policies.get((service_id, priority)) or self._policies.get((None, priority))
        if policy is None:
            raise SLAConfigurationError(f"No SLA policy configured for {priority.name}.")
        return policy

    @classmethod
    def with_defaults(cls) -> "SLAPolicyBook":
        """The exact table from the project brief."""
        book = cls()
        for p, resp, res in [(Priority.P1, timedelta(minutes=5), timedelta(minutes=30)),
                             (Priority.P2, timedelta(minutes=15), timedelta(hours=2)),
                             (Priority.P3, timedelta(hours=1), timedelta(hours=8)),
                             (Priority.P4, timedelta(hours=4), timedelta(hours=24))]:
            book.add(SLAPolicy(p, resp, res))
        return book


class SLAClock:
    def __init__(self, policy: SLAPolicy, started_at: datetime):
        self._policy = policy
        self._started_at = started_at
        self._paused_since: datetime | None = None
        self._paused_total = timedelta(0)
        self._responded_at: datetime | None = None
        self._resolved_at: datetime | None = None
        self._response_breached = False
        self._resolution_breached = False
        self._warning_sent = False
        self._breach_notified = False

    @classmethod
    def restore(cls, policy, started_at, paused_since, paused_total, responded_at, resolved_at,
                response_breached, resolution_breached, warning_sent, breach_notified) -> "SLAClock":
        """Rebuild a clock exactly as it was saved."""
        c = cls(policy, started_at)
        c._paused_since, c._paused_total = paused_since, paused_total or timedelta(0)
        c._responded_at, c._resolved_at = responded_at, resolved_at
        c._response_breached, c._resolution_breached = response_breached, resolution_breached
        c._warning_sent, c._breach_notified = warning_sent, breach_notified
        return c

    # ---- read-only accessors -------------------------------------------------------
    policy = property(lambda s: s._policy)
    paused_since = property(lambda s: s._paused_since)
    paused_total = property(lambda s: s._paused_total)
    responded_at = property(lambda s: s._responded_at)
    resolved_at = property(lambda s: s._resolved_at)
    is_paused = property(lambda s: s._paused_since is not None)
    is_responded = property(lambda s: s._responded_at is not None)
    response_breached = property(lambda s: s._response_breached)
    resolution_breached = property(lambda s: s._resolution_breached)
    warning_sent = property(lambda s: s._warning_sent)
    breach_notified = property(lambda s: s._breach_notified)

    def mark_warning_sent(self) -> None:
        self._warning_sent = True

    def mark_breach_notified(self) -> None:
        self._breach_notified = True

    def reprioritize(self, policy: SLAPolicy) -> None:
        """Deadlines stay anchored to the original creation time."""
        self._policy = policy

    def response_due(self) -> datetime:
        return self._started_at + self._policy.response_target + self._paused_total

    def resolution_due(self) -> datetime:
        return self._started_at + self._policy.resolution_target + self._paused_total

    # ---- pause / resume ------------------------------------------------------------
    def pause(self, now: datetime) -> None:
        if self._paused_since is None:
            self._paused_since = now

    def resume(self, now: datetime) -> None:
        if self._paused_since is not None:
            self._paused_total += now - self._paused_since
            self._paused_since = None

    # ---- milestones ----------------------------------------------------------------
    def mark_responded(self, now: datetime) -> None:
        if self._responded_at is None:
            self._responded_at = now
            self._response_breached = now > self.response_due()

    def mark_resolved(self, now: datetime) -> None:
        self.resume(now)
        self._resolved_at = now
        if now > self.resolution_due():
            self._resolution_breached = True

    def reopen(self) -> None:
        self._resolved_at = None

    # ---- evaluation ----------------------------------------------------------------
    def _effective_now(self, now: datetime) -> datetime:
        return self._paused_since if self._paused_since is not None else now

    def _fraction(self, target: timedelta, now: datetime) -> float:
        elapsed = self._effective_now(now) - self._started_at - self._paused_total
        return max(0.0, elapsed / target)

    def used_fraction(self, now: datetime) -> float:
        """0.0 = just started, 1.0 = resolution deadline reached."""
        return self._fraction(self._policy.resolution_target, now)

    def response_used_fraction(self, now: datetime) -> float:
        return self._fraction(self._policy.response_target, now)

    def time_remaining(self, now: datetime) -> timedelta:
        return self.resolution_due() - self._effective_now(now)

    def status(self, now: datetime) -> SLAStatus:
        if self._resolved_at is not None:
            return SLAStatus.BREACHED if self._resolution_breached else SLAStatus.MET
        t = self._effective_now(now)
        if self._resolution_breached or self._response_breached or t > self.resolution_due():
            return SLAStatus.BREACHED
        if self._responded_at is None and t > self.response_due():
            return SLAStatus.BREACHED
        if self.is_paused:
            return SLAStatus.PAUSED
        if self.used_fraction(now) >= self._policy.warning_threshold:
            return SLAStatus.AT_RISK
        return SLAStatus.ON_TRACK

    def to_dict(self, now: datetime) -> dict:
        return {"priority": self._policy.priority.name,
                "responseDue": both_times(self.response_due()),
                "resolutionDue": both_times(self.resolution_due()),
                "responded": self._responded_at is not None,
                "status": self.status(now).name,
                "usedPercent": round(self.used_fraction(now) * 100, 1),
                "minutesRemaining": int(self.time_remaining(now).total_seconds() // 60),
                "paused": self.is_paused}
