"""
Database tests for itsm.api.sqlite_storage.SqliteStorage.   Run:  python -m pytest tests/test_sqlite_storage.py -v

Part A  adapter on its own (hand-built records)   : schema, save/load, update, delete, relationships
Part B  restart persistence                        : close the database, open it again, compare
Part C  real ServiceDesk integration               : attach_storage, full workflows, monitor, seeding
"""
from __future__ import annotations

import sqlite3
import threading
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from itsm.api.init_db import open_desk
from itsm.api.sqlite_storage import SCHEMA_VERSION, TABLES, SqliteStorage
from itsm.domain import IncidentRequest, ServiceDesk
from itsm.domain.catalog import Category
from itsm.domain.common import EventType, FakeClock, Priority, Role
from itsm.domain.events import DomainEvent
from itsm.domain.exceptions import PersistenceError
from itsm.domain.incident import Note, Resolution
from itsm.domain.persistence import IncidentRecord, ServiceRecord, UserRecord
from itsm.domain.sample_data import PASSWORD, seed
from itsm.domain.sla import SLAPolicy

T0 = datetime(2026, 11, 7, 4, 30, tzinfo=timezone.utc)


# ───────────────────────────── helpers / fixtures ───────────────────────────────────────────
@pytest.fixture
def db_path(tmp_path):
    return tmp_path / "itsm.db"


@pytest.fixture
def storage(db_path):
    s = SqliteStorage(db_path)
    yield s
    try:
        s.close()
    except PersistenceError:
        pass


def employee(uid="E1", email="e1@corp.in") -> UserRecord:
    return UserRecord(uid, "Emp " + uid, email, Role.EMPLOYEE, "c2FsdA==:aGFzaA==", True, "Finance")


def technician(uid="T1", email="t1@corp.in", skills=None) -> UserRecord:
    return UserRecord(uid, "Tech " + uid, email, Role.TECHNICIAN, "c2FsdA==:aGFzaA==", True, None,
                      skills if skills is not None else {"NETWORK": 5, "HARDWARE": 3}, 20, 4.5, True)


def service(sid="SVC-A", deps=(), kws=("alpha", "beta")) -> ServiceRecord:
    return ServiceRecord(sid, "Service " + sid, 4, "NETWORK", tuple(kws), tuple(deps), "Ops Team")


def incident(iid="INC1001", reporter="E1", svc="SVC-A", assignee=None, **kw) -> IncidentRecord:
    base = dict(
        incident_id=iid, title="Printer is broken", description="Nothing prints at all today",
        reporter_id=reporter, service_id=svc, impact="HIGH", urgency="MEDIUM", affected_users=7,
        created_at=T0, status="ASSIGNED", category="HARDWARE", category_confidence=0.5, priority="P2",
        priority_explanation={"strategy": "weighted", "score": 31.2, "thresholds": "P1≥48, P2≥24"},
        assignee_id=assignee, previous_assignee_id=None, assignment_reason="smart strategy: skill 5/5",
        resolved_at=None, closed_at=None, feedback_rating=None, feedback_comment=None, feedback_at=None,
        escalation_level=0, escalated_to=None, related_incidents=(), reopen_count=0,
        sla_paused_since=None, sla_paused_seconds=0.0, sla_responded_at=None, sla_resolved_at=None,
        sla_response_breached=False, sla_resolution_breached=False, sla_warning_sent=False,
        sla_breach_notified=False, notes=(), resolutions=())
    base.update(kw)
    return IncidentRecord(**base)


def populate(s: SqliteStorage) -> None:
    """Minimal valid world: 1 employee, 1 technician, 2 services (B depends on A)."""
    s.save_user(employee())
    s.save_user(technician())
    s.save_service(service("SVC-A"))
    s.save_service(service("SVC-B", deps=["SVC-A"], kws=["gamma"]))


def rows(db_path, sql, *args):
    """Look at the database file with a completely separate connection."""
    con = sqlite3.connect(db_path)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


# ═════════════════════════════ A. schema ═════════════════════════════════════════════════════
class TestSchema:
    def test_all_tables_are_created(self, storage):
        assert set(TABLES) <= set(storage.table_names())
        assert len(TABLES) == 13

    def test_schema_version_is_recorded(self, storage, db_path):
        assert rows(db_path, "PRAGMA user_version")[0][0] == SCHEMA_VERSION

    def test_foreign_keys_are_enforced_on_the_connection(self, storage):
        assert storage._conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_file_database_uses_wal(self, storage):
        assert storage._conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"

    def test_parent_directory_is_created(self, tmp_path):
        s = SqliteStorage(tmp_path / "nested" / "deeper" / "x.db")
        assert (tmp_path / "nested" / "deeper" / "x.db").exists()
        s.close()

    def test_in_memory_database_works(self):
        with SqliteStorage(":memory:") as s:
            s.save_user(employee())
            assert [u.user_id for u in s.load_users()] == ["E1"]

    def test_opening_again_never_erases_data(self, db_path):
        s1 = SqliteStorage(db_path)
        populate(s1)
        s1.close()
        for _ in range(3):                       # re-running initialisation repeatedly
            s = SqliteStorage(db_path)
            assert len(s.load_users()) == 2 and len(s.load_services()) == 2
            s.close()

    def test_newer_schema_version_is_refused(self, db_path):
        SqliteStorage(db_path).close()
        con = sqlite3.connect(db_path)
        con.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
        con.commit()
        con.close()
        with pytest.raises(PersistenceError, match="newer"):
            SqliteStorage(db_path)

    def test_unopenable_path_raises_persistence_error(self, tmp_path):
        blocker = tmp_path / "file.txt"
        blocker.write_text("x")
        with pytest.raises(PersistenceError):
            SqliteStorage(blocker / "sub" / "x.db")

    def test_use_after_close_raises_persistence_error(self, db_path):
        s = SqliteStorage(db_path)
        s.close()
        with pytest.raises(PersistenceError):
            s.save_user(employee())

    def test_empty_database_loads_empty_lists(self, storage):
        assert storage.load_users() == [] and storage.load_services() == []
        assert storage.load_incidents() == [] and storage.load_audit_events() == []
        assert storage.load_categories() == [] and storage.load_sla_policies() == []


# ═════════════════════════════ A. users ══════════════════════════════════════════════════════
class TestUsers:
    def test_employee_round_trip(self, storage):
        storage.save_user(employee())
        assert storage.load_users() == [employee()]

    def test_technician_round_trip_with_skills(self, storage):
        storage.save_user(technician())
        (loaded,) = storage.load_users()
        assert loaded == technician()
        assert loaded.skills == {"NETWORK": 5, "HARDWARE": 3} and loaded.available is True

    def test_update_changes_fields_and_replaces_skills(self, storage):
        storage.save_user(technician())
        storage.save_user(replace(technician(), name="Renamed", active=False, available=False,
                                  skills={"DATABASE": 4}, max_workload_points=30))
        (u,) = storage.load_users()
        assert (u.name, u.active, u.available, u.max_workload_points) == ("Renamed", False, False, 30)
        assert u.skills == {"DATABASE": 4}

    def test_update_does_not_duplicate_or_reorder_rows(self, storage):
        for i in range(3):
            storage.save_user(employee(f"E{i}", f"e{i}@corp.in"))
        storage.save_user(replace(employee("E0", "e0@corp.in"), name="Changed"))
        assert [u.user_id for u in storage.load_users()] == ["E0", "E1", "E2"]

    def test_update_of_a_user_keeps_their_incidents(self, storage):
        """UPSERT (not INSERT OR REPLACE) must not trip the foreign-key rules."""
        populate(storage)
        storage.save_incident(incident())
        storage.save_user(replace(employee(), name="New Name"))
        assert len(storage.load_incidents()) == 1

    def test_duplicate_email_is_rejected_case_insensitively(self, storage):
        storage.save_user(employee("E1", "same@corp.in"))
        with pytest.raises(PersistenceError):
            storage.save_user(employee("E2", "SAME@corp.in"))
        assert len(storage.load_users()) == 1

    def test_skill_level_out_of_range_is_rejected(self, storage):
        with pytest.raises(PersistenceError):
            storage.save_user(technician(skills={"NETWORK": 9}))
        assert storage.load_users() == []             # whole save rolled back

    def test_delete_user(self, storage):
        storage.save_user(technician())
        assert storage.delete_user("T1") is True
        assert storage.load_users() == []
        assert rows(storage.path, "SELECT COUNT(*) FROM technician_skills")[0][0] == 0   # cascade
        assert storage.delete_user("T1") is False

    def test_cannot_delete_a_user_that_incidents_reference(self, storage):
        populate(storage)
        storage.save_incident(incident())
        with pytest.raises(PersistenceError):
            storage.delete_user("E1")
        assert len(storage.load_users()) == 2


# ═════════════════════════════ A. services ═══════════════════════════════════════════════════
class TestServices:
    def test_round_trip_keywords_dependencies_and_owner(self, storage):
        populate(storage)
        a, b = storage.load_services()
        assert a == service("SVC-A")
        assert b.depends_on == ("SVC-A",) and b.keywords == ("gamma",) and b.owner == "Ops Team"

    def test_dependency_order_is_preserved(self, storage):
        for sid in ("X", "Y", "Z"):
            storage.save_service(service(sid))
        storage.save_service(service("W", deps=["Z", "X", "Y"]))
        assert storage.load_services()[-1].depends_on == ("Z", "X", "Y")

    def test_update_replaces_keywords_and_dependencies(self, storage):
        populate(storage)
        storage.save_service(service("SVC-C"))
        storage.save_service(replace(service("SVC-B"), name="Renamed", keywords=("new",), depends_on=("SVC-C",)))
        b = [s for s in storage.load_services() if s.service_id == "SVC-B"][0]
        assert (b.name, b.keywords, b.depends_on) == ("Renamed", ("new",), ("SVC-C",))
        assert len(storage.load_services()) == 3

    def test_dependency_on_unknown_service_is_rejected(self, storage):
        storage.save_service(service("SVC-A"))
        with pytest.raises(PersistenceError):
            storage.save_service(service("SVC-B", deps=["NOPE"]))
        assert [s.service_id for s in storage.load_services()] == ["SVC-A"]

    def test_self_dependency_is_rejected(self, storage):
        with pytest.raises(PersistenceError):
            storage.save_service(service("SVC-A", deps=["SVC-A"]))

    def test_criticality_range_is_enforced(self, storage):
        with pytest.raises(PersistenceError):
            storage.save_service(replace(service(), business_criticality=6))

    def test_delete_service_cascades_to_keywords(self, storage):
        storage.save_service(service())
        assert storage.delete_service("SVC-A") is True
        assert rows(storage.path, "SELECT COUNT(*) FROM service_keywords")[0][0] == 0

    def test_cannot_delete_service_that_others_depend_on(self, storage):
        populate(storage)
        with pytest.raises(PersistenceError):
            storage.delete_service("SVC-A")
        assert len(storage.load_services()) == 2

    def test_cannot_delete_service_used_by_an_incident(self, storage):
        populate(storage)
        storage.save_incident(incident(svc="SVC-B"))
        with pytest.raises(PersistenceError):
            storage.delete_service("SVC-B")


# ═════════════════════════════ A. incidents + relationships ═════════════════════════════════
class TestIncidents:
    def test_full_round_trip(self, storage):
        populate(storage)
        notes = (Note("T1", "first note", T0 + timedelta(minutes=1), True),
                 Note("E1", "QUESTION: any news?", T0 + timedelta(minutes=2), False))
        res = (Resolution("Replaced the toner cartridge", "Worn part", "Order spares", "T1", T0 + timedelta(hours=1)),)
        rec = incident(assignee="T1", previous_assignee_id="T1", related_incidents=("INC1002", "INC0999"),
                       notes=notes, resolutions=res, status="RESOLVED", resolved_at=T0 + timedelta(hours=1),
                       feedback_rating=4, feedback_comment="thanks", feedback_at=T0 + timedelta(hours=2),
                       escalation_level=2, escalated_to="SYSTEM_ADMIN", reopen_count=1,
                       sla_paused_since=T0 + timedelta(minutes=5), sla_paused_seconds=125.5,
                       sla_responded_at=T0 + timedelta(minutes=3), sla_resolved_at=T0 + timedelta(hours=1),
                       sla_response_breached=True, sla_warning_sent=True, category_confidence=0.75)
        rec = replace(rec, related_incidents=("INC0999", "INC1002"))     # stored sorted, like to_record()
        storage.save_incident(rec)
        assert storage.load_incidents() == [rec]

    def test_datetimes_come_back_timezone_aware_utc(self, storage):
        populate(storage)
        ist = timezone(timedelta(hours=5, minutes=30))
        storage.save_incident(incident(created_at=datetime(2026, 11, 7, 10, 0, tzinfo=ist)))
        (loaded,) = storage.load_incidents()
        assert loaded.created_at.tzinfo is not None and loaded.created_at == T0

    def test_unicode_in_text_and_explanation(self, storage):
        populate(storage)
        storage.save_incident(incident(title="Ünïcode → 日本語 ✓", description="Ünïcode body → ✓ ✓ ✓ ✓"))
        (loaded,) = storage.load_incidents()
        assert loaded.title == "Ünïcode → 日本語 ✓" and loaded.priority_explanation["thresholds"] == "P1≥48, P2≥24"

    def test_update_overwrites_instead_of_duplicating(self, storage):
        populate(storage)
        storage.save_incident(incident())
        storage.save_incident(incident(status="IN_PROGRESS", assignee="T1", reopen_count=3))
        (loaded,) = storage.load_incidents()
        assert (loaded.status, loaded.assignee_id, loaded.reopen_count) == ("IN_PROGRESS", "T1", 3)

    def test_update_replaces_children(self, storage):
        populate(storage)
        n1 = Note("T1", "one", T0)
        n2 = Note("T1", "two", T0 + timedelta(minutes=1))
        storage.save_incident(incident(notes=(n1,), related_incidents=("INC2000",)))
        storage.save_incident(incident(notes=(n1, n2), related_incidents=("INC3000",)))
        (loaded,) = storage.load_incidents()
        assert loaded.notes == (n1, n2) and loaded.related_incidents == ("INC3000",)

    def test_notes_keep_their_order(self, storage):
        populate(storage)
        notes = tuple(Note("T1", f"note {i}", T0 + timedelta(minutes=10 - i)) for i in range(5))
        storage.save_incident(incident(notes=notes))
        assert storage.load_incidents()[0].notes == notes

    def test_incidents_load_in_creation_order(self, storage):
        populate(storage)
        storage.save_incident(incident("INC1002", created_at=T0 + timedelta(hours=1)))
        storage.save_incident(incident("INC1001", created_at=T0))
        assert [i.incident_id for i in storage.load_incidents()] == ["INC1001", "INC1002"]

    def test_unchanged_incident_is_not_rewritten(self, storage):
        populate(storage)
        rec = incident()
        storage.save_incident(rec)
        before = storage._conn.total_changes
        for _ in range(5):                         # what run_monitor() does every minute
            storage.save_incident(rec)
        assert storage._conn.total_changes == before
        storage.save_incident(replace(rec, status="CLOSED"))
        assert storage._conn.total_changes > before

    # ---- relationships / foreign keys ------------------------------------------------------
    def test_unknown_reporter_is_rejected(self, storage):
        populate(storage)
        with pytest.raises(PersistenceError):
            storage.save_incident(incident(reporter="GHOST"))
        assert storage.load_incidents() == []

    def test_unknown_service_is_rejected(self, storage):
        populate(storage)
        with pytest.raises(PersistenceError):
            storage.save_incident(incident(svc="SVC-NOPE"))

    def test_unknown_assignee_is_rejected(self, storage):
        populate(storage)
        with pytest.raises(PersistenceError):
            storage.save_incident(incident(assignee="GHOST"))

    def test_failed_save_is_atomic_and_leaves_no_partial_rows(self, storage):
        populate(storage)
        storage.save_incident(incident())
        bad = incident(status="CLOSED", notes=(Note("GHOST", "x", T0),))      # note author does not exist
        with pytest.raises(PersistenceError):
            storage.save_incident(bad)
        (loaded,) = storage.load_incidents()
        assert loaded.status == "ASSIGNED" and loaded.notes == ()              # old version intact

    def test_failed_save_is_retried_not_skipped(self, storage):
        populate(storage)
        bad = incident(notes=(Note("NEW-USER", "x", T0),))
        with pytest.raises(PersistenceError):
            storage.save_incident(bad)
        storage.save_user(employee("NEW-USER", "nu@corp.in"))
        storage.save_incident(bad)                                              # now it must really save
        assert storage.load_incidents()[0].notes[0].author_id == "NEW-USER"

    def test_link_to_an_incident_that_is_not_saved_yet_is_allowed(self, storage):
        """The desk saves the OLDER incident (linking to the new one) before the new one exists."""
        populate(storage)
        storage.save_incident(incident("INC1001", related_incidents=("INC1002",)))
        storage.save_incident(incident("INC1002", related_incidents=("INC1001",)))
        assert [i.related_incidents for i in storage.load_incidents()] == [("INC1002",), ("INC1001",)]

    def test_resolution_technician_must_exist(self, storage):
        populate(storage)
        r = Resolution("Fixed the thing properly", "cause", "", "GHOST", T0)
        with pytest.raises(PersistenceError):
            storage.save_incident(incident(resolutions=(r,)))

    def test_delete_incident_cascades_but_keeps_audit(self, storage):
        populate(storage)
        storage.save_incident(incident(notes=(Note("T1", "n", T0),), related_incidents=("INC9",)))
        storage.save_audit_event(DomainEvent(EventType.INCIDENT_CREATED, "INC1001", "E1", T0, "created"))
        assert storage.delete_incident("INC1001") is True
        for table in ("incidents", "incident_notes", "incident_resolutions", "incident_links"):
            assert rows(storage.path, f"SELECT COUNT(*) FROM {table}")[0][0] == 0
        assert len(storage.load_audit_events()) == 1
        assert storage.delete_incident("INC1001") is False

    def test_deleted_incident_can_be_saved_again(self, storage):
        populate(storage)
        rec = incident()
        storage.save_incident(rec)
        storage.delete_incident("INC1001")
        storage.save_incident(rec)                  # the skip-if-unchanged cache must have been cleared
        assert len(storage.load_incidents()) == 1

    def test_database_has_no_foreign_key_violations(self, storage):
        populate(storage)
        storage.save_incident(incident(assignee="T1", notes=(Note("T1", "n", T0),)))
        assert storage.integrity_problems() == []


# ═════════════════════════════ A. optional tables ════════════════════════════════════════════
class TestOptionalTables:
    def test_audit_events_round_trip_in_order(self, storage):
        evs = [DomainEvent(EventType.INCIDENT_CREATED, "INC1", "E1", T0, "created", None, "NEW", ("T1", "L1"), True),
               DomainEvent(EventType.STATUS_CHANGED, "INC1", "SYSTEM", T0 + timedelta(minutes=1),
                           "→ ASSIGNED", "NEW", "ASSIGNED", (), False)]
        for e in evs:
            storage.save_audit_event(e)
        assert storage.load_audit_events() == evs

    def test_categories_round_trip_and_update(self, storage):
        storage.save_category(Category("Printing", "Printers", {"toner", "print"}))
        storage.save_category(Category("PRINTING", "Printers and scanners", {"toner", "scan"}))
        (c,) = storage.load_categories()
        assert c.name == "PRINTING" and c.description == "Printers and scanners" and c.keywords == {"toner", "scan"}
        assert storage.delete_category("printing") is True and storage.load_categories() == []

    def test_sla_policies_default_and_per_service(self, storage):
        storage.save_service(service("SVC-A"))
        default = SLAPolicy(Priority.P1, timedelta(minutes=10), timedelta(hours=1), 0.8)
        special = SLAPolicy(Priority.P1, timedelta(minutes=2), timedelta(minutes=20), 0.5, "SVC-A")
        storage.save_sla_policy(default)
        storage.save_sla_policy(special)
        storage.save_sla_policy(replace(default, resolution_target=timedelta(hours=2)))    # update
        loaded = storage.load_sla_policies()
        assert len(loaded) == 2
        assert special in loaded and replace(default, resolution_target=timedelta(hours=2)) in loaded
        assert storage.delete_sla_policy(Priority.P1, "SVC-A") is True and len(storage.load_sla_policies()) == 1

    def test_sla_policy_for_unknown_service_is_rejected(self, storage):
        with pytest.raises(PersistenceError):
            storage.save_sla_policy(SLAPolicy(Priority.P2, timedelta(minutes=1), timedelta(hours=1), 0.5, "NOPE"))


# ═════════════════════════════ A. concurrency ════════════════════════════════════════════════
def test_concurrent_saves_from_many_threads(storage):
    populate(storage)
    errors = []

    def worker(n):
        try:
            for k in range(20):
                storage.save_incident(incident(f"INC{n}{k:02d}", created_at=T0 + timedelta(seconds=n * 100 + k)))
                storage.save_audit_event(DomainEvent(EventType.NOTE_ADDED, f"INC{n}{k:02d}", "E1", T0, "x"))
        except Exception as e:                                           # pragma: no cover
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(1, 6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert errors == []
    assert len(storage.load_incidents()) == 100 and len(storage.load_audit_events()) == 100


# ═════════════════════════════ B. restart persistence (adapter only) ════════════════════════
def test_everything_survives_close_and_reopen(db_path):
    s1 = SqliteStorage(db_path)
    populate(s1)
    s1.save_category(Category("PRINTING", "Printers", {"toner"}))
    s1.save_sla_policy(SLAPolicy(Priority.P3, timedelta(hours=2), timedelta(hours=9), 0.7))
    rec = incident(assignee="T1", notes=(Note("T1", "hello", T0),), related_incidents=("INC7",))
    s1.save_incident(rec)
    s1.save_audit_event(DomainEvent(EventType.INCIDENT_CREATED, "INC1001", "E1", T0, "created"))
    before = (s1.load_users(), s1.load_services(), s1.load_incidents(), s1.load_categories(),
              s1.load_sla_policies(), s1.load_audit_events())
    s1.close()

    s2 = SqliteStorage(db_path)                                    # "restart the application"
    after = (s2.load_users(), s2.load_services(), s2.load_incidents(), s2.load_categories(),
             s2.load_sla_policies(), s2.load_audit_events())
    assert after[0] == before[0] and after[1] == before[1] and after[2] == before[2] == [rec]
    assert [c.name for c in after[3]] == ["PRINTING"] and after[4] == before[4] and after[5] == before[5]
    s2.close()


def test_updates_and_deletes_also_survive_restart(db_path):
    s1 = SqliteStorage(db_path)
    populate(s1)
    s1.save_incident(incident())
    s1.save_incident(incident(status="CLOSED"))
    s1.save_user(technician("T9", "t9@corp.in"))
    s1.delete_user("T9")
    s1.close()
    s2 = SqliteStorage(db_path)
    assert s2.load_incidents()[0].status == "CLOSED"
    assert [u.user_id for u in s2.load_users()] == ["E1", "T1"]
    s2.close()


# ═════════════════════════════ C. ServiceDesk integration ═══════════════════════════════════
def new_desk(db_path, clock):
    storage = SqliteStorage(db_path)
    desk = ServiceDesk(clock)
    desk.attach_storage(storage)
    return desk, storage


def payment_request(title="Payment application down", users=600, impact="ORGANIZATION", urgency="CRITICAL"):
    return (IncidentRequest.builder(title, "Customers cannot complete payment transactions at checkout.")
            .service("SVC-PAY").impact(impact).urgency(urgency).affected_users(users).build())


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def world(db_path, clock):
    desk, storage = new_desk(db_path, clock)
    org = seed(desk)
    yield desk, org, storage
    try:
        storage.close()
    except PersistenceError:
        pass


class TestServiceDeskIntegration:
    def test_seeding_writes_users_services_and_dependencies(self, world):
        desk, org, storage = world
        c = storage.counts()
        assert c["users"] == 10 and c["services"] == 7 and c["service_dependencies"] == 6
        assert c["technician_skills"] > 0 and storage.integrity_problems() == []

    def test_reported_incident_is_saved_with_audit_trail(self, world):
        desk, org, storage = world
        inc = desk.report_incident(org.get("emp1"), payment_request())
        (rec,) = storage.load_incidents()
        assert rec.incident_id == inc.incident_id == "INC1001" and rec.priority == "P1"
        assert rec.assignee_id == inc.assignee.user_id
        assert rec.priority_explanation["strategy"] == "weighted"
        assert len(storage.load_audit_events()) == len(desk.audit.all()) > 0

    def test_full_lifecycle_survives_restart_exactly(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        emp = org.get("emp1")
        inc = desk.report_incident(emp, payment_request())
        tech = inc.assignee
        iid = inc.incident_id
        desk.acknowledge(tech, iid)
        desk.start_work(tech, iid)
        desk.add_note(tech, iid, "Checking the connection pool", True)
        desk.request_info(tech, iid, "Which region is affected?")
        clock.advance(minutes=10)
        desk.provide_info(emp, iid, "All regions")
        desk.resolve(tech, iid, "Restarted the pool service", "Pool exhausted", "Add alerting")
        desk.verify(emp, iid)
        desk.give_feedback(emp, iid, 5, "Quick fix")
        desk.close(org.get("admin"), iid)
        before = {i.incident_id: i.to_dict(desk.now()) for i in desk._incidents.find_all()}
        before_audit = [e.to_dict() for e in desk.audit.all()]
        storage.close()

        desk2, storage2 = new_desk(db_path, clock)               # ← restart
        after = {i.incident_id: i.to_dict(desk2.now()) for i in desk2._incidents.find_all()}
        assert after == before
        assert [e.to_dict() for e in desk2.audit.all()] == before_audit
        restored = desk2.get_incident(desk2.user("A001"), iid)
        assert restored.status == "CLOSED" and len(restored.resolutions) == 1 and len(restored.notes) >= 3
        assert restored.feedback.rating == 5
        storage2.close()

    def test_users_can_still_log_in_after_restart(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        seed(desk)
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)
        assert desk2.login("asha@corp.in", PASSWORD).role == Role.SYSTEM_ADMIN
        assert desk2.login("tara@corp.in", PASSWORD).user_id == "T201"
        storage2.close()

    def test_numbering_continues_after_restart(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        desk.report_incident(org.get("emp1"), payment_request())
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)
        new = desk2.report_incident(desk2.user("E102"), payment_request("Second payment problem", 5, "LOW", "LOW"))
        assert new.incident_id == "INC1002"
        storage2.close()

    def test_technician_workload_and_history_are_rebuilt(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        inc = desk.report_incident(org.get("emp1"), payment_request())           # P1 = 8 points
        tech_id = inc.assignee.user_id
        points = inc.assignee.workload_points
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)
        t = desk2.user(tech_id)
        assert t.workload_points == points == Priority.P1.workload_points
        assert t.active_incident_ids == {"INC1001"}
        storage2.close()

    def test_duplicate_links_are_saved_in_both_directions(self, world, db_path, clock):
        desk, org, storage = world
        a = desk.report_incident(org.get("emp1"), payment_request())
        b = desk.report_incident(org.get("emp2"), payment_request("Payment application failing", 40, "HIGH", "HIGH"))
        links = rows(db_path, "SELECT incident_id, related_id FROM incident_links ORDER BY 1, 2")
        assert (a.incident_id, b.incident_id) in links and (b.incident_id, a.incident_id) in links
        assert storage.integrity_problems() == []

    def test_admin_changes_are_persisted(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        admin = org.get("admin")
        desk.update_technician_skills(admin, "T204", {"NETWORK": 4})
        desk.set_availability(admin, "T202", False)
        desk.deactivate_user(admin, "E103")
        desk.add_category(admin, "printing", {"toner", "cartridge"}, "Printers and toner")
        desk.configure_sla(admin, SLAPolicy(Priority.P1, timedelta(minutes=3), timedelta(minutes=20), 0.6))
        storage.close()

        desk2, storage2 = new_desk(db_path, clock)
        assert desk2.user("T204").skills == {"NETWORK": 4}
        assert desk2.user("T202").is_available() is False
        assert desk2.user("E103").is_active is False
        assert desk2.categories.exists("PRINTING") and "toner" in desk2.categories.get("PRINTING").keywords
        assert desk2._sla_book.policy_for(Priority.P1).response_target == timedelta(minutes=3)
        storage2.close()

    def test_service_catalog_and_dependency_graph_are_rebuilt(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        seed(desk)
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)
        assert desk2.catalog.upstream_of("SVC-RPT") == {"SVC-PAY", "SVC-AUTH", "SVC-DB"}
        assert desk2.catalog.get("SVC-PAY").depends_on == ("SVC-DB", "SVC-AUTH")
        assert "postgres" in desk2.catalog.get("SVC-DB").keywords
        storage2.close()

    def test_sla_breach_state_is_persisted_by_the_monitor(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        inc = desk.report_incident(org.get("emp1"), payment_request())
        clock.advance(minutes=40)                                                # P1 = 30 min target
        result = desk.run_monitor()
        assert inc.incident_id in result.breaches and result.escalations
        before = inc.to_dict(desk.now())
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)
        again = desk2.get_incident(desk2.user("A001"), inc.incident_id)
        assert again.to_dict(desk2.now()) == before
        assert again.sla.breach_notified is True and again.escalation_level > 0
        assert desk2.run_monitor().breaches == []                                # notified only once
        storage2.close()

    def test_monitor_on_idle_system_does_not_write(self, world, clock):
        desk, org, storage = world
        desk.report_incident(org.get("emp1"), payment_request())
        desk.run_monitor()                                                       # first pass may save flags
        before = storage._conn.total_changes
        for _ in range(3):
            desk.run_monitor()
        assert storage._conn.total_changes == before

    def test_reopen_and_sticky_reassignment_survive_restart(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        emp = org.get("emp1")
        inc = desk.report_incident(emp, payment_request())
        tech, iid = inc.assignee, inc.incident_id
        desk.acknowledge(tech, iid)
        desk.start_work(tech, iid)
        desk.resolve(tech, iid, "Restarted the pool service", "Pool exhausted")
        desk.reopen(emp, iid, "It broke again")
        assert desk.get_incident(emp, iid).assignee == tech                      # sticky
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)
        again = desk2.get_incident(desk2.user("A001"), iid)
        assert again.status == "ASSIGNED" and again.reopen_count == 1 and again.assignee.user_id == tech.user_id
        assert len(again.resolutions) == 1
        storage2.close()

    def test_audit_trail_is_not_duplicated_by_restarts(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        tech_id = desk.report_incident(org.get("emp1"), payment_request()).assignee.user_id
        n = len(desk.audit.all())
        storage.close()
        for _ in range(3):
            d, s = new_desk(db_path, clock)
            assert len(d.audit.all()) == n
            s.close()
        d, s = new_desk(db_path, clock)
        d.add_note(d.user(tech_id), "INC1001", "one more event")
        assert len(s.load_audit_events()) == n + 1
        s.close()

    def test_database_failure_surfaces_as_persistence_error(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        org = seed(desk)
        storage.close()
        with pytest.raises(PersistenceError) as err:
            desk.report_incident(org.get("emp1"), payment_request())
        assert err.value.http_status == 503


class TestSeedingSafety:
    def test_open_desk_seeds_an_empty_database_once(self, db_path, clock):
        desk, storage, seeded = open_desk(str(db_path), clock=clock)
        assert seeded is True and storage.counts()["incidents"] == 4
        counts = storage.counts()
        storage.close()
        desk2, storage2, seeded2 = open_desk(str(db_path), clock=clock)
        assert seeded2 is False and storage2.counts() == counts
        storage2.close()

    def test_seeding_does_not_touch_an_existing_database(self, db_path, clock):
        desk, storage = new_desk(db_path, clock)
        admin_only = desk  # a database that already has its own data
        from itsm.domain.users import Administrator
        desk.register_user_bootstrap(Administrator("X1", "Existing Admin", "x1@corp.in", PASSWORD))
        storage.close()
        desk2, storage2, seeded = open_desk(str(db_path), clock=clock)
        assert seeded is False
        assert [u.user_id for u in storage2.load_users()] == ["X1"] and storage2.load_services() == []
        storage2.close()

    def test_seed_without_sample_incidents(self, db_path, clock):
        _, storage, seeded = open_desk(str(db_path), sample_incidents=False, clock=clock)
        assert seeded and storage.counts()["incidents"] == 0 and storage.counts()["users"] == 10
        storage.close()

    def test_no_seed_option_creates_empty_tables_only(self, db_path, clock):
        _, storage, seeded = open_desk(str(db_path), seed_if_empty=False, clock=clock)
        assert not seeded and storage.counts()["users"] == 0
        storage.close()

    def test_sample_data_has_a_clean_integrity_check_and_restores(self, db_path, clock):
        _, storage, _ = open_desk(str(db_path), clock=clock)
        assert storage.integrity_problems() == []
        storage.close()
        desk2, storage2 = new_desk(db_path, clock)                              # full rebuild from sample data
        assert len(desk2._incidents.find_all()) == 4 and not desk2.is_empty()
        storage2.close()
