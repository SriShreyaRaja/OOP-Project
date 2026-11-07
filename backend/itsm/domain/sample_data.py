"""A ready-made organisation for the demo, the tests and the video. Every password: Passw0rd!"""
from __future__ import annotations

from dataclasses import dataclass

from .catalog import ITService
from .common import Clock
from .service_desk import ServiceDesk
from .users import Administrator, Employee, ITManager, TeamLead, Technician, User

PASSWORD = "Passw0rd!"


@dataclass
class Org:
    desk: ServiceDesk
    people: dict[str, User]

    def get(self, key: str) -> User:
        return self.people[key]

    def tech(self, key: str) -> Technician:
        return self.people[key]


def build(clock: Clock | None = None) -> Org:
    return seed(ServiceDesk(clock))


def seed(desk: ServiceDesk) -> Org:
    """
    Load the sample organisation into an empty desk.
    Member 3, at startup:  desk.attach_storage(db);  if desk.is_empty(): seed(desk)
    """
    admin = Administrator("A001", "Asha Admin", "asha@corp.in", PASSWORD)
    desk.register_user_bootstrap(admin)

    for s in [ITService("SVC-DB", "Core Database", 5, "DATABASE", "postgres", "database", "db"),
              ITService("SVC-AUTH", "Authentication SSO", 5, "AUTHENTICATION", "login", "sso", "password"),
              ITService("SVC-PAY", "Payment Application", 5, "APPLICATION", "payment", "transaction", "checkout"),
              ITService("SVC-NET", "Office Network", 4, "NETWORK", "wifi", "network", "vpn", "internet"),
              ITService("SVC-MAIL", "Email & Calendar", 3, "APPLICATION", "email", "outlook", "calendar"),
              ITService("SVC-PRINT", "Printing", 1, "HARDWARE", "printer", "print"),
              ITService("SVC-RPT", "Finance Reporting", 3, "APPLICATION", "report", "dashboard")]:
        desk.add_service(admin, s)
    for svc, up in [("SVC-AUTH", "SVC-DB"), ("SVC-PAY", "SVC-DB"), ("SVC-PAY", "SVC-AUTH"),
                    ("SVC-MAIL", "SVC-AUTH"), ("SVC-PRINT", "SVC-NET"), ("SVC-RPT", "SVC-PAY")]:
        desk.add_dependency(admin, svc, up)

    people: dict[str, User] = {
        "admin": admin,
        "manager": ITManager("M001", "Meera Manager", "meera@corp.in", PASSWORD),
        "lead": TeamLead("L001", "Leo Lead", "leo@corp.in", PASSWORD,
                         {"APPLICATION": 4, "DATABASE": 4, "NETWORK": 3}, 16, 9),
        "t_app": Technician("T201", "Tara AppSupport", "tara@corp.in", PASSWORD,
                            {"APPLICATION": 5, "DATABASE": 3}, 20, 4),
        "t_net": Technician("T202", "Nikhil Network", "nikhil@corp.in", PASSWORD,
                            {"NETWORK": 5, "HARDWARE": 3}, 20, 6),
        "t_db": Technician("T203", "Dev DBA", "dev@corp.in", PASSWORD,
                           {"DATABASE": 5, "CLOUD": 3, "APPLICATION": 2}, 20, 7),
        "t_jr": Technician("T204", "Jaya Junior", "jaya@corp.in", PASSWORD,
                           {"SOFTWARE": 3, "HARDWARE": 4, "AUTHENTICATION": 3}, 24, 1),
        "emp1": Employee("E101", "Ravi Finance", "ravi@corp.in", PASSWORD, "Finance"),
        "emp2": Employee("E102", "Sana Sales", "sana@corp.in", PASSWORD, "Sales"),
        "emp3": Employee("E103", "Kiran Ops", "kiran@corp.in", PASSWORD, "Operations"),
    }
    for key, u in people.items():
        if key != "admin":
            desk.register_user(admin, u)
    return Org(desk, people)
