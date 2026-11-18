"""
Create / open the SQLite database and (on the very first run only) load the sample organisation.

    python -m itsm.api.init_db                       # data/itsm.db (or $ITSM_DB), seeded if empty
    python -m itsm.api.init_db --db other.db
    python -m itsm.api.init_db --no-sample-incidents # users + services only
    python -m itsm.api.init_db --no-seed             # just create the empty tables

SAFE TO RE-RUN: the schema uses CREATE TABLE IF NOT EXISTS and sample data is loaded only when
the database has no users. There is deliberately no "reset" option; to start over, stop the
app and delete the .db / .db-wal / .db-shm files yourself.

From code (e.g. FastAPI startup) use `open_desk()`; it does the same thing and returns the desk.
"""
from __future__ import annotations

import argparse
import os

from ..domain import IncidentRequest, ServiceDesk
from ..domain.common import Clock
from ..domain.sample_data import Org, seed
from .sqlite_storage import SqliteStorage

DEFAULT_DB = os.environ.get("ITSM_DB", "data/itsm.db")


def add_sample_incidents(desk: ServiceDesk, org: Org) -> None:
    """A handful of realistic incidents, created through the normal ServiceDesk workflow."""
    b = IncidentRequest.builder
    payment = desk.report_incident(org.get("emp1"), b(
        "Payment application is down",
        "Customers cannot complete payment transactions at checkout since this morning.")
        .service("SVC-PAY").impact("ORGANIZATION").urgency("CRITICAL").affected_users(600).build())
    desk.report_incident(org.get("emp2"), b(
        "Office WiFi keeps disconnecting",
        "The sales floor WiFi drops every few minutes, video calls are unusable.")
        .service("SVC-NET").impact("MEDIUM").urgency("MEDIUM").affected_users(25).build())
    printer = desk.report_incident(org.get("emp3"), b(
        "Printer on floor 3 is jammed",
        "The shared printer shows a paper jam error and will not print anything.")
        .service("SVC-PRINT").impact("LOW").urgency("LOW").affected_users(4).build())
    desk.report_incident(org.get("emp1"), b(
        "Finance dashboard loads very slowly",
        "The monthly finance reporting dashboard takes minutes to open.")
        .service("SVC-RPT").impact("MEDIUM").urgency("LOW").affected_users(12).build())

    # Walk one incident through its lifecycle so the sample data has a note + a resolution.
    tech = printer.assignee
    if tech is not None:
        desk.acknowledge(tech, printer.incident_id)
        desk.start_work(tech, printer.incident_id)
        desk.add_note(tech, printer.incident_id, "Checked the tray, a sheet was stuck in the rollers.", True)
        desk.resolve(tech, printer.incident_id, "Removed the stuck paper and ran a test print.",
                     "Wrong paper size loaded in tray 2", "Label tray 2 with the correct paper size.")
    _ = payment  # (left open and escalating on purpose: good for the SLA demo)


def open_desk(db_path: str = DEFAULT_DB, *, seed_if_empty: bool = True, sample_incidents: bool = True,
              clock: Clock | None = None) -> tuple[ServiceDesk, SqliteStorage, bool]:
    """
    Open the database, rebuild a ServiceDesk from it and seed it ONLY if it has no users yet.
    Returns (desk, storage, seeded). This is also the recommended FastAPI startup call.
    """
    storage = SqliteStorage(db_path)
    desk = ServiceDesk(clock)
    desk.attach_storage(storage)
    seeded = False
    if seed_if_empty and desk.is_empty():
        org = seed(desk)
        if sample_incidents:
            add_sample_incidents(desk, org)
        seeded = True
    return desk, storage, seeded


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(description="Initialise the I-ITSM SQLite database (never erases data).")
    p.add_argument("--db", default=DEFAULT_DB, help=f"database file (default: {DEFAULT_DB})")
    p.add_argument("--no-seed", action="store_true", help="create the tables only, load no sample data")
    p.add_argument("--no-sample-incidents", action="store_true", help="seed users and services but no incidents")
    args = p.parse_args(argv)

    desk, storage, seeded = open_desk(args.db, seed_if_empty=not args.no_seed,
                                      sample_incidents=not args.no_sample_incidents)
    print(f"Database: {args.db}")
    if seeded:
        print("Empty database → sample data loaded (every sample password: Passw0rd!)")
    elif args.no_seed:
        print("Tables ready, no sample data requested.")
    else:
        print("Database already contains data → nothing was changed.")
    for table, n in storage.counts().items():
        print(f"  {table:<22}{n:>6}")
    problems = storage.integrity_problems()
    print("Integrity check:", "OK" if not problems else problems)
    storage.close()


if __name__ == "__main__":
    main()
