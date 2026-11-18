
"""
Create / open the SQLite database and (on the very first run only)
load the sample organisation.

Usage:

    python -m itsm.api.init_db
        # data/itsm.db or $ITSM_DB

    python -m itsm.api.init_db --db other.db

    python -m itsm.api.init_db --no-sample-incidents
        # users + services only

    python -m itsm.api.init_db --no-seed
        # just create the empty tables

SAFE TO RE-RUN:
The schema uses CREATE TABLE IF NOT EXISTS.
Sample data is loaded only when the database has no users.

There is deliberately no reset option.

From code (e.g. FastAPI startup), use open_desk().
It initializes the database and returns the ServiceDesk.
"""

from __future__ import annotations

import argparse
import os

from ..domain import IncidentRequest, ServiceDesk
from ..domain.common import Clock
from ..domain.sample_data import Org, seed
from .sqlite_storage import SqliteStorage


DEFAULT_DB = "data/itsm.db"


def get_database_path(db_path: str | None = None) -> str:
    """
    Resolve the database path.

    Priority:
    1. Explicit db_path argument.
    2. ITSM_DB environment variable.
    3. Default database path.
    """

    return db_path or os.environ.get("ITSM_DB") or DEFAULT_DB


def add_sample_incidents(desk: ServiceDesk, org: Org) -> None:
    """Create realistic sample incidents through the ServiceDesk workflow."""

    builder = IncidentRequest.builder

    payment = desk.report_incident(
        org.get("emp1"),
        builder(
            "Payment application is down",
            "Customers cannot complete payment transactions at checkout since this morning."
        )
        .service("SVC-PAY")
        .impact("ORGANIZATION")
        .urgency("CRITICAL")
        .affected_users(600)
        .build()
    )

    desk.report_incident(
        org.get("emp2"),
        builder(
            "Office WiFi keeps disconnecting",
            "The sales floor WiFi drops every few minutes, video calls are unusable."
        )
        .service("SVC-NET")
        .impact("MEDIUM")
        .urgency("MEDIUM")
        .affected_users(25)
        .build()
    )

    printer = desk.report_incident(
        org.get("emp3"),
        builder(
            "Printer on floor 3 is jammed",
            "The shared printer shows a paper jam error and will not print anything."
        )
        .service("SVC-PRINT")
        .impact("LOW")
        .urgency("LOW")
        .affected_users(4)
        .build()
    )

    desk.report_incident(
        org.get("emp1"),
        builder(
            "Finance dashboard loads very slowly",
            "The monthly finance reporting dashboard takes minutes to open."
        )
        .service("SVC-RPT")
        .impact("MEDIUM")
        .urgency("LOW")
        .affected_users(12)
        .build()
    )

    # Walk one incident through its lifecycle.
    # This gives the sample database a note and resolution.

    tech = printer.assignee

    if tech is not None:
        desk.acknowledge(tech, printer.incident_id)

        desk.start_work(tech, printer.incident_id)

        desk.add_note(
            tech,
            printer.incident_id,
            "Checked the tray, a sheet was stuck in the rollers.",
            True
        )

        desk.resolve(
            tech,
            printer.incident_id,
            "Removed the stuck paper and ran a test print.",
            "Wrong paper size loaded in tray 2",
            "Label tray 2 with the correct paper size."
        )

    # Keep the payment incident open for the SLA demonstration.
    _ = payment


def open_desk(
    db_path: str | None = None,
    *,
    seed_if_empty: bool = True,
    sample_incidents: bool = True,
    clock: Clock | None = None
) -> tuple[ServiceDesk, SqliteStorage, bool]:
    """
    Open the SQLite database and rebuild a ServiceDesk from it.

    Database path priority:
    1. Explicit db_path.
    2. ITSM_DB environment variable.
    3. Default database path.

    Sample data is loaded ONLY if the database has no users.

    Returns:
        (desk, storage, seeded)
    """

    resolved_db_path = get_database_path(db_path)

    storage = SqliteStorage(resolved_db_path)

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
    """Initialize the SQLite database from the command line."""

    parser = argparse.ArgumentParser(
        description="Initialize the I-ITSM SQLite database (never erases data)."
    )

    parser.add_argument(
        "--db",
        default=None,
        help="Database file (overrides ITSM_DB and the default path)."
    )

    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="Create tables only; do not load sample data."
    )

    parser.add_argument(
        "--no-sample-incidents",
        action="store_true",
        help="Seed users and services without sample incidents."
    )

    args = parser.parse_args(argv)

    db_path = get_database_path(args.db)

    desk, storage, seeded = open_desk(
        db_path,
        seed_if_empty=not args.no_seed,
        sample_incidents=not args.no_sample_incidents
    )

    print(f"Database: {db_path}")

    if seeded:
        print(
            "Empty database -> sample data loaded "
            "(every sample password: Passw0rd!)"
        )

    elif args.no_seed:
        print("Tables ready, no sample data requested.")

    else:
        print("Database already contains data -> nothing was changed.")

    for table, count in storage.counts().items():
        print(f"  {table:<22}{count:>6}")

    problems = storage.integrity_problems()

    print(
        "Integrity check:",
        "OK" if not problems else problems
    )

    storage.close()


if __name__ == "__main__":
    main()
