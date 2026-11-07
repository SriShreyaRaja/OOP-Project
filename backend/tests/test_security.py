"""Authorization, authentication and input validation."""
import pytest

from itsm.domain.common import Priority
from itsm.domain.exceptions import (AuthenticationError, CategoryNotFoundError, ServiceNotFoundError,
                                    UnauthorizedOperationError, ValidationError, WorkloadExceededError)
from itsm.domain.service_desk import IncidentRequest
from itsm.domain.users import Employee, Technician


def test_login_works_and_rejects_wrong_password(env):
    assert env.desk.login("ravi@corp.in", "Passw0rd!").user_id == "E101"
    with pytest.raises(AuthenticationError):
        env.desk.login("ravi@corp.in", "nope12345")
    with pytest.raises(AuthenticationError):
        env.desk.login("ghost@corp.in", "Passw0rd!")


def test_deactivated_user_cannot_login_or_act(env):
    env.desk.deactivate_user(env.u("admin"), "E102")
    with pytest.raises(AuthenticationError):
        env.desk.login("sana@corp.in", "Passw0rd!")
    with pytest.raises(UnauthorizedOperationError):
        env.desk.report_incident(env.u("emp2"), env.payment_outage().build())


def test_employee_cannot_resolve(env):
    i = env.report_payment()
    with pytest.raises(UnauthorizedOperationError):
        env.desk.resolve(env.u("emp1"), i.incident_id, "I fixed it myself somehow", "unknown")


def test_other_technician_cannot_acknowledge(env):
    i = env.report_payment()
    other = env.org.tech("t_db") if i.assignee == env.org.tech("t_net") else env.org.tech("t_net")
    with pytest.raises(UnauthorizedOperationError):
        env.desk.acknowledge(other, i.incident_id)


def test_employee_cannot_configure_or_see_others_incidents(env):
    i = env.report_payment()
    with pytest.raises(UnauthorizedOperationError):
        env.desk.set_assignment_strategy(env.u("emp1"), "load")
    with pytest.raises(UnauthorizedOperationError):
        env.desk.get_incident(env.u("emp2"), i.incident_id)
    with pytest.raises(UnauthorizedOperationError):
        env.desk.overview(env.u("emp1"))


def test_internal_notes_hidden_from_employees(env):
    i = env.report_payment()
    env.desk.add_note(i.assignee, i.incident_id, "DB creds rotated", internal=True)
    assert i.visible_notes(env.u("emp1")) == []
    assert len(i.visible_notes(i.assignee)) == 1


@pytest.mark.parametrize("title, desc, impact, users", [
    ("Hi", "Payment app is down for everyone", "HIGH", 1),
    ("Payment down", "short", "HIGH", 1),
    ("Payment down", "Payment app is down for us", "HUGE", 1),
    ("Payment down", "Payment app is down for us", "HIGH", 0),
], ids=["short-title", "short-description", "bad-impact", "zero-users"])
def test_invalid_incident_input_is_rejected(env, title, desc, impact, users):
    with pytest.raises(ValidationError):
        env.desk.report_incident(env.u("emp1"), IncidentRequest.builder(title, desc).service("SVC-PAY")
                                 .impact(impact).affected_users(users).build())


def test_unknown_service_and_category(env):
    with pytest.raises(ServiceNotFoundError):
        env.desk.report_incident(env.u("emp1"), IncidentRequest.builder(
            "Thing broken", "Something is broken here").service("NOPE").build())
    with pytest.raises(CategoryNotFoundError):
        env.desk.report_incident(env.u("emp1"), IncidentRequest.builder(
            "Thing broken", "Something is broken here").service("SVC-PAY").category("ALIENS").build())
    assert env.desk.factory.peek_next_id() == "INC1001", "rejected reports must not burn IDs"


def test_weak_passwords_and_bad_emails_rejected():
    with pytest.raises(ValidationError):
        Employee("E9", "X", "x@corp.in", "short")
    with pytest.raises(ValidationError):
        Employee("E9", "X", "x@corp.in", "onlyletters")
    with pytest.raises(ValidationError):
        Employee("E9", "X", "not-an-email", "longenough1")


def test_duplicate_registration_rejected(env):
    with pytest.raises(ValidationError):
        env.desk.register_user(env.u("admin"), Employee("E101", "Copy", "copy@corp.in", "Passw0rd!"))
    with pytest.raises(ValidationError):
        env.desk.register_user(env.u("admin"), Employee("E999", "Copy", "ravi@corp.in", "Passw0rd!"))


def test_password_is_hashed_not_stored():
    e = Employee("E9", "X", "x@corp.in", "CorrectHorse1")
    assert e.check_password("CorrectHorse1")
    assert not e.check_password("wrong")
    assert "CorrectHorse1" not in str(e.to_dict()) and "CorrectHorse1" not in e.encoded_password_hash()


def test_workload_points_are_enforced():
    t = Technician("T9", "T", "t@corp.in", "Passw0rd1", {"NETWORK": 3}, 10, 1)
    t.take_incident("INC1", Priority.P1)                        # 8 points
    with pytest.raises(WorkloadExceededError):
        t.take_incident("INC2", Priority.P2)                    # 8 + 5 > 10
    t.take_incident("INC3", Priority.P4)                        # 1 more still fits
    assert t.workload_points == 9
