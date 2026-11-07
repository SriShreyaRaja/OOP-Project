"""
Intelligent features. Simple, rule-based and explainable, each behind a clear interface so
Member 4 can plug in a smarter version (TF-IDF, embeddings, ML) without touching the desk.

  DuplicateDetector    → Feature A: duplicate incident detection
  IncidentCorrelator   → Feature B: correlation / root cause over the service dependency graph
  SLARiskAnalyzer      → Feature E: predictive SLA risk, before the standard warning
  ResolutionSuggester  → Feature G: suggested fixes from history
  WhatIfSimulator      → bonus: blast radius if a service fails
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta

from . import text
from .catalog import ServiceCatalog
from .common import SLAStatus


@dataclass(frozen=True)
class Match:
    incident_id: str
    score: float
    reason: str


class DuplicateDetector(ABC):
    @abstractmethod
    def find_duplicates(self, incident, candidates: list) -> list[Match]: ...


class KeywordDuplicateDetector(DuplicateDetector):
    """Normalised-keyword Jaccard similarity + a same-service bonus, among recent open incidents."""

    def __init__(self, threshold: float = 0.45, same_service_bonus: float = 0.25,
                 window: timedelta = timedelta(hours=24)):
        self.threshold, self.bonus, self.window = threshold, same_service_bonus, window

    def find_duplicates(self, incident, candidates):
        txt = f"{incident.title} {incident.description}"
        out = []
        for other in candidates:
            if other.incident_id == incident.incident_id or not other.is_open:
                continue
            if abs(incident.created_at - other.created_at) > self.window:
                continue
            score = text.jaccard(txt, f"{other.title} {other.description}")
            same = other.service.service_id == incident.service.service_id
            if same:
                score += self.bonus
            score = min(1.0, round(score, 2))
            if score >= self.threshold:
                out.append(Match(other.incident_id, score, "text similarity" + (" + same service" if same else "")))
        return sorted(out, key=lambda m: -m.score)


@dataclass(frozen=True)
class Correlation:
    suspected_root_service_id: str
    service_name: str
    incident_ids: tuple[str, ...]
    direct_reports: int
    explanation: str


class IncidentCorrelator:
    """
    If several open incidents hit services that depend on the same upstream service, that
    service is the likely root cause. Ranking: covers the most incidents → is itself reported
    broken → most fundamental (fewest dependencies of its own).
    """

    def __init__(self, catalog: ServiceCatalog, min_incidents: int = 2):
        self._catalog, self._min = catalog, min_incidents

    def correlate(self, open_incidents: list) -> list[Correlation]:
        by_upstream: dict[str, set[str]] = defaultdict(set)
        direct: dict[str, int] = defaultdict(int)
        for inc in open_incidents:
            sid = inc.service.service_id
            direct[sid] += 1
            for up in self._catalog.upstream_of(sid) | {sid}:
                by_upstream[up].add(inc.incident_id)
        out = []
        for up, ids in by_upstream.items():
            if len(ids) >= self._min:
                name, d = self._catalog.get(up).name, direct.get(up, 0)
                out.append(Correlation(up, name, tuple(sorted(ids)), d,
                                       f"{len(ids)} open incidents share a dependency on {name}"
                                       + (f" ({d} reported directly on it)" if d else "")))
        return sorted(out, key=lambda c: (-len(c.incident_ids), -c.direct_reports,
                                          len(self._catalog.upstream_of(c.suspected_root_service_id)),
                                          c.suspected_root_service_id))


@dataclass(frozen=True)
class SLARisk:
    incident_id: str
    risk: float
    level: str
    factors: tuple[str, ...]


class SLARiskAnalyzer:
    """Predicts breaches using time used, assignment, the assignee's load and reopen history."""

    def assess(self, incident, now: datetime) -> SLARisk | None:
        sla = incident.sla
        if not incident.is_open or sla is None:
            return None
        if sla.status(now) == SLAStatus.BREACHED:
            return SLARisk(incident.incident_id, 1.0, "BREACHED", ("SLA already violated",))
        used = min(sla.used_fraction(now), 1.5)
        risk = used * 0.6
        factors = [f"{used:.0%} of resolution time used"]
        if not sla.is_responded:
            resp = min(sla.response_used_fraction(now), 1.5)
            if resp * 0.6 > risk:
                risk = resp * 0.6
                factors[0] = f"not acknowledged, {resp:.0%} of response time used"
        if incident.assignee is None:
            risk += 0.25
            factors.append("not assigned")
        else:
            risk += incident.assignee.load_ratio * 0.2
            factors.append(f"assignee load {incident.assignee.load_ratio:.0%}")
        if incident.reopen_count:
            risk += 0.1
            factors.append("previously reopened")
        risk = round(min(risk, 1.0), 2)
        level = "HIGH" if risk >= 0.6 else "MEDIUM" if risk >= 0.35 else "LOW"
        return SLARisk(incident.incident_id, risk, level, tuple(factors))


@dataclass(frozen=True)
class Suggestion:
    from_incident_id: str
    fix: str
    root_cause: str
    similarity: float


class ResolutionSuggester:
    def suggest(self, incident, history: list, top: int = 3) -> list[Suggestion]:
        txt = f"{incident.title} {incident.description}"
        out = []
        for h in history:
            if h.incident_id == incident.incident_id or not h.resolutions:
                continue
            s = text.jaccard(txt, f"{h.title} {h.description}")
            if h.service.service_id == incident.service.service_id:
                s += 0.2
            if s > 0.2:
                r = h.resolutions[-1]
                out.append(Suggestion(h.incident_id, r.description, r.root_cause, round(min(s, 1.0), 2)))
        return sorted(out, key=lambda x: -x.similarity)[:top]


@dataclass(frozen=True)
class BlastRadius:
    failed_service_id: str
    failed_service_name: str
    impacted_service_names: tuple[str, ...]
    impacted_count: int
    business_critical_impacted: int
    exposure_score: int


class WhatIfSimulator:
    """'What if this service failed?' Read-only analysis over the dependency graph."""

    def __init__(self, catalog: ServiceCatalog):
        self._catalog = catalog

    def simulate_failure(self, service_id: str) -> BlastRadius:
        failed = self._catalog.get(service_id)
        impacted = [self._catalog.get(s) for s in self._catalog.downstream_of(service_id)]
        return BlastRadius(service_id, failed.name, tuple(s.name for s in impacted), len(impacted),
                           sum(1 for s in impacted if s.business_criticality >= 5),
                           failed.business_criticality + sum(s.business_criticality for s in impacted))
