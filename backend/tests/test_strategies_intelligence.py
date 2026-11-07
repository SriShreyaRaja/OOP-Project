"""Assignment strategies, intelligent features, search and reports."""
import pytest

from itsm.domain.assignment import (PriorityBasedAssignment, RoundRobinAssignment, SkillBasedAssignment,
                                    SmartRecommendationAssignment)
from itsm.domain.common import ServiceHealth
from itsm.domain.exceptions import DependencyCycleError, DuplicateIncidentError, TechnicianUnavailableError
from itsm.domain.service_desk import IncidentRequest, SearchCriteria

TECHS = ("lead", "t_app", "t_net", "t_db", "t_jr")


def test_strategies_behave_differently(env):
    i = env.desk.report_incident(env.u("emp1"), env.payment_outage().manual_assignment().build())
    techs = [env.org.tech(k) for k in TECHS]
    assert SkillBasedAssignment().select(i, techs).technician.user_id == "T201"      # APPLICATION 5/5
    assert PriorityBasedAssignment().select(i, techs).technician.user_id == "L001"   # most experienced
    rr = RoundRobinAssignment()
    assert rr.select(i, techs).technician != rr.select(i, techs).technician
    assert len(SmartRecommendationAssignment().select(i, techs).reasons) == 4


def test_assignment_strategy_swap_at_runtime(env):
    env.desk.set_assignment_strategy(env.u("admin"), "load")
    i = env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "Wifi keeps dropping", "Office wifi disconnects every few minutes").build())
    assert i.assignment_reason.startswith("load strategy")


def test_no_capacity_leaves_incident_for_manual_assignment(env):
    for k in TECHS:
        env.org.tech(k).set_available(False)
    i = env.report_payment()
    assert i.status == "CLASSIFIED"
    with pytest.raises(TechnicianUnavailableError):
        SkillBasedAssignment().select(i, [env.org.tech("t_app")])
    env.org.tech("t_app").set_available(True)
    env.desk.assign_manually(env.u("lead"), i.incident_id, "T201")
    assert i.status == "ASSIGNED"


def test_duplicates_are_linked_and_can_be_blocked(env):
    a = env.report_payment()
    b = env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "Payment transaction failing", "Payment transaction failing at checkout").impact("HIGH").urgency("HIGH").build())
    assert a.incident_id in b.related_incidents and b.incident_id in a.related_incidents
    with pytest.raises(DuplicateIncidentError) as err:
        env.desk.report_incident(env.u("emp3"), IncidentRequest.builder(
            "Unable to make payment", "Payment unavailable again for our team").block_duplicates().build())
    assert err.value.original_incident_id
    assert env.desk.factory.peek_next_id() == "INC1003", "a blocked report must not burn an ID"


def test_correlation_points_to_shared_root_cause(env):
    env.report_payment()
    env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "SSO login down", "Cannot login through SSO anywhere").impact("ORGANIZATION").urgency("CRITICAL").build())
    assert env.desk.correlations(env.u("manager"))[0].suspected_root_service_id == "SVC-AUTH"


def test_dependency_cycles_are_rejected(env):
    with pytest.raises(DependencyCycleError):
        env.desk.add_dependency(env.u("admin"), "SVC-DB", "SVC-RPT")
    with pytest.raises(DependencyCycleError):
        env.desk.add_dependency(env.u("admin"), "SVC-DB", "SVC-DB")


def test_what_if_blast_radius(env):
    r = env.desk.simulate_failure(env.u("manager"), "SVC-DB")
    assert set(r.impacted_service_names) == {"Authentication SSO", "Payment Application",
                                             "Email & Calendar", "Finance Reporting"}
    assert r.business_critical_impacted == 2
    assert env.desk.simulate_failure(env.u("manager"), "SVC-RPT").impacted_count == 0


def test_sla_risk_flags_unacknowledged_incidents_early(env):
    env.report_payment()
    env.clock.advance(minutes=3)
    risk = env.desk.sla_risks(env.u("manager"))[0]
    assert risk.level == "MEDIUM"
    assert risk.factors[0].startswith("not acknowledged")


def test_resolution_suggestions_come_from_history(env):
    old = env.report_payment()
    env.full_lifecycle(old)
    fresh = env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "Payment transaction failing", "Payment transactions failing again").service("SVC-PAY").build())
    s = env.desk.suggest_resolutions(env.u("manager"), fresh.incident_id)
    assert s[0].from_incident_id == old.incident_id
    assert s[0].root_cause == "Node memory leak"


def test_new_category_without_code_change(env):
    env.desk.add_category(env.u("admin"), "IOT", {"sensor", "thermostat"}, "Smart building devices")
    i = env.desk.report_incident(env.u("emp1"), IncidentRequest.builder(
        "Thermostat sensor offline", "The thermostat sensor in room 4 is offline").service("SVC-NET").build())
    assert i.category == "IOT"


def test_search_supports_many_criteria_and_respects_visibility(env):
    a = env.report_payment()
    env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "Printer jammed", "The 2nd floor printer is jammed").service("SVC-PRINT").impact("LOW").urgency("LOW").build())
    m = env.u("manager")
    assert env.desk.search(m, SearchCriteria.where().priority("P1")) == [a]
    assert len(env.desk.search(m, SearchCriteria.where().category("HARDWARE").open_only())) == 1
    assert len(env.desk.search(m, SearchCriteria.where().service("SVC-PAY").status("ASSIGNED"))) == 1
    assert len(env.desk.search(m, SearchCriteria.where().sla_status("ON_TRACK"))) == 2
    assert len(env.desk.search(m, SearchCriteria.where().technician(a.assignee.user_id).text("payment"))) == 1
    assert env.desk.search(env.u("emp2"), SearchCriteria.where().text("payment")) == []


def test_reports_and_service_health(env):
    i = env.report_payment()
    assert env.desk.service_analysis(env.u("manager"))[0].health == ServiceHealth.DOWN
    env.full_lifecycle(i)
    env.desk.give_feedback(env.u("emp1"), i.incident_id, 4, "ok")
    o = env.desk.overview(env.u("manager"))
    assert (o.total_incidents, o.resolved_incidents, o.open_incidents) == (1, 1, 0)
    assert o.average_feedback == 4.0
    assert o.sla_compliance_percent == 100.0
