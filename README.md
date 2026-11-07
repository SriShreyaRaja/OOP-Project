# I-ITSM — Intelligent IT Service Management & Incident Resolution System

CS F213 / MAC F212 OOP Project, Semester I 2026–27 · **Python 3.10+**

> **Central question:** How can object-oriented thinking be used to design a maintainable, extensible and intelligent software system for managing IT incidents in a real organization?

## Quick start

You need **Python 3.10 or newer** (`python --version` to check).

| I want to… | Windows | Mac / Linux | Any editor |
|---|---|---|---|
| See the 3 demo workflows | double-click `backend/run_demo.bat` | `backend/run_demo.sh` | in `backend/`: `python -m itsm.demo` |
| Run all 61 tests | double-click `backend/run_tests.bat` | `backend/run_tests.sh` | in `backend/`: `python -m pytest` |

The domain uses only Python's standard library. The tests need `pytest` (`pip install -r backend/requirements.txt`; the test scripts do this for you).

**Editor:** VS Code (with the Python extension) or PyCharm Community → open the `backend` folder.

Sample logins (all passwords `Passw0rd!`): `ravi@corp.in` (employee), `tara@corp.in` (technician), `leo@corp.in` (team lead), `asha@corp.in` (admin), `meera@corp.in` (IT manager).

## Repository layout

```
i_itsm/
├── backend/
│   ├── requirements.txt              pytest (the domain itself needs nothing extra)
│   ├── run_demo.bat / .sh            run the demo
│   ├── run_tests.bat / .sh           run the tests
│   ├── itsm/
│   │   ├── domain/                   ← Member 2: business logic (pure Python)
│   │   │   ├── service_desk.py       ServiceDesk: the ONE class the API calls
│   │   │   ├── incident.py           the Incident + Note, Resolution, Feedback
│   │   │   ├── states.py             lifecycle (State pattern)
│   │   │   ├── users.py              roles, permissions, password hashing
│   │   │   ├── priority.py           priority strategies
│   │   │   ├── assignment.py         technician assignment strategies
│   │   │   ├── sla.py                SLA policies and the SLA clock
│   │   │   ├── escalation.py         escalation chain
│   │   │   ├── events.py             event bus + audit trail (Observer)
│   │   │   ├── notifications.py      in-app, email, SMS adapter
│   │   │   ├── intelligence.py       duplicates, correlation, SLA risk, suggestions, what-if
│   │   │   ├── catalog.py            IT services (dependency graph) and categories
│   │   │   ├── factory.py            factories
│   │   │   ├── repository.py         repositories
│   │   │   ├── persistence.py        ← Member 3 implements StorageAdapter
│   │   │   ├── exceptions.py         16 custom exceptions
│   │   │   ├── common.py text.py     enums, clock, JSON helpers, text tools
│   │   │   └── sample_data.py        a ready-made demo company
│   │   └── demo.py                   the 3 video workflows
│   └── tests/                        61 pytest tests
└── docs/
    ├── MEMBER2_DOMAIN_HANDOFF.md     how the domain works + what each member does next
    ├── API_CONTRACT.md               endpoints + JSON shapes (Members 1 & 3)
    ├── DATABASE_DESIGN.md            ER diagram + how to plug in SQLite (Member 3)
    ├── TEST_CASES.md                 61 documented test cases + bug log
    └── diagrams/                     use case, class, state, sequence, architecture, ER (PNG + source)
```

## Team

| Member | Area | Starts from |
|---|---|---|
| 1 | Frontend (Employee portal, Technician workspace, Admin dashboard) | `docs/API_CONTRACT.md`: build against the JSON samples |
| 2 | Domain model, OOP design, patterns | done: `docs/MEMBER2_DOMAIN_HANDOFF.md` |
| 3 | REST API (FastAPI), database (SQLite), security | `docs/API_CONTRACT.md` + `docs/DATABASE_DESIGN.md` |
| 4 | Intelligent features, testing, demo video | `itsm/domain/intelligence.py` + `docs/TEST_CASES.md` |

## Git workflow

Work on your own branch, open a Pull Request into `main`, and have one teammate review it. Run the tests before every PR. Each member works in their own folder, so you won't edit the same files.
