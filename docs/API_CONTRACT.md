# I-ITSM — API Contract (for Members 1 and 3)

This is the agreement between the frontend (Member 1), the REST API (Member 3) and the domain layer (Member 2). If all three follow it, the pieces fit together the first time.

**Rules for everyone**
- Field names are exactly as shown below (camelCase). Member 1 can build screens against these JSON samples *today* using mock data.
- Every endpoint (except login) needs the logged-in user. Member 3 gets the `User` from the JWT/session and passes it as the first argument. **Permission checks already happen inside the domain**, so controllers don't need their own role checks.
- Every error comes back in one shape, with the HTTP status from `ITSMException.httpStatus()`:
  ```json
  { "error": "INVALID_STATE_TRANSITION", "message": "Cannot close INC1005 while it is ASSIGNED. Allowed now: [ASSIGN, ACKNOWLEDGE]." }
  ```

## Endpoints

| Method & path | Who | Calls | Returns |
|---|---|---|---|
| `POST /api/auth/login` | anyone | `desk.login(email, password)` | user `toMap()` + token |
| `POST /api/auth/password` | any user | `desk.changePassword(user, old, new)` | 204 |
| **Employee** | | | |
| `POST /api/incidents` | employee | `desk.reportIncident(user, IncidentRequest.builder(title, description).service(..).impact(..).urgency(..).affectedUsers(..).build())` | incident (201) |
| `GET /api/incidents/mine` | employee | `desk.myIncidents(user)` | incident[] |
| `GET /api/incidents/{id}` | reporter, assignee, staff | `desk.getIncident(user, id)` | incident |
| `GET /api/incidents/{id}/notes` | same | `incident.visibleNotes(user)` | note[] (internal notes hidden from employees) |
| `POST /api/incidents/{id}/info` | reporter | `desk.provideInfo(user, id, answer)` | incident |
| `POST /api/incidents/{id}/verify` | reporter | `desk.verify(user, id)` | incident |
| `POST /api/incidents/{id}/reopen` | reporter | `desk.reopen(user, id, reason)` | incident |
| `POST /api/incidents/{id}/close` | reporter, admin | `desk.close(user, id)` | incident |
| `POST /api/incidents/{id}/feedback` | reporter | `desk.giveFeedback(user, id, rating, comment)` | incident |
| **Technician** | | | |
| `GET /api/technician/queue` | technician | `desk.myQueue(tech)` | incident[] (most urgent first) |
| `GET /api/technician/me` | technician | `tech.toMap()` | skills, workloadPoints, maxWorkloadPoints… |
| `POST /api/technician/availability` | technician | `desk.setAvailability(user, user.getUserId(), available)` | 204 |
| `POST /api/incidents/{id}/acknowledge` | assignee | `desk.acknowledge(user, id)` | incident |
| `POST /api/incidents/{id}/start` | assignee | `desk.startWork(user, id)` | incident |
| `POST /api/incidents/{id}/notes` | assignee / reporter | `desk.addNote(user, id, text, internal)` | incident |
| `POST /api/incidents/{id}/request-info` | assignee | `desk.requestInfo(user, id, question)` | incident |
| `POST /api/incidents/{id}/resolve` | assignee | `desk.resolve(user, id, fix, rootCause, preventiveAction)` | incident |
| `GET /api/incidents/{id}/suggestions` | staff | `desk.suggestResolutions(user, id)` | suggestion[] |
| **Team lead / Admin** | | | |
| `GET /api/incidents?priority=P1&status=…&category=…&service=…&technician=…&slaStatus=…&from=…&to=…&q=…&open=true` | staff | `desk.search(user, SearchCriteria.where().priority(..)…)` | incident[] |
| `GET /api/incidents/{id}/recommendations` | staff | `desk.recommendTechnicians(user, id, 3)` | candidate[] with reasons |
| `POST /api/incidents/{id}/assign` | lead, admin | `desk.assignManually(user, id, technicianId)` | incident |
| `POST /api/incidents/{id}/reassess` | lead, admin | `desk.reassess(user, id, impact, urgency, affectedUsers)` | incident |
| `GET /api/incidents/{id}/audit` | staff, reporter | `desk.auditTrail(user, id)` → `event.toMap()` | event[] |
| `POST /api/admin/users` | admin | `desk.registerUser(admin, UserFactory.create(role, …))` | user |
| `POST /api/admin/users/{id}/deactivate` | admin | `desk.deactivateUser(admin, id)` | 204 |
| `PUT /api/admin/technicians/{id}/skills` | admin | `desk.updateTechnicianSkills(admin, id, skillsMap)` | 204 |
| `POST /api/admin/services` | admin | `desk.addService(admin, new ITService(...))` | 201 |
| `POST /api/admin/services/{id}/dependencies` | admin | `desk.addDependency(admin, id, dependsOnId)` | 204 |
| `POST /api/admin/categories` | admin | `desk.addCategory(admin, name, keywords, description)` | 201 |
| `POST /api/admin/sla-policies` | admin | `desk.configureSla(admin, new SLAPolicy(...))` | 201 |
| `PUT /api/admin/strategies/assignment` | admin | `desk.setAssignmentStrategy(admin, "skill" \| "load" \| "round_robin" \| "priority" \| "smart")` | 204 |
| `PUT /api/admin/strategies/priority` | admin | `desk.setPriorityStrategy(admin, "weighted" \| "matrix")` | 204 |
| **Dashboards** | | | |
| `GET /api/reports/overview` | staff | `desk.overview(user)` | overview |
| `GET /api/reports/workload` | staff | `desk.technicianWorkload(user)` | row[] |
| `GET /api/reports/services` | staff | `desk.serviceAnalysis(user)` | row[] incl. health |
| `GET /api/reports/sla-violations` | staff | `desk.slaViolations(user)` | incident[] |
| `GET /api/reports/sla-risks` | staff | `desk.slaRisks(user)` | risk[] |
| `GET /api/reports/correlations` | staff | `desk.correlations(user)` | correlation[] |
| `GET /api/reports/what-if/{serviceId}` | staff | `desk.simulateFailure(user, serviceId)` | blast radius |
| `GET /api/audit` | admin | `desk.allAuditLogs(user)` | event[] (newest first) |
| `GET /api/notifications` | any user | `desk.inbox(user)` | notification[] |

Background job (no endpoint): `@Scheduled(fixedRate = 60000) void monitor() { desk.runMonitor(); }`

## Sample: incident (`incident.toMap(desk.now())`)

`allowedActions` tells the UI which buttons to show. Times are shown in UTC and IST; `createdAtIso` is for sorting.

```json
{
  "incidentId": "INC1001",
  "title": "Payment application unavailable",
  "description": "Users are unable to complete transactions on the payment application.",
  "reporterId": "E101",
  "serviceId": "SVC-PAY",
  "serviceName": "Payment Application",
  "category": "APPLICATION",
  "categoryConfidence": 1.0,
  "impact": "ORGANIZATION",
  "urgency": "CRITICAL",
  "affectedUsers": 600,
  "priority": "P1",
  "priorityExplanation": {
    "strategy": "weighted",
    "formula": "Impact × Urgency × Criticality × UserBoost",
    "impact": "ORGANIZATION (4)",
    "urgency": "CRITICAL (4)",
    "businessCriticality": "Payment Application (5)",
    "affectedUsers": 600,
    "userBoost": 1.28,
    "score": 102.2,
    "thresholds": "P1≥48, P2≥24, P3≥10, else P4",
    "result": "P1 - Critical"
  },
  "status": "ASSIGNED",
  "allowedActions": [
    "ASSIGN",
    "ACKNOWLEDGE"
  ],
  "assignedTo": "T201",
  "assignmentReason": "smart strategy: skill 5/5, workload 0/20, fixed Payment Application 0×, 4.0y exp",
  "sla": {
    "priority": "P1",
    "responseDue": "2026-11-07 04:35 UTC / 10:05 IST",
    "resolutionDue": "2026-11-07 05:00 UTC / 10:30 IST",
    "responded": false,
    "status": "ON_TRACK",
    "usedPercent": 0.0,
    "minutesRemaining": 30,
    "paused": false
  },
  "resolution": null,
  "rootCause": null,
  "createdAt": "2026-11-07 04:30 UTC / 10:00 IST",
  "createdAtIso": "2026-11-07T04:30:00Z",
  "resolvedAt": null,
  "closedAt": null,
  "escalationLevel": 0,
  "escalatedTo": null,
  "relatedIncidents": [],
  "reopenCount": 0,
  "feedbackRating": null
}
```

## Sample: overview dashboard (`desk.overview(user)`)

```json
{
  "totalIncidents": 1,
  "openIncidents": 1,
  "criticalOpen": 1,
  "resolvedIncidents": 0,
  "slaViolations": 0,
  "slaCompliancePercent": 100.0,
  "meanTimeToAcknowledgeMinutes": 0.0,
  "meanTimeToResolveMinutes": 0.0,
  "averageFeedback": null,
  "byStatus": {
    "ASSIGNED": 1
  },
  "byPriority": {
    "P1": 1
  }
}
```

## Sample: technician workload row

```json
{
  "technicianId": "T201",
  "name": "Tara AppSupport",
  "activeIncidents": 1,
  "workloadPoints": 8,
  "maxPoints": 20,
  "resolved": 0,
  "available": true
}
```

## Error codes

| Code | HTTP | When |
|---|---|---|
| `INVALID_INPUT` | 400 | Missing/short title or description, bad enum value, weak password… |
| `INVALID_LOGIN` | 401 | Wrong email/password, or account temporarily locked |
| `UNAUTHORIZED_OPERATION` | 403 | Role isn't allowed to do this |
| `INCIDENT_NOT_FOUND`, `USER_NOT_FOUND`, `SERVICE_NOT_FOUND`, `CATEGORY_NOT_FOUND` | 404 | Unknown ID |
| `INVALID_STATE_TRANSITION` | 409 | E.g. closing an incident that is still ASSIGNED |
| `DUPLICATE_INCIDENT` | 409 | Report blocked as a duplicate (message names the original) |
| `TECHNICIAN_UNAVAILABLE`, `WORKLOAD_EXCEEDED` | 409 | Nobody free / technician full |
| `DEPENDENCY_CYCLE` | 409 | Service dependency would create a loop |
| `MISSING_SLA_CONFIGURATION` | 500 | No SLA policy for that priority |
| `EXTERNAL_SERVICE_FAILURE` | 502 | Third-party (SMS/email) failure |
| `DATABASE_FAILURE` | 503 | Database unreachable (thrown by Member 3's adapter) |
