"""Incident lifecycle (State pattern) and the end-to-end workflow."""
from datetime import timedelta

import pytest

from itsm.domain.common import SLAStatus
from itsm.domain.exceptions import InvalidStateTransitionError, ValidationError
from itsm.domain.states import Action, States


def test_report_runs_the_full_pipeline(env):
    i = env.report_payment()
    assert i.priority.name == "P1"
    assert i.category == "APPLICATION"
    assert i.service.service_id == "SVC-PAY"
    assert i.status == "ASSIGNED"
    assert i.sla.policy.resolution_target == timedelta(minutes=30)


def test_service_is_guessed_from_text_when_not_given(env):
    assert env.report_payment().service.service_id == "SVC-PAY"


def test_complete_lifecycle_is_audited_in_order(env):
    i = env.report_payment()
    env.full_lifecycle(i)
    states = [e.new_state for e in env.desk.audit.for_incident(i.incident_id) if e.new_state]
    assert states == ["NEW", "CLASSIFIED", "ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS",
                      "RESOLVED", "VERIFIED", "CLOSED"]


def test_notifications_go_out_on_two_channels(env):
    i = env.report_payment()
    tid = i.assignee.user_id
    assert env.desk.inbox(i.assignee)
    assert any(n.recipient_id == tid for n in env.desk.channel("email").outbox)


def test_cannot_close_new_incident():
    with pytest.raises(InvalidStateTransitionError):
        States.NEW.close()


def test_cannot_resolve_before_work_starts(env):
    i = env.report_payment()
    with pytest.raises(InvalidStateTransitionError):
        env.resolve(i)
    assert i.resolutions == [], "a failed transition must not leave partial data"


def test_allowed_actions_reflect_the_state(env):
    i = env.report_payment()
    assert i.allowed_actions() == [Action.ASSIGN, Action.ACKNOWLEDGE]
    assert States.CLOSED.allowed_actions() == []
    assert States.from_name("IN_PROGRESS") is States.IN_PROGRESS


def test_each_viewer_sees_only_their_own_buttons(env):
    i = env.report_payment()
    assert i.actions_for(i.assignee) == [Action.ACKNOWLEDGE]
    assert i.actions_for(env.u("emp1")) == [], "reporter can't act while it's ASSIGNED"
    assert i.actions_for(env.u("lead")) == [Action.ASSIGN, Action.ACKNOWLEDGE]
    env.work(i)
    env.resolve(i)
    assert i.actions_for(env.u("emp1")) == [Action.VERIFY, Action.REOPEN, Action.CLOSE]
    assert i.actions_for(env.u("emp2")) == [], "a stranger gets nothing"
    assert "assignmentReason" not in i.to_dict(env.desk.now(), env.u("emp1"))


def test_sla_pauses_while_awaiting_info(env):
    i = env.report_payment()
    env.work(i)
    due_before = i.sla.resolution_due()
    env.desk.request_info(i.assignee, i.incident_id, "Which branch?")
    env.clock.advance(minutes=120)
    assert i.sla.status(env.desk.now()) == SLAStatus.PAUSED
    env.desk.provide_info(env.u("emp1"), i.incident_id, "Hyderabad")
    assert i.sla.resolution_due() == due_before + timedelta(minutes=120)


def test_reopen_goes_back_to_the_same_technician(env):
    i = env.report_payment()
    first = i.assignee
    env.work(i)
    env.resolve(i)
    assert first.workload_points == 0
    env.desk.reopen(env.u("emp1"), i.incident_id, "Still failing at counter 3")
    assert i.status == "ASSIGNED"
    assert i.assignee == first
    assert i.assignment_reason.startswith("sticky")
    assert i.reopen_count == 1
    assert len(i.resolutions) == 1, "the previous resolution is kept as history"


def test_feedback_only_after_resolution(env):
    i = env.report_payment()
    with pytest.raises(ValidationError):
        env.desk.give_feedback(env.u("emp1"), i.incident_id, 5, "great")
    env.full_lifecycle(i)
    env.desk.give_feedback(env.u("emp1"), i.incident_id, 4, "ok")
    assert i.feedback.rating == 4
