"""Persistence (save → restart → reload) and day-to-day operations."""
import json
from datetime import timedelta

import pytest

from itsm.domain import sample_data
from itsm.domain.common import FakeClock, to_json
from itsm.domain.exceptions import AuthenticationError, UnauthorizedOperationError
from itsm.domain.notifications import NotificationChannel
from itsm.domain.persistence import InMemoryStorage, UserRecord
from itsm.domain.service_desk import IncidentRequest, ServiceDesk
from itsm.domain.users import Technician


def test_everything_survives_a_restart():
    # Day 1: a desk backed by storage does real work
    clock, db = FakeClock(), InMemoryStorage()
    day1 = ServiceDesk(clock)
    day1.attach_storage(db)
    org = sample_data.seed(day1)
    open_inc = day1.report_incident(org.get("emp1"), IncidentRequest.builder(
        "Payment application unavailable", "Users are unable to complete transactions on the payment app.")
        .impact("ORGANIZATION").urgency("CRITICAL").affected_users(500).build())
    tech = open_inc.assignee
    day1.acknowledge(tech, open_inc.incident_id)
    day1.start_work(tech, open_inc.incident_id)
    day1.request_info(tech, open_inc.incident_id, "Which branch?")            # SLA paused
    done = day1.report_incident(org.get("emp2"), IncidentRequest.builder(
        "Printer jammed", "The 2nd floor printer is jammed").service("SVC-PRINT").impact("LOW").urgency("LOW").build())
    pt = done.assignee
    day1.acknowledge(pt, done.incident_id)
    day1.start_work(pt, done.incident_id)
    day1.resolve(pt, done.incident_id, "Cleared the paper path and rollers.", "Worn roller", "Replace rollers yearly")

    # Day 2: a brand-new desk on the same storage
    day2 = ServiceDesk(clock)
    day2.attach_storage(db)
    assert not day2.is_empty()
    ravi = day2.login("ravi@corp.in", sample_data.PASSWORD)                    # password hash survived
    reloaded = day2.get_incident(ravi, open_inc.incident_id)
    assert reloaded.status == "AWAITING_INFO"
    assert reloaded.sla.is_paused
    assert reloaded.priority_explanation == open_inc.priority_explanation
    assert day2.user(tech.user_id).workload_points == 8, "workload rebuilt from open incidents"
    assert day2.user(pt.user_id).resolved_count == 1
    assert len(day2.audit.all()) == len(day1.audit.all())
    assert day2.factory.peek_next_id() == "INC1003", "numbering continues"
    day2.provide_info(ravi, open_inc.incident_id, "Hyderabad")                 # …and work simply continues
    assert reloaded.status == "IN_PROGRESS"


def test_user_record_round_trip(env):
    t = env.org.tech("t_net")
    back = UserRecord.from_user(t).to_user()
    assert isinstance(back, Technician)
    assert back.skills == t.skills
    assert back.check_password(sample_data.PASSWORD)


def test_login_locks_after_five_failures(env):
    for _ in range(5):
        with pytest.raises(AuthenticationError):
            env.desk.login("ravi@corp.in", "wrongpass1")
    with pytest.raises(AuthenticationError, match="Too many"):
        env.desk.login("ravi@corp.in", sample_data.PASSWORD)
    env.clock.advance(minutes=16)
    assert env.desk.login("ravi@corp.in", sample_data.PASSWORD).user_id == "E101"


def test_resolved_incidents_auto_close(env):
    i = env.report_payment()
    env.work(i)
    env.resolve(i)
    env.clock.advance(hours=71)
    assert env.desk.run_monitor().auto_closed == []
    env.clock.advance(hours=2)
    assert env.desk.run_monitor().auto_closed == [i.incident_id]
    assert i.status == "CLOSED"


def test_technician_queue_is_sorted_by_urgency(env):
    tara = env.org.tech("t_app")
    env.desk.set_assignment_strategy(env.u("admin"), "skill")
    low = env.desk.report_incident(env.u("emp2"), IncidentRequest.builder(
        "Payment report typo", "Small label typo on the payment receipt page").service("SVC-PAY")
        .impact("LOW").urgency("LOW").build())
    high = env.report_payment()
    assert env.desk.my_queue(tara) == [high, low]
    assert env.desk.my_incidents(env.u("emp1")) == [high]


def test_manage_technicians(env):
    env.desk.update_technician_skills(env.u("admin"), "T204", {"CLOUD": 4})
    jaya = env.org.tech("t_jr")
    assert jaya.skill_level("CLOUD") == 4 and jaya.skill_level("HARDWARE") == 0
    env.desk.set_availability(jaya, "T204", False)                            # a technician can do it for themselves
    assert not jaya.is_available()
    with pytest.raises(UnauthorizedOperationError):
        env.desk.set_availability(env.org.tech("t_net"), "T204", True)
    with pytest.raises(UnauthorizedOperationError):
        env.desk.update_technician_skills(env.u("lead"), "T204", {})


def test_broken_notification_channel_does_not_break_workflow(env):
    class BrokenSms(NotificationChannel):
        name = "sms"

        def send(self, notification):
            raise RuntimeError("SMS provider timeout")

    env.desk.add_notification_channel(BrokenSms())
    i = env.report_payment()                       # P1 → urgent → uses SMS too
    assert i.status == "ASSIGNED"
    assert env.desk.notification_failures(env.u("manager"))


def test_admin_views_audit_log_and_violations(env):
    i = env.report_payment()
    env.clock.advance(minutes=40)
    env.desk.run_monitor()
    assert env.desk.sla_violations(env.u("manager")) == [i]
    assert env.desk.all_audit_logs(env.u("admin"))
    with pytest.raises(UnauthorizedOperationError):
        env.desk.all_audit_logs(env.u("t_app"))


def test_incident_serializes_to_json(env):
    i = env.report_payment()
    data = json.loads(to_json(i.to_dict(env.desk.now(), i.assignee)))
    assert data["incidentId"] == "INC1001"
    assert data["allowedActions"] == ["ASSIGN", "ACKNOWLEDGE"]
    assert data["yourActions"] == ["ACKNOWLEDGE"]
