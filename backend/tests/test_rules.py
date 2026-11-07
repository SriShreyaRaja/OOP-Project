"""Business rules: priority, SLA, escalation."""
from datetime import timedelta

import pytest

from itsm.domain.catalog import ITService
from itsm.domain.common import Impact, Priority, Role, Urgency
from itsm.domain.exceptions import SLAConfigurationError
from itsm.domain.priority import MatrixPriorityStrategy, WeightedScorePriorityStrategy
from itsm.domain.service_desk import IncidentRequest
from itsm.domain.sla import SLAPolicy, SLAPolicyBook


@pytest.mark.parametrize("impact, urgency, crit, expected", [
    (Impact.LOW, Urgency.LOW, 1, Priority.P4),                  # 1
    (Impact.MEDIUM, Urgency.MEDIUM, 3, Priority.P3),            # 12
    (Impact.HIGH, Urgency.MEDIUM, 4, Priority.P2),              # 24, exactly on the P2 boundary
    (Impact.ORGANIZATION, Urgency.CRITICAL, 3, Priority.P1),    # 48, exactly on the P1 boundary
    (Impact.HIGH, Urgency.HIGH, 2, Priority.P3),                # 18, just below P2
], ids=["score1-P4", "score12-P3", "score24-P2", "score48-P1", "score18-P3"])
def test_weighted_priority_thresholds(impact, urgency, crit, expected):
    s = ITService("S", "Svc", crit, "SOFTWARE")
    assert WeightedScorePriorityStrategy().calculate(impact, urgency, s, 1).priority == expected


def test_many_affected_users_raise_priority():
    s = ITService("S", "Svc", 2, "SOFTWARE")
    w = WeightedScorePriorityStrategy()
    assert w.calculate(Impact.HIGH, Urgency.HIGH, s, 1).priority == Priority.P3          # 18
    assert w.calculate(Impact.HIGH, Urgency.HIGH, s, 10_000).priority == Priority.P2     # 18 × 1.4 = 25.2


def test_matrix_bumps_critical_services():
    r = MatrixPriorityStrategy().calculate(Impact.MEDIUM, Urgency.MEDIUM, ITService("S", "Core", 5, "DATABASE"), 1)
    assert r.priority == Priority.P2
    assert r.explanation["criticalServiceBump"] is True


def test_priority_strategy_swap_at_runtime(env):
    env.desk.set_priority_strategy(env.u("admin"), "matrix")
    assert env.report_payment().priority_explanation["strategy"] == "matrix"


def test_reassessment_updates_priority_sla_and_workload_points(env):
    i = env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "Printer jammed", "The second floor printer is jammed again").service("SVC-PRINT")
        .impact("LOW").urgency("LOW").build())
    assert i.priority == Priority.P4
    before = i.assignee.workload_points
    env.desk.reassess(env.u("lead"), i.incident_id, "ORGANIZATION", "CRITICAL", 2000)
    # 4 × 4 × 1 (printing is low-criticality) × 1.33 boost = 21.3 → P3
    assert i.priority == Priority.P3
    assert i.sla.policy.resolution_target == timedelta(hours=8)
    assert i.assignee.workload_points == before - 1 + 3


def test_service_specific_sla_overrides_default(env):
    env.desk.configure_sla(env.u("admin"), SLAPolicy(Priority.P1, timedelta(minutes=2), timedelta(minutes=15),
                                                     0.75, "SVC-PAY"))
    assert env.report_payment().sla.policy.resolution_target == timedelta(minutes=15)


def test_missing_sla_configuration():
    with pytest.raises(SLAConfigurationError):
        SLAPolicyBook().policy_for(Priority.P1)


def test_sla_warning_then_breach_reported_once(env):
    i = env.report_payment()
    env.desk.acknowledge(i.assignee, i.incident_id)
    env.clock.advance(minutes=24)
    assert env.desk.run_monitor().warnings == [i.incident_id]
    env.clock.advance(minutes=10)
    assert env.desk.run_monitor().breaches == [i.incident_id]
    assert env.desk.run_monitor().breaches == [], "a breach must not be re-announced"


def test_auto_escalation_climbs_the_chain(env):
    i = env.report_payment()
    env.clock.advance(minutes=6)
    assert env.desk.run_monitor().escalations == [(i.incident_id, Role.TEAM_LEAD)]
    env.clock.advance(minutes=30)
    assert env.desk.run_monitor().escalations == [(i.incident_id, Role.IT_MANAGER)]
    assert env.desk.inbox(env.u("manager"))


def test_acknowledged_incidents_are_not_escalated(env):
    i = env.report_payment()
    env.desk.acknowledge(i.assignee, i.incident_id)
    env.clock.advance(minutes=40)
    assert env.desk.run_monitor().escalations == []
