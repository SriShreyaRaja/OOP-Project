# I-ITSM Domain Layer (Python) — Member 2 Handoff

The domain layer is the "brain" of I-ITSM: every business rule, design pattern and intelligent feature lives here. It is **pure Python 3.10+ using only the standard library**, so it runs and is tested on its own. The web API (Member 3) and the screens (Member 1) plug into it.

## Running it

From the `backend/` folder: `python -m itsm.demo` (the 3 video workflows) and `python -m pytest` (61 tests). On Windows you can double-click `run_demo.bat` / `run_tests.bat`.

## How this answers the central question

**Maintainable.** Each rule lives in exactly one class. Attributes are private (leading underscore) and exposed read-only through properties; an incident changes only through business methods that check permissions and legality first. One facade (`ServiceDesk`) is the only door into the domain.

**Extensible.** A new lifecycle state is one class. A new priority or assignment algorithm is one class, selectable at runtime by an admin. A new notification channel is one class. A new incident category or service is added as data, with no code change. A smarter duplicate detector plugs in behind an abstract base class.

**Intelligent.** Explainable priority ("why is this P1?"), smart technician recommendation with reasons, auto-categorization, duplicate detection, root-cause correlation over a service dependency graph, what-if blast-radius simulation, predictive SLA risk, automatic escalation, sticky reassignment on reopen, and suggested resolutions from history.

## Module map (`itsm/domain/`)

| Module | Contents | Patterns / OOP concepts |
|---|---|---|
| `users.py` | `User` (abstract) → `Employee`, `Technician` → `TeamLead`, `Administrator` → `ITManager`, `SystemAccount`; `PasswordHash` | Abstraction (ABC), inheritance (true is-a only), polymorphic `permissions`, encapsulation, salted PBKDF2 hashing |
| `incident.py` | `Incident`; `Note`, `Resolution`, `Feedback` dataclasses | Encapsulation, composition (owns notes/resolutions/SLA clock), association (reporter, technician, service) |
| `states.py` | 10 lifecycle states incl. `AWAITING_INFO` and `REOPENED` | **State** pattern (states are shared instances) |
| `priority.py` | `WeightedScorePriorityStrategy`, `MatrixPriorityStrategy` | **Strategy** pattern, abstract base class |
| `assignment.py` | skill, load, round_robin, priority, smart | **Strategy** + **Template Method** (base class fixes filter → score → sort → pick) |
| `events.py` | `EventBus`, `DomainEvent`, `AuditLog` | **Observer** pattern |
| `notifications.py` | In-app, Email, SMS channels; `NotificationService` | **Observer**, **Adapter** (`SmsChannelAdapter` wraps a vendor SDK) |
| `factory.py` | `IncidentFactory`, `UserFactory`, `NotificationChannelFactory` | **Factory** pattern |
| `repository.py` | `IncidentRepository`, `UserRepository` + in-memory versions | **Repository** pattern |
| `persistence.py` | `StorageAdapter` (the one class Member 3 implements), `UserRecord`, `IncidentRecord`, `ServiceRecord`, `InMemoryStorage` | Write-through persistence |
| `escalation.py` | `EscalationHandler` chain, `EscalationPolicy` | **Chain of Responsibility** |
| `service_desk.py` | `ServiceDesk`, `IncidentRequest`, `SearchCriteria`, report dataclasses | **Facade**, **Builder** (request + search) |
| `sla.py` | `SLAPolicy`, `SLAPolicyBook` (per-service overrides), `SLAClock` (pause/resume) | Encapsulation, composition |
| `catalog.py` | `ITService`, `ServiceCatalog` (dependency graph, cycle check, BFS/DFS), `CategoryRegistry` | Collections & graph algorithms |
| `intelligence.py` | Duplicate detector, correlator, SLA risk, resolution suggester, what-if simulator | Abstract interfaces Member 4 can upgrade |
| `exceptions.py` | 15 specific exceptions under `ITSMError`, each with a `code` and `http_status` | Exception hierarchy |
| `common.py`, `text.py` | Enums, `Clock` / `FakeClock`, UTC + IST times, JSON helpers, text tools | Dependency inversion (testable time) |

**Design patterns: 11** (the brief requires 2): State, Strategy ×2, Template Method, Observer, Adapter, Factory, Repository, Chain of Responsibility, Facade, Builder.

## What makes this design stand out

1. **Every decision explains itself.** Priority returns a full breakdown ("why is this P1?"); assignment returns reasons for each candidate. Both go into the audit trail.
2. **Workload is measured in points, not ticket count:** a P1 costs 8 points, a P4 costs 1.
3. **The SLA clock pauses** while waiting for the reporter (AWAITING_INFO), and deadlines shift fairly.
4. **The UI never guesses which buttons to show:** `incident.actions_for(user)` combines what the current State allows with what this person may do.
5. **Root-cause correlation** over the service dependency graph: "Payment and Email are failing; both depend on SSO, which is also reported down."
6. **What-if simulation:** "if the Core Database fails, these 4 services go down, 2 of them business-critical."
7. **Dependency cycles are impossible:** the catalog rejects any edge that would create one.
8. **Predictive SLA risk** warns before the standard 75% warning.
9. **Sticky reassignment:** a reopened incident goes back to the technician who already knows it.
10. **Resolutions record root cause and preventive action**, feeding "suggested resolution".
11. **Testable time:** `FakeClock` lets the demo and tests show breaches and escalations instantly. All times display in UTC and IST.
12. **Survives restarts:** everything is saved through one interface and fully rebuilt at startup (tested).
13. **Production-minded:** thread-safe facade (one lock), login lockout after 5 failures, auto-close of resolved incidents after 72 h, and a failing notification channel never breaks the workflow.

## Handoff contracts

### Member 3 — API and database (FastAPI + SQLite suggested)
- Create one `ServiceDesk` at startup and call **only** its public methods from your routes. Return `incident.to_dict(desk.now(), user)` and `to_plain(...)` (from `itsm.domain.common`) for everything else; both are JSON-ready.
- One exception handler covers every domain error:
  ```python
  from fastapi.responses import JSONResponse
  from itsm.domain.exceptions import ITSMError

  @app.exception_handler(ITSMError)
  def handle_domain_error(request, e: ITSMError):
      return JSONResponse(status_code=e.http_status, content=e.to_dict())
  ```
- **Database:** write one class implementing `persistence.StorageAdapter` with Python's built-in `sqlite3` and call `desk.attach_storage(adapter)` at startup. Everything is then saved on every change and reloaded after a restart. Full guide: `docs/DATABASE_DESIGN.md`.
- `ServiceDesk` is thread-safe, so FastAPI's worker threads can share it.
- Call `desk.run_monitor()` every minute (a background task or APScheduler).
- Use `desk.login(email, password)` behind your login endpoint (it locks an account after 5 failed attempts).

### Member 1 — Frontend
- Build your screens now against the JSON samples in `docs/API_CONTRACT.md`, then switch to the live API when Member 3 is ready.
- Show buttons from `yourActions` (the buttons this user may press). `priorityExplanation` and `assignmentReason` make good tooltips.
- Employee portal: `my_incidents`. Technician workspace: `my_queue` (most urgent first). Notification bell: `inbox`.

### Member 4 — Intelligence and testing
- `intelligence.py` defines abstract base classes. To upgrade duplicate detection, write a subclass of `DuplicateDetector` and plug it in with `desk.set_duplicate_detector(MyDetector())`.
- `tests/` has 61 passing pytest tests, documented in `docs/TEST_CASES.md`. Extend it with API tests (FastAPI's `TestClient`).

## Priority algorithm (for the report)

```
base  = Impact (1–4) × Urgency (1–4) × Business Criticality (1–5)     max 80
boost = 1 + 0.1 × log10(affected users)                               1 user ×1.0, 1,000 users ×1.3
score = base × boost
P1 ≥ 48   P2 ≥ 24   P3 ≥ 10   else P4
```
The log boost means the number of affected users matters, but cannot by itself turn a trivial problem into a critical one. The alternative `matrix` strategy is the ITIL impact/urgency matrix, with a one-level bump for business-critical services.

## Diagrams for the report

All in `docs/diagrams/` as PNG plus `.puml` source (editable at plantuml.com).

| File | Shows |
|---|---|
| `1-use-case.png` | Actors and what each can do |
| `2-state-diagram.png` | Incident lifecycle (State pattern) |
| `3-class-diagram-core.png` | Users, Incident, SLA, services and their relationships |
| `4-class-diagram-patterns.png` | All 11 design patterns and how ServiceDesk uses them |
| `5-sequence-report-incident.png` | Workflow 1 step by step |
| `6-architecture.png` | Layered architecture and who owns each layer |
| `7-er-diagram.png` | Suggested database schema |
