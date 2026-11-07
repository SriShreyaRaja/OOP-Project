# I-ITSM — API Contract (for Members 1 and 3)

This is the agreement between the frontend (Member 1), the REST API (Member 3) and the domain (Member 2). If all three follow it, the pieces fit together the first time.

**Rules for everyone**
- Field names are exactly as shown below (camelCase). Member 1 can build screens against these JSON samples *today* using fake data.
- Every endpoint (except login) needs the logged-in user. Member 3 looks the user up from the login token and passes it as the first argument. **Permission checks already happen inside the domain**, so routes don't need their own role checks.
- Incidents are returned with `incident.to_dict(desk.now(), user)`. That includes `yourActions`: exactly the buttons *this* person may press. Everything else (reports, notes, events) goes through `to_plain(...)` from `itsm.domain.common`.
- Every error comes back in one shape, with the HTTP status from `e.http_status`:
  ```json
  { "error": "INVALID_STATE_TRANSITION", "message": "Cannot close INC1005 while it is ASSIGNED. Allowed now: ['ASSIGN', 'ACKNOWLEDGE']." }
  ```

## Endpoints

| Method & path | Who | Calls (`desk.…`) | Returns |
|---|---|---|---|
| `POST /api/auth/login` | anyone | `login(email, password)` | `{ "token": "...", "user": user.to_dict() }` |
| `POST /api/auth/password` | any user | `change_password(user, old, new)` | 204 |
| `GET /api/services` | any user | `catalog.all()` → `s.to_dict()` | service[] (report-form dropdown) |
| `GET /api/categories` | any user | `categories.names()` | string[] |
| `GET /api/notifications` | any user | `inbox(user)` | notification[] |
| **Employee** | | | |
| `POST /api/incidents` | employee | `report_incident(user, IncidentRequest.builder(title, description).service(..).impact(..).urgency(..).affected_users(..).build())` | incident (201) |
| `GET /api/incidents/mine` | employee | `my_incidents(user)` | incident[] |
| `GET /api/incidents/{id}` | reporter, assignee, staff | `get_incident(user, id)` | incident |
| `GET /api/incidents/{id}/notes` | same | `get_incident(user, id).visible_notes(user)` | note[] (internal notes hidden from employees) |
| `POST /api/incidents/{id}/info` | reporter | `provide_info(user, id, answer)` | incident |
| `POST /api/incidents/{id}/verify` | reporter | `verify(user, id)` | incident |
| `POST /api/incidents/{id}/reopen` | reporter | `reopen(user, id, reason)` | incident |
| `POST /api/incidents/{id}/close` | reporter, admin | `close(user, id)` | incident |
| `POST /api/incidents/{id}/feedback` | reporter | `give_feedback(user, id, rating, comment)` | incident |
| **Technician** | | | |
| `GET /api/technician/queue` | technician | `my_queue(user)` | incident[] (most urgent first) |
| `GET /api/technician/me` | technician | `user.to_dict()` | skills, workloadPoints, maxWorkloadPoints… |
| `POST /api/technician/availability` | technician | `set_availability(user, user.user_id, available)` | 204 |
| `POST /api/incidents/{id}/acknowledge` | assignee | `acknowledge(user, id)` | incident |
| `POST /api/incidents/{id}/start` | assignee | `start_work(user, id)` | incident |
| `POST /api/incidents/{id}/notes` | assignee / reporter | `add_note(user, id, text, internal)` | incident |
| `POST /api/incidents/{id}/request-info` | assignee | `request_info(user, id, question)` | incident |
| `POST /api/incidents/{id}/resolve` | assignee | `resolve(user, id, fix, root_cause, preventive_action)` | incident |
| `GET /api/incidents/{id}/suggestions` | staff | `suggest_resolutions(user, id)` | suggestion[] |
| **Team lead / Admin** | | | |
| `GET /api/incidents?priority=P1&status=…&category=…&service=…&technician=…&slaStatus=…&from=…&to=…&q=…&open=true` | staff | `search(user, SearchCriteria.where().priority(..)…)` | incident[] |
| `GET /api/incidents/{id}/recommendations` | staff | `recommend_technicians(user, id, 3)` | candidate[] (`technicianId`, `name`, `score`, `reasons`) |
| `POST /api/incidents/{id}/assign` | lead, admin | `assign_manually(user, id, technician_id)` | incident |
| `POST /api/incidents/{id}/reassess` | lead, admin | `reassess(user, id, impact, urgency, affected_users)` | incident |
| `GET /api/incidents/{id}/audit` | staff, reporter | `audit_trail(user, id)` → `e.to_dict()` | event[] |
| `POST /api/admin/users` | admin | `register_user(admin, UserFactory.create(role, …))` | user |
| `POST /api/admin/users/{id}/deactivate` | admin | `deactivate_user(admin, id)` | 204 |
| `PUT /api/admin/technicians/{id}/skills` | admin | `update_technician_skills(admin, id, skills)` | 204 |
| `POST /api/admin/services` | admin | `add_service(admin, ITService(...))` | 201 |
| `POST /api/admin/services/{id}/dependencies` | admin | `add_dependency(admin, id, depends_on_id)` | 204 |
| `POST /api/admin/categories` | admin | `add_category(admin, name, keywords, description)` | 201 |
| `POST /api/admin/sla-policies` | admin | `configure_sla(admin, SLAPolicy(...))` | 201 |
| `PUT /api/admin/strategies/assignment` | admin | `set_assignment_strategy(admin, "skill" \| "load" \| "round_robin" \| "priority" \| "smart")` | 204 |
| `PUT /api/admin/strategies/priority` | admin | `set_priority_strategy(admin, "weighted" \| "matrix")` | 204 |
| **Dashboards** | | | |
| `GET /api/reports/overview` | staff | `overview(user)` | overview |
| `GET /api/reports/workload` | staff | `technician_workload(user)` | row[] |
| `GET /api/reports/services` | staff | `service_analysis(user)` | row[] incl. health |
| `GET /api/reports/sla-violations` | staff | `sla_violations(user)` | incident[] |
| `GET /api/reports/sla-risks` | staff | `sla_risks(user)` | risk[] |
| `GET /api/reports/correlations` | staff | `correlations(user)` | correlation[] |
| `GET /api/reports/what-if/{serviceId}` | staff | `simulate_failure(user, service_id)` | blast radius |
| `GET /api/audit` | admin | `all_audit_logs(user)` | event[] (newest first) |

Background job (no endpoint): run `desk.run_monitor()` every 60 seconds.

## Request bodies (what the browser sends)

| Request | JSON body |
|---|---|
| `POST /api/auth/login` | `{ "email": "ravi@corp.in", "password": "Passw0rd!" }` |
| `POST /api/incidents` | `{ "title": "...", "description": "...", "serviceId": "SVC-PAY" or null, "impact": "LOW\|MEDIUM\|HIGH\|ORGANIZATION", "urgency": "LOW\|MEDIUM\|HIGH\|CRITICAL", "affectedUsers": 500, "category": null }` |
| `POST /api/incidents/{id}/notes` | `{ "text": "...", "internal": false }` |
| `POST /api/incidents/{id}/request-info` | `{ "question": "..." }` |
| `POST /api/incidents/{id}/info` | `{ "answer": "..." }` |
| `POST /api/incidents/{id}/resolve` | `{ "fix": "... (10+ chars)", "rootCause": "...", "preventiveAction": "..." }` |
| `POST /api/incidents/{id}/reopen` | `{ "reason": "..." }` |
| `POST /api/incidents/{id}/feedback` | `{ "rating": 5, "comment": "..." }` |
| `POST /api/incidents/{id}/assign` | `{ "technicianId": "T202" }` |
| `POST /api/incidents/{id}/reassess` | `{ "impact": "HIGH", "urgency": "CRITICAL", "affectedUsers": 2000 }` (any may be null) |
| `POST /api/technician/availability` | `{ "available": false }` |
| `PUT /api/admin/strategies/assignment` | `{ "name": "load" }` |

## Sample: incident (`incident.to_dict(desk.now(), user)`, seen by the assigned technician)

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
  "createdAtIso": "2026-11-07T04:30:00+00:00",
  "resolvedAt": null,
  "closedAt": null,
  "escalationLevel": 0,
  "escalatedTo": null,
  "relatedIncidents": [],
  "reopenCount": 0,
  "feedbackRating": null,
  "yourActions": [
    "ACKNOWLEDGE"
  ]
}
```

## Sample: overview dashboard (`to_plain(desk.overview(user))`)

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
| `DATABASE_FAILURE` | 503 | Database unreachable (raised by Member 3's adapter) |
