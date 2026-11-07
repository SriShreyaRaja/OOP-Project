# I-ITSM — Documented Test Cases

All 61 test cases are automated **pytest** tests in `backend/tests/` and **all pass**. Run them with `python -m pytest` in `backend/`, or double-click `run_tests.bat` (Windows) / `run_tests.sh` (Mac/Linux).

The PDF asks for at least 15 test cases covering normal operations, boundary conditions, invalid inputs, exceptions, authorization and business rules. Coverage by category:

| Category | Count |
|---|---|
| Normal | 16 |
| Boundary | 9 |
| Invalid input | 7 |
| Exceptions | 7 |
| Authorization | 7 |
| Business rules | 15 |
| **Total** | **61** |

Tests use a `FakeClock`, so time-based rules (SLA warnings, breaches, escalation, auto-close, login lockout) are tested in milliseconds without waiting.

| ID | Category | Scenario | Input / steps | Expected result | Test (file › function) | Status |
|---|---|---|---|---|---|---|
| TC01 | Normal | Employee reports a payment outage | Impact ORGANIZATION, Urgency CRITICAL, 500 users, no service given | Service = Payment, category = APPLICATION, P1, ASSIGNED, 30-min resolution SLA | `test_lifecycle.py` › `test_report_runs_the_full_pipeline` | ✅ Pass |
| TC02 | Normal | Service identified from the description | "Payment application unavailable…" | Service SVC-PAY chosen automatically | `test_lifecycle.py` › `test_service_is_guessed_from_text_when_not_given` | ✅ Pass |
| TC03 | Normal | Full lifecycle is recorded | Report → acknowledge → start → resolve → verify → close | Audit trail has all 8 states in order | `test_lifecycle.py` › `test_complete_lifecycle_is_audited_in_order` | ✅ Pass |
| TC04 | Normal | Technician notified on assignment | New P1 incident | In-app inbox and email outbox both contain the notice | `test_lifecycle.py` › `test_notifications_go_out_on_two_channels` | ✅ Pass |
| TC05 | Normal | Reopen after a failed fix | Resolve, then reporter reopens | Status ASSIGNED, same technician (sticky), previous resolution kept | `test_lifecycle.py` › `test_reopen_goes_back_to_the_same_technician` | ✅ Pass |
| TC06 | Normal | Save → restart → reload | Incidents in AWAITING_INFO and RESOLVED, new desk on same storage | Status, paused SLA, workload, history, audit, ID numbering and login all restored | `test_persistence_operations.py` › `test_everything_survives_a_restart` | ✅ Pass |
| TC07 | Normal | User converted to a DB row and back | Technician with skills | Same type, same skills, password still works | `test_persistence_operations.py` › `test_user_record_round_trip` | ✅ Pass |
| TC08 | Normal | Technician workspace queue | P4 then P1 assigned to the same technician | Queue shows P1 first | `test_persistence_operations.py` › `test_technician_queue_is_sorted_by_urgency` | ✅ Pass |
| TC09 | Normal | Admin edits skills; technician goes away | New skills; self-unavailable | Skills replaced; availability changed; others blocked | `test_persistence_operations.py` › `test_manage_technicians` | ✅ Pass |
| TC10 | Normal | Admin monitoring views | P1 left for 40 minutes | Appears in SLA violations; audit log visible to admin only | `test_persistence_operations.py` › `test_admin_views_audit_log_and_violations` | ✅ Pass |
| TC11 | Normal | API output format | to_dict() of a new incident, seen by its technician | Valid JSON incl. allowedActions [ASSIGN, ACKNOWLEDGE] and yourActions [ACKNOWLEDGE] | `test_persistence_operations.py` › `test_incident_serializes_to_json` | ✅ Pass |
| TC12 | Normal | Each assignment strategy | Same P1 incident, 5 technicians | Skill → T201, Priority → L001, round-robin rotates, smart gives 4 reasons | `test_strategies_intelligence.py` › `test_strategies_behave_differently` | ✅ Pass |
| TC13 | Normal | Admin switches strategy | set_assignment_strategy("load") | Next incident assigned by the load strategy | `test_strategies_intelligence.py` › `test_assignment_strategy_swap_at_runtime` | ✅ Pass |
| TC14 | Normal | Admin adds a category | Category IOT {sensor, thermostat} | "Thermostat sensor offline" is classified IOT | `test_strategies_intelligence.py` › `test_new_category_without_code_change` | ✅ Pass |
| TC15 | Normal | Search & filter | priority, category, service, status, SLA status, technician, text, open-only | Correct matches; employee can't see others' incidents | `test_strategies_intelligence.py` › `test_search_supports_many_criteria_and_respects_visibility` | ✅ Pass |
| TC16 | Normal | Dashboards | Open P1 on Payment, then closed with feedback 4 | Payment health DOWN; overview counts, feedback 4.0, 100% SLA compliance | `test_strategies_intelligence.py` › `test_reports_and_service_health` | ✅ Pass |
| TC17 | Boundary | Lowest possible score | LOW × LOW × criticality 1 = 1 | P4 | `test_rules.py` › `test_weighted_priority_thresholds[score1-P4]` | ✅ Pass |
| TC18 | Boundary | Mid score | MEDIUM × MEDIUM × 3 = 12 | P3 | `test_rules.py` › `test_weighted_priority_thresholds[score12-P3]` | ✅ Pass |
| TC19 | Boundary | Exactly on the P2 threshold | HIGH × MEDIUM × 4 = 24 | P2 | `test_rules.py` › `test_weighted_priority_thresholds[score24-P2]` | ✅ Pass |
| TC20 | Boundary | Exactly on the P1 threshold | ORGANIZATION × CRITICAL × 3 = 48 | P1 | `test_rules.py` › `test_weighted_priority_thresholds[score48-P1]` | ✅ Pass |
| TC21 | Boundary | Just below P2 | HIGH × HIGH × 2 = 18 | P3 | `test_rules.py` › `test_weighted_priority_thresholds[score18-P3]` | ✅ Pass |
| TC22 | Boundary | User-count boost crosses a threshold | Score 18 with 1 user vs 10,000 users | P3 → P2 | `test_rules.py` › `test_many_affected_users_raise_priority` | ✅ Pass |
| TC23 | Boundary | Auto-close timing | Resolved, then 71 h and 73 h pass | Not closed at 71 h; CLOSED at 73 h | `test_persistence_operations.py` › `test_resolved_incidents_auto_close` | ✅ Pass |
| TC24 | Boundary | Brute-force protection | 5 wrong passwords, then the right one; wait 16 min | Locked after 5; unlocked after the window | `test_persistence_operations.py` › `test_login_locks_after_five_failures` | ✅ Pass |
| TC25 | Boundary | Capacity limit in points | Max 10: P1 (8), then P2 (5), then P4 (1) | P2 rejected; P4 fits (9/10) | `test_security.py` › `test_workload_points_are_enforced` | ✅ Pass |
| TC26 | Invalid input | Title too short | Title "Hi" | ValidationError | `test_security.py` › `test_invalid_incident_input_is_rejected[short-title]` | ✅ Pass |
| TC27 | Invalid input | Description too short | Description "short" | ValidationError | `test_security.py` › `test_invalid_incident_input_is_rejected[short-description]` | ✅ Pass |
| TC28 | Invalid input | Unknown impact value | Impact "HUGE" | ValidationError listing valid values | `test_security.py` › `test_invalid_incident_input_is_rejected[bad-impact]` | ✅ Pass |
| TC29 | Invalid input | Zero affected users | affected_users = 0 | ValidationError | `test_security.py` › `test_invalid_incident_input_is_rejected[zero-users]` | ✅ Pass |
| TC30 | Invalid input | Non-existent service / category | Service "NOPE", category "ALIENS" | ServiceNotFoundError / CategoryNotFoundError; no incident ID consumed | `test_security.py` › `test_unknown_service_and_category` | ✅ Pass |
| TC31 | Invalid input | Weak credentials | "short", "onlyletters", "not-an-email" | ValidationError each time | `test_security.py` › `test_weak_passwords_and_bad_emails_rejected` | ✅ Pass |
| TC32 | Invalid input | Re-using an ID or email | Existing E101 / ravi@corp.in | ValidationError | `test_security.py` › `test_duplicate_registration_rejected` | ✅ Pass |
| TC33 | Exceptions | Illegal transition | NEW → close | InvalidStateTransitionError | `test_lifecycle.py` › `test_cannot_close_new_incident` | ✅ Pass |
| TC34 | Exceptions | Illegal transition, no partial data | Resolve while ASSIGNED | InvalidStateTransitionError; no resolution stored | `test_lifecycle.py` › `test_cannot_resolve_before_work_starts` | ✅ Pass |
| TC35 | Exceptions | No SLA policy configured | Empty policy book, P1 | SLAConfigurationError | `test_rules.py` › `test_missing_sla_configuration` | ✅ Pass |
| TC36 | Exceptions | Technician unavailable | All technicians unavailable | Incident kept CLASSIFIED; TechnicianUnavailableError; manual assignment works later | `test_strategies_intelligence.py` › `test_no_capacity_leaves_incident_for_manual_assignment` | ✅ Pass |
| TC37 | Exceptions | Circular service dependency | DB → Reporting, DB → DB | DependencyCycleError | `test_strategies_intelligence.py` › `test_dependency_cycles_are_rejected` | ✅ Pass |
| TC38 | Exceptions | Duplicate incident | 3 payment reports; the 3rd with block_duplicates | First two linked both ways; third rejected with the original's ID | `test_strategies_intelligence.py` › `test_duplicates_are_linked_and_can_be_blocked` | ✅ Pass |
| TC39 | Exceptions | Network failure in a notification channel | SMS channel raises on send | Incident still ASSIGNED; failure logged for the admin | `test_persistence_operations.py` › `test_broken_notification_channel_does_not_break_workflow` | ✅ Pass |
| TC40 | Authorization | Invalid login | Wrong password; unknown email | AuthenticationError, same message for both | `test_security.py` › `test_login_works_and_rejects_wrong_password` | ✅ Pass |
| TC41 | Authorization | Deactivated account | Admin deactivates E102 | Login fails; reporting blocked | `test_security.py` › `test_deactivated_user_cannot_login_or_act` | ✅ Pass |
| TC42 | Authorization | Unauthorized operation | Employee calls resolve | UnauthorizedOperationError | `test_security.py` › `test_employee_cannot_resolve` | ✅ Pass |
| TC43 | Authorization | Wrong technician | Non-assignee acknowledges | UnauthorizedOperationError | `test_security.py` › `test_other_technician_cannot_acknowledge` | ✅ Pass |
| TC44 | Authorization | Role boundaries | Employee changes strategy / views another's incident / opens reports | UnauthorizedOperationError each time | `test_security.py` › `test_employee_cannot_configure_or_see_others_incidents` | ✅ Pass |
| TC45 | Authorization | Note visibility | Internal technician note | Hidden from the reporter, visible to the technician | `test_security.py` › `test_internal_notes_hidden_from_employees` | ✅ Pass |
| TC46 | Authorization | Password protection | Create a user | Password verifies; plain text never stored or exposed | `test_security.py` › `test_password_is_hashed_not_stored` | ✅ Pass |
| TC47 | Business rules | Stage-allowed actions | ASSIGNED incident; CLOSED state | [ASSIGN, ACKNOWLEDGE]; none for CLOSED | `test_lifecycle.py` › `test_allowed_actions_reflect_the_state` | ✅ Pass |
| TC48 | Business rules | Role-aware buttons | Same incident viewed by assignee, reporter, team lead, stranger | Assignee [ACKNOWLEDGE]; reporter none until resolved, then [VERIFY, REOPEN, CLOSE]; lead [ASSIGN, ACKNOWLEDGE]; stranger none | `test_lifecycle.py` › `test_each_viewer_sees_only_their_own_buttons` | ✅ Pass |
| TC49 | Business rules | SLA pause | Request info, wait 120 min, answer | Status PAUSED; deadline moved by exactly 120 min | `test_lifecycle.py` › `test_sla_pauses_while_awaiting_info` | ✅ Pass |
| TC50 | Business rules | Feedback timing | Feedback before and after closure | Rejected before; rating 4 stored after | `test_lifecycle.py` › `test_feedback_only_after_resolution` | ✅ Pass |
| TC51 | Business rules | ITIL matrix strategy | MEDIUM/MEDIUM on a criticality-5 service | P2 (bumped from P3) | `test_rules.py` › `test_matrix_bumps_critical_services` | ✅ Pass |
| TC52 | Business rules | Switch priority strategy | set_priority_strategy("matrix") | Explanation shows the matrix strategy | `test_rules.py` › `test_priority_strategy_swap_at_runtime` | ✅ Pass |
| TC53 | Business rules | Re-prioritisation | Printer P4 reassessed to ORGANIZATION/CRITICAL/2000 | P3, 8-hour SLA, technician points 1 → 3 | `test_rules.py` › `test_reassessment_updates_priority_sla_and_workload_points` | ✅ Pass |
| TC54 | Business rules | Per-service SLA | Payment P1 policy = 15 min | Incident gets the 15-min target | `test_rules.py` › `test_service_specific_sla_overrides_default` | ✅ Pass |
| TC55 | Business rules | SLA monitoring | Advance 24 min, then 10 more | Warning at 80%, breach after 30 min, never repeated | `test_rules.py` › `test_sla_warning_then_breach_reported_once` | ✅ Pass |
| TC56 | Business rules | Automatic escalation | Unacknowledged P1 for 6 min, then 36 min | TEAM_LEAD, then IT_MANAGER; manager notified | `test_rules.py` › `test_auto_escalation_climbs_the_chain` | ✅ Pass |
| TC57 | Business rules | No escalation once acknowledged | Acknowledged P1, wait 40 min | No escalation | `test_rules.py` › `test_acknowledged_incidents_are_not_escalated` | ✅ Pass |
| TC58 | Business rules | Root-cause correlation | Payment + SSO incidents | Suggested root = Authentication SSO | `test_strategies_intelligence.py` › `test_correlation_points_to_shared_root_cause` | ✅ Pass |
| TC59 | Business rules | What-if simulation | Core Database fails | 4 services impacted, 2 business-critical; Reporting impacts none | `test_strategies_intelligence.py` › `test_what_if_blast_radius` | ✅ Pass |
| TC60 | Business rules | Predictive SLA risk | Unacknowledged P1 after 3 min | MEDIUM risk: "not acknowledged, 60% of response time used" | `test_strategies_intelligence.py` › `test_sla_risk_flags_unacknowledged_incidents_early` | ✅ Pass |
| TC61 | Business rules | Suggested resolution | Similar incident after one was fixed | Suggests the earlier fix and root cause | `test_strategies_intelligence.py` › `test_resolution_suggestions_come_from_history` | ✅ Pass |

## Bug resolution log

Issues found and fixed while building the domain layer:

| # | Problem found | Fix |
|---|---|---|
| 1 | Rejected duplicate reports still consumed an incident ID, leaving gaps (INC1001, INC1003…) | `IncidentFactory.discard()` returns the ID; tested in TC30 and TC38 |
| 2 | An illegal transition could leave partial data behind (e.g. a stored resolution on a non-resolved incident) | Every action validates the transition *before* changing any data; tested in TC34 |
| 3 | Root-cause ranking picked Core Database over SSO even when SSO itself was reported down | Ranking now prefers services with direct reports, then the most fundamental; tested in TC58 |
| 4 | SLA risk said "LOW" for an unacknowledged P1 close to its 5-minute response deadline | Risk now considers the response deadline too; tested in TC60 |
| 5 | A failing notification channel (e.g. SMS outage) would abort the whole report | Each delivery is isolated and failures are logged; tested in TC39 |
| 6 | After a restart, technician workloads read 0 and new incidents restarted at INC1001 | Workloads and history rebuilt from incidents; numbering continues; tested in TC06 |
| 7 | An employee was shown technician buttons such as RESOLVE | `actions_for(viewer)` filters the stage's actions by role and ownership; tested in TC48 |
| 8 | Report JSON used snake_case while incidents used camelCase | `to_plain()` converts dataclass fields to camelCase; tested in TC11 |
