"""
STRATEGY PATTERN #2 (+ TEMPLATE METHOD): technician assignment.

The template is fixed in the base class: filter eligible → score each → sort → pick the
best. Subclasses only supply `_score`. Every candidate carries human-readable reasons.

  skill        best proficiency in the incident's category
  load         most spare capacity (in workload points)
  round_robin  fair rotation
  priority     P1/P2 → most experienced, P3/P4 → least loaded
  smart        weighted blend (Intelligent Feature D: Smart Technician Recommendation)
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .common import Priority
from .exceptions import TechnicianUnavailableError, ValidationError
from .users import Technician


@dataclass(frozen=True)
class Candidate:
    technician: Technician
    score: float
    reasons: tuple[str, ...] = field(default_factory=tuple)

    def summary(self) -> str:
        return f"{self.technician.user_id} (score {self.score:.2f}): {'; '.join(self.reasons)}"


class AssignmentStrategy(ABC):
    name = "abstract"
    requires_skill = True

    @abstractmethod
    def _score(self, incident, technician: Technician) -> Candidate: ...

    def eligible(self, incident, technicians: list[Technician]) -> list[Technician]:
        """Available, with capacity for this priority, and (if required) skilled."""
        pool = [t for t in technicians if t.has_capacity_for(incident.priority)]
        if self.requires_skill and incident.category:
            skilled = [t for t in pool if t.skill_level(incident.category) > 0]
            if skilled:
                return skilled          # otherwise fall back to anyone free rather than nobody
        return pool

    def rank(self, incident, technicians: list[Technician]) -> list[Candidate]:
        cands = [self._score(incident, t) for t in self.eligible(incident, technicians)]
        return sorted(cands, key=lambda c: (-c.score, c.technician.workload_points, c.technician.user_id))

    def select(self, incident, technicians: list[Technician]) -> Candidate:
        ranked = self.rank(incident, technicians)
        if not ranked:
            raise TechnicianUnavailableError(
                f"No technician has capacity for {incident.incident_id} ({incident.priority}).")
        return ranked[0]


class SkillBasedAssignment(AssignmentStrategy):
    name = "skill"

    def _score(self, incident, t):
        lvl = t.skill_level(incident.category)
        return Candidate(t, lvl + min(t.years_experience, 10) / 100,
                         (f"{incident.category} skill {lvl}/5", f"{t.years_experience}y experience"))


class LoadBasedAssignment(AssignmentStrategy):
    name = "load"
    requires_skill = False

    def _score(self, incident, t):
        return Candidate(t, 1 - t.load_ratio, (f"workload {t.workload_points}/{t.max_workload_points} points",))


class RoundRobinAssignment(AssignmentStrategy):
    name = "round_robin"
    requires_skill = True

    def __init__(self):
        self._last_assigned_id: str | None = None

    def rank(self, incident, technicians):
        pool = sorted(self.eligible(incident, technicians), key=lambda t: t.user_id)
        ids = [t.user_id for t in pool]
        start = ids.index(self._last_assigned_id) + 1 if self._last_assigned_id in ids else 0
        ordered = pool[start:] + pool[:start]
        return [Candidate(t, len(ordered) - k, (f"next in rotation (#{k + 1})",)) for k, t in enumerate(ordered)]

    def select(self, incident, technicians):
        c = super().select(incident, technicians)
        self._last_assigned_id = c.technician.user_id
        return c

    def _score(self, incident, t):
        raise NotImplementedError("round robin ranks by rotation")


class PriorityBasedAssignment(AssignmentStrategy):
    name = "priority"

    def _score(self, incident, t):
        if incident.priority in (Priority.P1, Priority.P2):
            skill = t.skill_level(incident.category)
            return Candidate(t, t.years_experience + skill,
                             (f"critical work → {t.years_experience}y experience + skill {skill}",))
        return Candidate(t, 1 - t.load_ratio,
                         (f"routine work → workload {t.workload_points}/{t.max_workload_points}",))


class SmartRecommendationAssignment(AssignmentStrategy):
    """
    score = w_skill·skill/5 + w_load·(1 − load) + w_history·min(fixes on this service, 5)/5
          + w_experience·min(years, 10)/10          (weights configurable, normalised to 1)
    """
    name = "smart"

    def __init__(self, skill=0.4, load=0.3, history=0.2, experience=0.1):
        total = skill + load + history + experience
        if min(skill, load, history, experience) < 0 or total <= 0:
            raise ValidationError("Weights must be non-negative and not all zero.")
        self._w = {"skill": skill / total, "load": load / total,
                   "history": history / total, "experience": experience / total}

    def _score(self, incident, t):
        skill = t.skill_level(incident.category)
        history = t.experience_with(incident.service.service_id)
        parts = {"skill": skill / 5, "load": 1 - t.load_ratio,
                 "history": min(history, 5) / 5, "experience": min(t.years_experience, 10) / 10}
        score = round(sum(self._w[k] * parts[k] for k in parts), 3)
        return Candidate(t, score, (f"skill {skill}/5", f"workload {t.workload_points}/{t.max_workload_points}",
                                    f"fixed {incident.service.name} {history}×", f"{t.years_experience}y exp"))


ASSIGNMENT_STRATEGIES = {cls.name: cls for cls in (SkillBasedAssignment, LoadBasedAssignment, RoundRobinAssignment,
                                                    PriorityBasedAssignment, SmartRecommendationAssignment)}


def assignment_strategy_by_name(name: str) -> AssignmentStrategy:
    if name not in ASSIGNMENT_STRATEGIES:
        raise ValidationError(f"Unknown assignment strategy '{name}'. Options: {sorted(ASSIGNMENT_STRATEGIES)}")
    return ASSIGNMENT_STRATEGIES[name]()
