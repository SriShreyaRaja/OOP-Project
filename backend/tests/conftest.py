"""Shared test setup: a fresh sample organisation and a fake clock for every test."""
import pytest

from itsm.domain import sample_data
from itsm.domain.common import FakeClock
from itsm.domain.service_desk import IncidentRequest


class Env:
    def __init__(self):
        self.clock = FakeClock()
        self.org = sample_data.build(self.clock)
        self.desk = self.org.desk

    def u(self, key):
        return self.org.get(key)

    @staticmethod
    def payment_outage():
        return (IncidentRequest.builder("Payment application unavailable",
                                        "Users are unable to complete transactions on the payment app.")
                .impact("ORGANIZATION").urgency("CRITICAL").affected_users(500))

    def report_payment(self):
        return self.desk.report_incident(self.u("emp1"), self.payment_outage().build())

    def work(self, inc):
        self.desk.acknowledge(inc.assignee, inc.incident_id)
        self.desk.start_work(inc.assignee, inc.incident_id)

    def resolve(self, inc):
        self.desk.resolve(inc.assignee, inc.incident_id, "Restarted the failing service node.",
                          "Node memory leak", "Add heap alert")

    def full_lifecycle(self, inc):
        self.work(inc)
        self.resolve(inc)
        self.desk.verify(self.u("emp1"), inc.incident_id)
        self.desk.close(self.u("emp1"), inc.incident_id)


@pytest.fixture
def env():
    return Env()
