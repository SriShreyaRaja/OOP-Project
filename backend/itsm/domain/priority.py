"""
STRATEGY PATTERN #1: how an assessment becomes a priority.

Every strategy returns the priority AND its explanation ("why is this P1?"). Admins can
swap the active strategy at runtime; incidents never know which one ran.
"""
from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from .catalog import ITService
from .common import Impact, Priority, Urgency
from .exceptions import ValidationError


@dataclass(frozen=True)
class PriorityResult:
    priority: Priority
    score: float
    explanation: dict = field(default_factory=dict)


class PriorityStrategy(ABC):
    name = "abstract"

    @abstractmethod
    def calculate(self, impact: Impact, urgency: Urgency, service: ITService,
                  affected_users: int) -> PriorityResult: ...


class WeightedScorePriorityStrategy(PriorityStrategy):
    """
    The brief's formula, plus a user-count boost:
        base  = Impact(1-4) × Urgency(1-4) × Business Criticality(1-5)     (max 80)
        boost = 1 + 0.1 × log10(affected users)       1 user → ×1.0 · 1,000 users → ×1.3
        score = base × boost        P1 ≥ 48 · P2 ≥ 24 · P3 ≥ 10 · else P4
    The log keeps the boost modest: many users matter, but a trivial problem can't become
    critical just because it's widespread.
    """
    name = "weighted"
    THRESHOLDS = ((48, Priority.P1), (24, Priority.P2), (10, Priority.P3))

    def calculate(self, impact, urgency, service, affected_users):
        base = impact.weight * urgency.weight * service.business_criticality
        boost = 1 + 0.1 * math.log10(max(1, affected_users))
        score = round(base * boost, 1)
        priority = next((p for t, p in self.THRESHOLDS if score >= t), Priority.P4)
        return PriorityResult(priority, score, {
            "strategy": self.name,
            "formula": "Impact × Urgency × Criticality × UserBoost",
            "impact": f"{impact.name} ({impact.weight})",
            "urgency": f"{urgency.name} ({urgency.weight})",
            "businessCriticality": f"{service.name} ({service.business_criticality})",
            "affectedUsers": affected_users,
            "userBoost": round(boost, 2),
            "score": score,
            "thresholds": "P1≥48, P2≥24, P3≥10, else P4",
            "result": str(priority),
        })


class MatrixPriorityStrategy(PriorityStrategy):
    """The classic ITIL impact/urgency matrix, +1 level for business-critical services."""
    name = "matrix"
    _ORDER = [Priority.P1, Priority.P2, Priority.P3, Priority.P4]

    def calculate(self, impact, urgency, service, affected_users):
        total = impact.weight + urgency.weight
        priority = Priority.P1 if total >= 7 else Priority.P2 if total >= 5 else Priority.P3 if total == 4 else Priority.P4
        bumped = False
        if service.business_criticality == 5 and priority != Priority.P1:
            priority = self._ORDER[self._ORDER.index(priority) - 1]
            bumped = True
        return PriorityResult(priority, float(total), {
            "strategy": self.name,
            "formula": "ITIL matrix on Impact + Urgency, +1 level for critical services",
            "impact": impact.name, "urgency": urgency.name, "matrixSum": total,
            "criticalServiceBump": bumped, "score": float(total), "result": str(priority),
        })


PRIORITY_STRATEGIES = {cls.name: cls for cls in (WeightedScorePriorityStrategy, MatrixPriorityStrategy)}


def priority_strategy_by_name(name: str) -> PriorityStrategy:
    if name not in PRIORITY_STRATEGIES:
        raise ValidationError(f"Unknown priority strategy '{name}'. Options: {sorted(PRIORITY_STRATEGIES)}")
    return PRIORITY_STRATEGIES[name]()
