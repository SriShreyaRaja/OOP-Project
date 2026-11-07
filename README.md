<<<<<<< HEAD
# I-ITSM — Intelligent IT Service Management & Incident Resolution System

CS F213 / MAC F212 OOP Project, Semester I 2026–27 · Java 17

> **Central question:** How can object-oriented thinking be used to design a maintainable, extensible and intelligent software system for managing IT incidents in a real organization?

## Quick start

You need **Java 17 or newer** (`java -version` to check).

| I want to… | Windows | Mac / Linux | IntelliJ |
|---|---|---|---|
| See the 3 demo workflows | double-click `backend/run-demo.bat` | `backend/run-demo.sh` | run `com.itsm.demo.Demo` |
| Run all 60 tests | double-click `backend/run-tests.bat` | `backend/run-tests.sh` | right-click `src/test/java` → Run |

**IntelliJ (recommended):** *File → Open →* choose `backend/pom.xml` → *Open as Project*.

Sample logins (all passwords `Passw0rd!`): `ravi@corp.in` (employee), `tara@corp.in` (technician), `leo@corp.in` (team lead), `asha@corp.in` (admin), `meera@corp.in` (IT manager).

## Repository layout

```
i_itsm_java/
├── backend/
│   ├── pom.xml                       Maven build file
│   ├── run-demo.bat / .sh            run the demo without an IDE
│   ├── run-tests.bat / .sh           run the tests without an IDE
│   └── src/
│       ├── main/java/com/itsm/
│       │   ├── domain/               ← Member 2: business logic (pure Java)
│       │   │   ├── desk/             ServiceDesk — the ONE class the API calls
│       │   │   ├── incident/ state/  incident + lifecycle (State pattern)
│       │   │   ├── user/             roles & permissions
│       │   │   ├── priority/ assignment/   strategies
│       │   │   ├── sla/ escalation/  SLA timers, escalation chain
│       │   │   ├── event/ notification/    audit trail, notifications
│       │   │   ├── intelligence/     ← Member 4 upgrades these
│       │   │   ├── persistence/      ← Member 3 implements StorageAdapter
│       │   │   └── catalog/ factory/ repository/ exception/ common/
│       │   └── demo/Demo.java        the 3 video workflows
│       └── test/java/                60 JUnit tests
└── docs/
    ├── MEMBER2_DOMAIN_HANDOFF.md     how the domain works + what each member does next
    ├── API_CONTRACT.md               endpoints + JSON shapes (Members 1 & 3)
    ├── DATABASE_DESIGN.md            ER diagram + how to plug in a DB (Member 3)
    ├── TEST_CASES.md                 60 documented test cases + bug log (Member 4 / report)
    └── diagrams/                     use case, class, state, sequence, architecture, ER (PNG + source)
```

## Team

| Member | Area | Starts from |
|---|---|---|
| 1 | Frontend (Employee portal, Technician workspace, Admin dashboard) | `docs/API_CONTRACT.md` — build against the JSON samples |
| 2 | Domain model, OOP design, patterns | done — `docs/MEMBER2_DOMAIN_HANDOFF.md` |
| 3 | REST API, database, security | `docs/API_CONTRACT.md` + `docs/DATABASE_DESIGN.md` |
| 4 | Intelligent features, testing, demo video | `domain/intelligence/` + `docs/TEST_CASES.md` |

## Git workflow

Work on your own branch (`feature/frontend`, `feature/api-db`, `feature/intelligence`), open a Pull Request into `main`, and have one teammate review it. Run the tests before every PR. The domain is in its own folder, so you won't edit the same files.
=======
# OOP-Project
>>>>>>> e5ffc3449d9ab5b909ca0c2929315834e274dc10
