"""
SQLite implementation of the domain's StorageAdapter (Member 3 / database owner).

    from itsm.api.sqlite_storage import SqliteStorage
    storage = SqliteStorage("data/itsm.db")
    desk = ServiceDesk()
    desk.attach_storage(storage)          # reloads everything saved, then saves every change

Design notes
------------
* Pure standard library (sqlite3). The domain layer is untouched: this class only implements
  the `StorageAdapter` interface from `itsm.domain.persistence`.
* Write-through: the desk calls save_*() on every change, so each save_*() is ONE atomic
  transaction (an incident and its notes/resolutions/links are written together or not at all).
* Saves are UPSERTs (INSERT ... ON CONFLICT DO UPDATE), never INSERT OR REPLACE: REPLACE
  deletes the old row first, which would fire the foreign-key rules and wipe child rows.
* Opening a database never erases anything: the schema uses CREATE TABLE IF NOT EXISTS and the
  schema version is tracked in PRAGMA user_version.
* Thread-safe: FastAPI worker threads may share one SqliteStorage; one connection guarded by an
  RLock, WAL journal for file databases, foreign keys switched ON for every connection.
* Every sqlite3 error is re-raised as PersistenceError (HTTP 503), as persistence.py asks.
* Datetimes are stored as ISO-8601 UTC text; booleans as 0/1; small structured values
  (priority explanation) as JSON text.
"""
from __future__ import annotations

import functools
import json
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import fields
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..domain.catalog import Category
from ..domain.common import EventType, Priority, Role
from ..domain.events import DomainEvent
from ..domain.exceptions import PersistenceError
from ..domain.incident import Note, Resolution
from ..domain.persistence import (Codec, IncidentRecord, ServiceRecord, StorageAdapter,
                                  UserRecord)
from ..domain.sla import SLAPolicy

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id              TEXT PRIMARY KEY,
    name                 TEXT NOT NULL,
    email                TEXT NOT NULL UNIQUE COLLATE NOCASE,
    role                 TEXT NOT NULL,
    password_hash        TEXT NOT NULL,
    active               INTEGER NOT NULL DEFAULT 1 CHECK (active IN (0, 1)),
    department           TEXT,
    max_workload_points  INTEGER NOT NULL DEFAULT 0 CHECK (max_workload_points >= 0),
    years_experience     REAL    NOT NULL DEFAULT 0 CHECK (years_experience >= 0),
    available            INTEGER NOT NULL DEFAULT 0 CHECK (available IN (0, 1))
);

CREATE TABLE IF NOT EXISTS technician_skills (
    user_id   TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    category  TEXT NOT NULL,
    level     INTEGER NOT NULL CHECK (level BETWEEN 1 AND 5),
    PRIMARY KEY (user_id, category)
);

CREATE TABLE IF NOT EXISTS services (
    service_id            TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    business_criticality  INTEGER NOT NULL CHECK (business_criticality BETWEEN 1 AND 5),
    default_category      TEXT NOT NULL,
    owner                 TEXT NOT NULL DEFAULT 'Unassigned'
);

CREATE TABLE IF NOT EXISTS service_keywords (
    service_id  TEXT NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
    keyword     TEXT NOT NULL,
    PRIMARY KEY (service_id, keyword)
);

CREATE TABLE IF NOT EXISTS service_dependencies (
    service_id     TEXT NOT NULL REFERENCES services(service_id) ON DELETE CASCADE,
    depends_on_id  TEXT NOT NULL REFERENCES services(service_id) ON DELETE RESTRICT,
    position       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (service_id, depends_on_id),
    CHECK (service_id <> depends_on_id)
);

CREATE TABLE IF NOT EXISTS categories (
    name         TEXT PRIMARY KEY,
    description  TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS category_keywords (
    category  TEXT NOT NULL REFERENCES categories(name) ON DELETE CASCADE,
    keyword   TEXT NOT NULL,
    PRIMARY KEY (category, keyword)
);

CREATE TABLE IF NOT EXISTS sla_policies (
    policy_id           TEXT PRIMARY KEY,                -- '<service_id or *>/<priority>'
    service_id          TEXT REFERENCES services(service_id) ON DELETE CASCADE,   -- NULL = default
    priority            TEXT NOT NULL,
    response_seconds    REAL NOT NULL CHECK (response_seconds > 0),
    resolution_seconds  REAL NOT NULL CHECK (resolution_seconds > 0),
    warning_threshold   REAL NOT NULL CHECK (warning_threshold > 0 AND warning_threshold < 1)
);

CREATE TABLE IF NOT EXISTS incidents (
    incident_id              TEXT PRIMARY KEY,
    title                    TEXT NOT NULL,
    description              TEXT NOT NULL,
    reporter_id              TEXT NOT NULL REFERENCES users(user_id)       ON DELETE RESTRICT,
    service_id               TEXT NOT NULL REFERENCES services(service_id) ON DELETE RESTRICT,
    impact                   TEXT NOT NULL,
    urgency                  TEXT NOT NULL,
    affected_users           INTEGER NOT NULL CHECK (affected_users >= 1),
    created_at               TEXT NOT NULL,
    status                   TEXT NOT NULL,
    category                 TEXT,
    category_confidence      REAL,
    priority                 TEXT,
    priority_explanation     TEXT NOT NULL DEFAULT '{}',      -- JSON
    assignee_id              TEXT REFERENCES users(user_id) ON DELETE RESTRICT,
    previous_assignee_id     TEXT REFERENCES users(user_id) ON DELETE RESTRICT,
    assignment_reason        TEXT NOT NULL DEFAULT '',
    resolved_at              TEXT,
    closed_at                TEXT,
    feedback_rating          INTEGER CHECK (feedback_rating IS NULL OR feedback_rating BETWEEN 1 AND 5),
    feedback_comment         TEXT,
    feedback_at              TEXT,
    escalation_level         INTEGER NOT NULL DEFAULT 0,
    escalated_to             TEXT,
    reopen_count             INTEGER NOT NULL DEFAULT 0,
    sla_paused_since         TEXT,
    sla_paused_seconds       REAL NOT NULL DEFAULT 0,
    sla_responded_at         TEXT,
    sla_resolved_at          TEXT,
    sla_response_breached    INTEGER NOT NULL DEFAULT 0,
    sla_resolution_breached  INTEGER NOT NULL DEFAULT 0,
    sla_warning_sent         INTEGER NOT NULL DEFAULT 0,
    sla_breach_notified      INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_incidents_status    ON incidents(status);
CREATE INDEX IF NOT EXISTS idx_incidents_assignee  ON incidents(assignee_id);
CREATE INDEX IF NOT EXISTS idx_incidents_reporter  ON incidents(reporter_id);
CREATE INDEX IF NOT EXISTS idx_incidents_service   ON incidents(service_id);

CREATE TABLE IF NOT EXISTS incident_notes (
    incident_id  TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    seq          INTEGER NOT NULL,
    author_id    TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    text         TEXT NOT NULL,
    at           TEXT NOT NULL,
    internal     INTEGER NOT NULL DEFAULT 0 CHECK (internal IN (0, 1)),
    PRIMARY KEY (incident_id, seq)
);

CREATE TABLE IF NOT EXISTS incident_resolutions (
    incident_id        TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    seq                INTEGER NOT NULL,
    description        TEXT NOT NULL,
    root_cause         TEXT NOT NULL,
    preventive_action  TEXT NOT NULL DEFAULT '',
    technician_id      TEXT NOT NULL REFERENCES users(user_id) ON DELETE RESTRICT,
    at                 TEXT NOT NULL,
    PRIMARY KEY (incident_id, seq)
);

-- related_id is intentionally NOT a foreign key: the desk saves the older incident (with a link
-- to the new one) BEFORE the new incident itself is saved, so the target may not exist yet.
CREATE TABLE IF NOT EXISTS incident_links (
    incident_id  TEXT NOT NULL REFERENCES incidents(incident_id) ON DELETE CASCADE,
    related_id   TEXT NOT NULL,
    PRIMARY KEY (incident_id, related_id)
);

-- Append-only history. No foreign keys on purpose: the audit trail must outlive the rows it
-- describes, and actors such as 'SYSTEM' are not rows in users.
CREATE TABLE IF NOT EXISTS audit_events (
    event_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type      TEXT NOT NULL,
    incident_id     TEXT NOT NULL,
    actor_id        TEXT NOT NULL,
    at              TEXT NOT NULL,
    description     TEXT NOT NULL,
    previous_state  TEXT,
    new_state       TEXT,
    recipients      TEXT NOT NULL DEFAULT '',
    urgent          INTEGER NOT NULL DEFAULT 0 CHECK (urgent IN (0, 1))
);
CREATE INDEX IF NOT EXISTS idx_audit_incident ON audit_events(incident_id);
"""

TABLES = ("users", "technician_skills", "services", "service_keywords", "service_dependencies",
          "categories", "category_keywords", "sla_policies", "incidents", "incident_notes",
          "incident_resolutions", "incident_links", "audit_events")

# IncidentRecord fields that map to scalar columns of `incidents` ----------------------------
_DATETIME_FIELDS = {"created_at", "resolved_at", "closed_at", "feedback_at", "sla_paused_since",
                    "sla_responded_at", "sla_resolved_at"}
_BOOL_FIELDS = {"sla_response_breached", "sla_resolution_breached", "sla_warning_sent",
                "sla_breach_notified"}
_CHILD_FIELDS = {"notes", "resolutions", "related_incidents"}
_SCALAR_FIELDS = [f.name for f in fields(IncidentRecord) if f.name not in _CHILD_FIELDS]
_INCIDENT_UPSERT = (
    f"INSERT INTO incidents ({', '.join(_SCALAR_FIELDS)}) "
    f"VALUES ({', '.join('?' for _ in _SCALAR_FIELDS)}) "
    f"ON CONFLICT(incident_id) DO UPDATE SET "
    + ", ".join(f"{c}=excluded.{c}" for c in _SCALAR_FIELDS if c != "incident_id"))


# ───────────────────────────── value converters ─────────────────────────────────────────────
def _dt_out(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:                       # the domain always uses aware UTC; be safe
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def _dt_in(text: str | None) -> datetime | None:
    if text is None:
        return None
    value = datetime.fromisoformat(text)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _db_errors(method):
    """Turn any sqlite3 failure into PersistenceError (the API answers 503 instead of crashing)."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        try:
            return method(self, *args, **kwargs)
        except sqlite3.Error as e:
            raise PersistenceError(f"Database error in {method.__name__}: {e}") from e
    return wrapper


# ───────────────────────────── the adapter ──────────────────────────────────────────────────
class SqliteStorage(StorageAdapter):
    """
    A complete StorageAdapter backed by one SQLite file (or ':memory:' for throw-away tests).
    Implements every method of the interface, including the optional audit / category /
    SLA-policy ones, plus delete_*() helpers the interface itself does not define.
    """

    def __init__(self, path: str | Path = "itsm.db"):
        self._path = str(path)
        self._lock = threading.RLock()
        # Last record written per incident. run_monitor() re-commits every open incident each
        # minute; identical records are skipped so an idle system does no database writes.
        self._saved_incidents: dict[str, IncidentRecord] = {}
        in_memory = self._path == ":memory:"
        try:
            if not in_memory:
                Path(self._path).expanduser().parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._path, check_same_thread=False, timeout=10)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA foreign_keys = ON")
            self._conn.execute("PRAGMA busy_timeout = 5000")
            if not in_memory:
                self._conn.execute("PRAGMA journal_mode = WAL")
                self._conn.execute("PRAGMA synchronous = NORMAL")
            self._init_schema()
        except (sqlite3.Error, OSError) as e:
            raise PersistenceError(f"Cannot open database '{self._path}': {e}") from e

    # ---- lifecycle -----------------------------------------------------------------------
    def _init_schema(self) -> None:
        """Create missing tables. Never drops or alters existing data."""
        version = self._conn.execute("PRAGMA user_version").fetchone()[0]
        if version > SCHEMA_VERSION:
            raise PersistenceError(
                f"Database schema v{version} is newer than this code (v{SCHEMA_VERSION}).")
        self._conn.executescript(SCHEMA)
        if version < SCHEMA_VERSION:
            self._conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error as e:
                raise PersistenceError(f"Error closing database: {e}") from e

    def __enter__(self) -> "SqliteStorage":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    @property
    def path(self) -> str:
        return self._path

    @contextmanager
    def _tx(self):
        """One atomic write transaction: commit on success, roll back on any error."""
        with self._lock:
            with self._conn as conn:
                yield conn

    # ---- diagnostics (used by the init script, the docs and the tests) --------------------
    @_db_errors
    def table_names(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            return sorted(r[0] for r in rows)

    @_db_errors
    def counts(self) -> dict[str, int]:
        with self._lock:
            return {t: self._conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLES}

    @_db_errors
    def integrity_problems(self) -> list[str]:
        """Empty list = healthy. Checks file integrity and that no foreign key is broken."""
        with self._lock:
            problems = [r[0] for r in self._conn.execute("PRAGMA integrity_check") if r[0] != "ok"]
            problems += [f"FK violation in {r[0]} (row {r[1]}) → {r[2]}"
                         for r in self._conn.execute("PRAGMA foreign_key_check")]
            return problems

    # ═════════════════════════════ users ═════════════════════════════════════════════════
    @_db_errors
    def save_user(self, user: UserRecord) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO users (user_id, name, email, role, password_hash, active, department,
                                      max_workload_points, years_experience, available)
                   VALUES (?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       name=excluded.name, email=excluded.email, role=excluded.role,
                       password_hash=excluded.password_hash, active=excluded.active,
                       department=excluded.department,
                       max_workload_points=excluded.max_workload_points,
                       years_experience=excluded.years_experience, available=excluded.available""",
                (user.user_id, user.name, user.email, user.role.name, user.password_hash,
                 int(user.active), user.department, user.max_workload_points,
                 user.years_experience, int(user.available)))
            c.execute("DELETE FROM technician_skills WHERE user_id = ?", (user.user_id,))
            c.executemany("INSERT INTO technician_skills (user_id, category, level) VALUES (?,?,?)",
                          [(user.user_id, cat, lvl) for cat, lvl in user.skills.items()])

    @_db_errors
    def load_users(self) -> list[UserRecord]:
        with self._lock:
            skills: dict[str, dict[str, int]] = {}
            for r in self._conn.execute("SELECT user_id, category, level FROM technician_skills"):
                skills.setdefault(r["user_id"], {})[r["category"]] = r["level"]
            rows = self._conn.execute("SELECT * FROM users ORDER BY rowid").fetchall()
        return [UserRecord(r["user_id"], r["name"], r["email"], Role[r["role"]], r["password_hash"],
                           bool(r["active"]), r["department"], skills.get(r["user_id"], {}),
                           r["max_workload_points"], r["years_experience"], bool(r["available"]))
                for r in rows]

    @_db_errors
    def delete_user(self, user_id: str) -> bool:
        """Hard delete. Refused (PersistenceError) while incidents still reference the user;
        the domain's normal way to remove someone is deactivate_user()."""
        with self._tx() as c:
            return c.execute("DELETE FROM users WHERE user_id = ?", (user_id,)).rowcount > 0

    # ═════════════════════════════ services ══════════════════════════════════════════════
    @_db_errors
    def save_service(self, service: ServiceRecord) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO services (service_id, name, business_criticality, default_category, owner)
                   VALUES (?,?,?,?,?)
                   ON CONFLICT(service_id) DO UPDATE SET
                       name=excluded.name, business_criticality=excluded.business_criticality,
                       default_category=excluded.default_category, owner=excluded.owner""",
                (service.service_id, service.name, service.business_criticality,
                 service.default_category, service.owner))
            c.execute("DELETE FROM service_keywords WHERE service_id = ?", (service.service_id,))
            c.executemany("INSERT INTO service_keywords (service_id, keyword) VALUES (?,?)",
                          [(service.service_id, k) for k in dict.fromkeys(service.keywords)])
            c.execute("DELETE FROM service_dependencies WHERE service_id = ?", (service.service_id,))
            c.executemany(
                "INSERT INTO service_dependencies (service_id, depends_on_id, position) VALUES (?,?,?)",
                [(service.service_id, up, pos) for pos, up in enumerate(dict.fromkeys(service.depends_on))])

    @_db_errors
    def load_services(self) -> list[ServiceRecord]:
        with self._lock:
            keywords: dict[str, list[str]] = {}
            for r in self._conn.execute("SELECT service_id, keyword FROM service_keywords ORDER BY keyword"):
                keywords.setdefault(r["service_id"], []).append(r["keyword"])
            deps: dict[str, list[str]] = {}
            for r in self._conn.execute(
                    "SELECT service_id, depends_on_id FROM service_dependencies ORDER BY service_id, position"):
                deps.setdefault(r["service_id"], []).append(r["depends_on_id"])
            rows = self._conn.execute("SELECT * FROM services ORDER BY rowid").fetchall()
        return [ServiceRecord(r["service_id"], r["name"], r["business_criticality"], r["default_category"],
                              tuple(keywords.get(r["service_id"], ())), tuple(deps.get(r["service_id"], ())),
                              r["owner"])
                for r in rows]

    @_db_errors
    def delete_service(self, service_id: str) -> bool:
        """Hard delete. Refused while incidents or other services still depend on it."""
        with self._tx() as c:
            return c.execute("DELETE FROM services WHERE service_id = ?", (service_id,)).rowcount > 0

    # ═════════════════════════════ incidents ═════════════════════════════════════════════
    @_db_errors
    def save_incident(self, incident: IncidentRecord) -> None:
        values = []
        for name in _SCALAR_FIELDS:
            v = getattr(incident, name)
            if name in _DATETIME_FIELDS:
                v = _dt_out(v)
            elif name in _BOOL_FIELDS:
                v = int(bool(v))
            elif name == "priority_explanation":
                v = json.dumps(v or {}, ensure_ascii=False, default=str)
            values.append(v)
        iid = incident.incident_id
        with self._lock:
            if self._saved_incidents.get(iid) == incident:
                return                                  # nothing changed since the last save
            self._write_incident(iid, incident, values)
            self._saved_incidents[iid] = incident       # remembered only after a successful commit

    def _write_incident(self, iid: str, incident: IncidentRecord, values: list) -> None:
        with self._tx() as c:
            c.execute(_INCIDENT_UPSERT, values)
            c.execute("DELETE FROM incident_notes WHERE incident_id = ?", (iid,))
            c.executemany(
                "INSERT INTO incident_notes (incident_id, seq, author_id, text, at, internal) VALUES (?,?,?,?,?,?)",
                [(iid, n, note.author_id, note.text, _dt_out(note.at), int(note.internal))
                 for n, note in enumerate(incident.notes)])
            c.execute("DELETE FROM incident_resolutions WHERE incident_id = ?", (iid,))
            c.executemany(
                """INSERT INTO incident_resolutions
                   (incident_id, seq, description, root_cause, preventive_action, technician_id, at)
                   VALUES (?,?,?,?,?,?,?)""",
                [(iid, n, r.description, r.root_cause, r.preventive_action, r.technician_id, _dt_out(r.at))
                 for n, r in enumerate(incident.resolutions)])
            c.execute("DELETE FROM incident_links WHERE incident_id = ?", (iid,))
            c.executemany("INSERT INTO incident_links (incident_id, related_id) VALUES (?,?)",
                          [(iid, rid) for rid in dict.fromkeys(incident.related_incidents)])

    @_db_errors
    def load_incidents(self) -> list[IncidentRecord]:
        with self._lock:
            notes: dict[str, list[Note]] = {}
            for r in self._conn.execute("SELECT * FROM incident_notes ORDER BY incident_id, seq"):
                notes.setdefault(r["incident_id"], []).append(
                    Note(r["author_id"], r["text"], _dt_in(r["at"]), bool(r["internal"])))
            resolutions: dict[str, list[Resolution]] = {}
            for r in self._conn.execute("SELECT * FROM incident_resolutions ORDER BY incident_id, seq"):
                resolutions.setdefault(r["incident_id"], []).append(
                    Resolution(r["description"], r["root_cause"], r["preventive_action"],
                               r["technician_id"], _dt_in(r["at"])))
            links: dict[str, list[str]] = {}
            for r in self._conn.execute("SELECT incident_id, related_id FROM incident_links ORDER BY related_id"):
                links.setdefault(r["incident_id"], []).append(r["related_id"])
            rows = self._conn.execute("SELECT * FROM incidents ORDER BY created_at, incident_id").fetchall()

        out = []
        for r in rows:
            data = {}
            for name in _SCALAR_FIELDS:
                v = r[name]
                if name in _DATETIME_FIELDS:
                    v = _dt_in(v)
                elif name in _BOOL_FIELDS:
                    v = bool(v)
                elif name == "priority_explanation":
                    v = json.loads(v or "{}")
                data[name] = v
            iid = r["incident_id"]
            out.append(IncidentRecord(**data, related_incidents=tuple(links.get(iid, ())),
                                      notes=tuple(notes.get(iid, ())),
                                      resolutions=tuple(resolutions.get(iid, ()))))
        return out

    @_db_errors
    def delete_incident(self, incident_id: str) -> bool:
        """Hard delete (notes, resolutions and links go with it). Audit events are kept."""
        with self._lock:
            with self._tx() as c:
                deleted = c.execute("DELETE FROM incidents WHERE incident_id = ?", (incident_id,)).rowcount > 0
            self._saved_incidents.pop(incident_id, None)
            return deleted

    # ═════════════════════════════ optional: audit trail ═════════════════════════════════
    @_db_errors
    def save_audit_event(self, event: DomainEvent) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO audit_events (event_type, incident_id, actor_id, at, description,
                                             previous_state, new_state, recipients, urgent)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (event.type.name, event.incident_id, event.actor_id, _dt_out(event.at), event.description,
                 event.previous_state, event.new_state, Codec.encode_list(event.recipients), int(event.urgent)))

    @_db_errors
    def load_audit_events(self) -> list[DomainEvent]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM audit_events ORDER BY event_id").fetchall()
        return [DomainEvent(EventType[r["event_type"]], r["incident_id"], r["actor_id"], _dt_in(r["at"]),
                            r["description"], r["previous_state"], r["new_state"],
                            tuple(Codec.decode_list(r["recipients"])), bool(r["urgent"]))
                for r in rows]

    # ═════════════════════════════ optional: categories ══════════════════════════════════
    @_db_errors
    def save_category(self, category: Category) -> None:
        with self._tx() as c:
            c.execute("""INSERT INTO categories (name, description) VALUES (?,?)
                         ON CONFLICT(name) DO UPDATE SET description=excluded.description""",
                      (category.name, category.description))
            c.execute("DELETE FROM category_keywords WHERE category = ?", (category.name,))
            c.executemany("INSERT INTO category_keywords (category, keyword) VALUES (?,?)",
                          [(category.name, k) for k in sorted(category.keywords)])

    @_db_errors
    def load_categories(self) -> list[Category]:
        with self._lock:
            kws: dict[str, list[str]] = {}
            for r in self._conn.execute("SELECT category, keyword FROM category_keywords"):
                kws.setdefault(r["category"], []).append(r["keyword"])
            rows = self._conn.execute("SELECT * FROM categories ORDER BY rowid").fetchall()
        return [Category(r["name"], r["description"], kws.get(r["name"], ())) for r in rows]

    @_db_errors
    def delete_category(self, name: str) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM categories WHERE name = ?", (name.upper(),)).rowcount > 0

    # ═════════════════════════════ optional: SLA policies ════════════════════════════════
    @staticmethod
    def _policy_id(policy: SLAPolicy) -> str:
        return f"{policy.service_id or '*'}/{policy.priority.name}"

    @_db_errors
    def save_sla_policy(self, policy: SLAPolicy) -> None:
        with self._tx() as c:
            c.execute(
                """INSERT INTO sla_policies (policy_id, service_id, priority, response_seconds,
                                             resolution_seconds, warning_threshold)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(policy_id) DO UPDATE SET
                       response_seconds=excluded.response_seconds,
                       resolution_seconds=excluded.resolution_seconds,
                       warning_threshold=excluded.warning_threshold""",
                (self._policy_id(policy), policy.service_id, policy.priority.name,
                 policy.response_target.total_seconds(), policy.resolution_target.total_seconds(),
                 policy.warning_threshold))

    @_db_errors
    def load_sla_policies(self) -> list[SLAPolicy]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM sla_policies ORDER BY rowid").fetchall()
        return [SLAPolicy(Priority[r["priority"]], timedelta(seconds=r["response_seconds"]),
                          timedelta(seconds=r["resolution_seconds"]), r["warning_threshold"], r["service_id"])
                for r in rows]

    @_db_errors
    def delete_sla_policy(self, priority: Priority, service_id: str | None = None) -> bool:
        with self._tx() as c:
            return c.execute("DELETE FROM sla_policies WHERE policy_id = ?",
                             (f"{service_id or '*'}/{priority.name}",)).rowcount > 0
