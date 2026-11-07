# I-ITSM — Database Design (for Member 3)

![ER diagram](diagrams/7-er-diagram.png)

## How persistence works

The domain uses a **write-through** design:

1. Live objects stay in memory (fast, and all business rules run on them).
2. Every change is immediately saved through **one interface, `StorageAdapter`** (`itsm/domain/persistence.py`).
3. At startup, `desk.attach_storage(adapter)` loads everything back and rebuilds technician workloads from the open incidents, so they can never drift out of sync.

Member 3 writes **one class**, `SqliteStorageAdapter(StorageAdapter)`, using Python's built-in `sqlite3` module (nothing to install). The domain hands you plain-data records to save:

| Domain object | Record to save | Rebuilt by |
|---|---|---|
| `User` (all roles) | `UserRecord.from_user(user)` | `record.to_user()` (done for you by `attach_storage`) |
| `Incident` | `incident.to_record()` → `IncidentRecord` | `Incident.restore(...)` (done for you) |
| `ITService` | `ServiceRecord.from_service(service)` | done for you |
| Audit event | `DomainEvent` (already plain data) | done for you |
| `Category`, `SLAPolicy` | already plain | done for you |

Required methods: `save_user` / `load_users`, `save_incident` / `load_incidents`, `save_service` / `load_services`. Optional (defaults do nothing): audit events, categories, SLA policies.

Passwords are stored as a salted PBKDF2 hash string (`"salt:hash"` in Base64, column `password_hash`), never in plain text. Small collections (skills, keywords, related incidents) fit in one text column using `Codec`, e.g. `"NETWORK=5,HARDWARE=3"`. Store datetimes as ISO text (`dt.isoformat()` / `datetime.fromisoformat(s)`).

## Startup code (FastAPI)

```python
from itsm.domain import ServiceDesk, sample_data
from itsm.domain.common import SystemClock

desk = ServiceDesk(SystemClock())
desk.attach_storage(SqliteStorageAdapter("itsm.db"))   # reload everything saved
if desk.is_empty():
    sample_data.seed(desk)                             # first run: create the demo company
```

## Skeleton to fill in

```python
import sqlite3
from itsm.domain.persistence import StorageAdapter, IncidentRecord, Codec
from itsm.domain.exceptions import PersistenceError

class SqliteStorageAdapter(StorageAdapter):
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.executescript(SCHEMA)          # CREATE TABLE IF NOT EXISTS ...

    def save_incident(self, r: IncidentRecord) -> None:
        try:
            with self.conn:                      # one transaction: all or nothing
                self.conn.execute("INSERT OR REPLACE INTO incidents VALUES (?, ?, ...)", (...))
                self.conn.execute("DELETE FROM incident_notes WHERE incident_id = ?", (r.incident_id,))
                self.conn.executemany("INSERT INTO incident_notes (...) VALUES (?, ?, ?, ?, ?)", [...])
                # same for incident_resolutions
        except sqlite3.Error as e:
            raise PersistenceError(f"Could not save {r.incident_id}") from e   # → HTTP 503

    # save_user / load_users / load_incidents / save_service / load_services / save_audit_event ...
```

`InMemoryStorage` (in `persistence.py`) is a complete working example of every method, and the test `test_everything_survives_a_restart` shows the full save → restart → reload cycle. Run the same test against your SQLite adapter to prove it works.

## Tables

| Table | Key columns | Notes |
|---|---|---|
| `users` | `user_id` PK, `email` UNIQUE | `role` decides which class is rebuilt; technician fields are NULL for other roles |
| `services` | `service_id` PK | `depends_on` and `keywords` as text via `Codec` |
| `incidents` | `incident_id` PK; FKs `reporter_id`, `service_id`, `assignee_id` | one column per scalar field of `IncidentRecord`; `priority_explanation` as JSON text |
| `incident_notes` | FK `incident_id` | one row per note |
| `incident_resolutions` | FK `incident_id` | every fix attempt kept, including reopened ones |
| `audit_events` | FK `incident_id` | append-only |
| `categories` | `name` PK | only admin-added categories need storing (defaults are built in) |
| `sla_policies` | (`priority`, `service_id`) | `service_id` NULL = default policy |

## Sample data

`sample_data.seed(desk)` creates: 1 admin, 1 IT manager, 1 team lead, 4 technicians with different skills, 3 employees, and 7 services with dependencies (Payment → Auth → Database, etc.). Every account's password is `Passw0rd!`.
