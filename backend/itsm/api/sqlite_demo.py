"""
Working example of the SQLite adapter wired into the real ServiceDesk, including a restart.
It is exactly the sequence the FastAPI startup performs (no endpoints, no auth here).

    python -m itsm.api.sqlite_demo                 # uses a throw-away database file
    python -m itsm.api.sqlite_demo --db data/itsm.db
"""
from __future__ import annotations

import argparse
import tempfile
from pathlib import Path

from ..domain import IncidentRequest, SearchCriteria
from ..domain.common import to_plain
from .init_db import open_desk


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", help="database file (default: a temporary one that is deleted afterwards)")
    args = p.parse_args()
    tmp = None if args.db else tempfile.TemporaryDirectory()
    db = args.db or str(Path(tmp.name) / "demo.db")

    # ── 1. APPLICATION STARTUP ─────────────────────────────────────────────────────────────
    #   open_desk = SqliteStorage(db) + ServiceDesk() + desk.attach_storage(storage)
    #               + seed sample data ONLY if the database has no users yet
    desk, storage, seeded = open_desk(db, sample_incidents=False)
    print(f"[start 1] seeded={seeded}  users={storage.counts()['users']}  incidents={storage.counts()['incidents']}")

    # ── 2. WHAT AN API ROUTE DOES (login → domain call → JSON) ─────────────────────────────
    ravi = desk.login("ravi@corp.in", "Passw0rd!")
    inc = desk.report_incident(ravi, IncidentRequest.builder(
        "Payment application is down", "Customers cannot complete payment transactions at checkout.")
        .service("SVC-PAY").impact("ORGANIZATION").urgency("CRITICAL").affected_users(600).build())
    print(f"[route]   reported {inc.incident_id}: priority {inc.priority.name}, assigned to {inc.assignee.name}")
    tech = inc.assignee
    desk.acknowledge(tech, inc.incident_id)
    desk.start_work(tech, inc.incident_id)
    desk.add_note(tech, inc.incident_id, "Connection pool is exhausted.", internal=True)
    print(f"[route]   JSON status: {to_plain(inc.to_dict(desk.now(), ravi))['status']}")

    # ── 3. SHUT DOWN (every change was already saved: write-through) ───────────────────────
    storage.close()
    del desk, storage

    # ── 4. RESTART: a brand-new process would do exactly this ──────────────────────────────
    desk, storage, seeded = open_desk(db, sample_incidents=False)
    print(f"[start 2] seeded={seeded}  (existing data was kept, nothing re-seeded)")
    restored = desk.get_incident(desk.user("A001"), inc.incident_id)
    print(f"[restart] {restored.incident_id} is {restored.status}, assigned to {restored.assignee.name}, "
          f"{len(restored.notes)} note(s), SLA {restored.sla.status(desk.now()).name}")
    print(f"[restart] technician workload rebuilt: {restored.assignee.workload_points} points")
    print(f"[restart] audit trail restored: {len(desk.audit.for_incident(inc.incident_id))} events")
    print(f"[restart] search works: {[i.incident_id for i in desk.search(desk.user('A001'), SearchCriteria.where().priority('P1').open_only())]}")
    print(f"[restart] login still works: {desk.login('ravi@corp.in', 'Passw0rd!').name}")
    print(f"[health]  database problems: {storage.integrity_problems() or 'none'}")
    storage.close()
    if tmp:
        tmp.cleanup()


if __name__ == "__main__":
    main()
