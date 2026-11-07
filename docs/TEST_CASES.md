# I-ITSM — Documented Test Cases

All 60 test cases are automated JUnit 5 tests in `backend/src/test/java/com/itsm/domain/` and **all pass**. Run them with `mvn test`, `run-tests.bat` (Windows) or `run-tests.sh` (Mac/Linux).

The PDF asks for at least 15 test cases covering normal operations, boundary conditions, invalid inputs, exceptions, authorization and business rules. Coverage by category:

| Category | Count |
|---|---|
| Normal | 16 |
| Boundary | 9 |
| Invalid input | 7 |
| Exceptions | 7 |
| Authorization | 7 |
| Business rules | 14 |
| **Total** | **60** |

Tests use a `FakeClock`, so time-based rules (SLA warnings, breaches, escalation, auto-close, login lockout) are tested in milliseconds without waiting.

| ID | Category | Scenario | Input / steps | Expected result | Test (class › method) | Status |
|---|---|---|---|---|---|---|
| TC01 | Normal | Employee reports a payment outage | Impact ORGANIZATION, Urgency CRITICAL, 500 users, no service given | Service = Payment, category = APPLICATION, P1, ASSIGNED, 30-min resolution SLA | `LifecycleTest` › `reportRunsTheFullPipeline` | ✅ Pass |
| TC02 | Normal | Service identified from the description | "Payment application unavailable…" | Service SVC-PAY chosen automatically | `LifecycleTest` › `serviceIsGuessedFromTextWhenNotGiven` | ✅ Pass |
| TC03 | Normal | Full lifecycle is recorded | Report → acknowledge → start → resolve → verify → close | Audit trail has all 8 states in order | `LifecycleTest` › `completeLifecycleIsAuditedInOrder` | ✅ Pass |
| TC04 | Normal | Technician notified on assignment | New P1 incident | In-app inbox and email outbox both contain the notice | `LifecycleTest` › `notificationsGoOutOnTwoChannels` | ✅ Pass |
| TC05 | Normal | Reopen after a failed fix | Resolve, then reporter reopens | Status ASSIGNED, same technician (sticky), previous resolution kept | `LifecycleTest` › `reopenGoesBackToTheSameTechnician` | ✅ Pass |
| TC06 | Normal | Save → restart → reload | Incidents in AWAITING_INFO and RESOLVED, new desk on same storage | Status, paused SLA, workload, history, audit, ID numbering and login all restored | `PersistenceAndOperationsTest` › `everythingSurvivesARestart` | ✅ Pass |
| TC07 | Normal | User converted to DB row and back | Technician with skills | Same type, same skills, password still works | `PersistenceAndOperationsTest` › `userRecordRoundTrip` | ✅ Pass |
| TC08 | Normal | Technician workspace queue | P4 then P1 assigned to the same technician | Queue shows P1 first | `PersistenceAndOperationsTest` › `technicianQueueIsSortedByUrgency` | ✅ Pass |
| TC09 | Normal | Admin edits skills; technician goes away | New skills map; self-unavailable | Skills replaced; availability changed; others blocked | `PersistenceAndOperationsTest` › `manageTechnicians` | ✅ Pass |
| TC10 | Normal | Admin monitoring views | P1 left for 40 minutes | Appears in SLA violations; audit log visible to admin only | `PersistenceAndOperationsTest` › `adminViewsAuditLogAndViolations` | ✅ Pass |
| TC11 | Normal | API output format | toMap() of a new incident | Valid JSON incl. allowedActions [ASSIGN, ACKNOWLEDGE] | `PersistenceAndOperationsTest` › `incidentSerializesToJson` | ✅ Pass |
| TC12 | Normal | Each assignment strategy | Same P1 incident, 5 technicians | Skill → T201, Priority → L001, round-robin rotates, smart gives 4 reasons | `StrategyAndIntelligenceTest` › `strategiesBehaveDifferently` | ✅ Pass |
| TC13 | Normal | Admin switches strategy | setAssignmentStrategy("load") | Next incident assigned by load strategy | `StrategyAndIntelligenceTest` › `strategySwapAtRuntime` | ✅ Pass |
| TC14 | Normal | Admin adds a category | Category IOT {sensor, thermostat} | "Thermostat sensor offline" is classified IOT | `StrategyAndIntelligenceTest` › `newCategoryWithoutCodeChange` | ✅ Pass |
| TC15 | Normal | Search & filter | priority, category, service, status, SLA status, technician, text, open-only | Correct matches; employee can't see others' incidents | `StrategyAndIntelligenceTest` › `searchSupportsManyCriteriaAndRespectsVisibility` | ✅ Pass |
| TC16 | Normal | Dashboards | Open P1 on Payment, then closed with feedback 4 | Payment health DOWN; overview counts, feedback 4.0, 100% SLA compliance | `StrategyAndIntelligenceTest` › `reportsAndServiceHealth` | ✅ Pass |
| TC17 | Boundary | Lowest possible score | LOW × LOW × criticality 1 = 1 | P4 | `RulesTest` › `weightedPriorityThresholds [1]` | ✅ Pass |
| TC18 | Boundary | Mid score | MEDIUM × MEDIUM × 3 = 12 | P3 | `RulesTest` › `weightedPriorityThresholds [2]` | ✅ Pass |
| TC19 | Boundary | Exactly on P2 threshold | HIGH × MEDIUM × 4 = 24 | P2 | `RulesTest` › `weightedPriorityThresholds [3]` | ✅ Pass |
| TC20 | Boundary | Exactly on P1 threshold | ORGANIZATION × CRITICAL × 3 = 48 | P1 | `RulesTest` › `weightedPriorityThresholds [4]` | ✅ Pass |
| TC21 | Boundary | Just below P2 | HIGH × HIGH × 2 = 18 | P3 | `RulesTest` › `weightedPriorityThresholds [5]` | ✅ Pass |
| TC22 | Boundary | User-count boost crosses a threshold | Score 18 with 1 user vs 10,000 users | P3 → P2 | `RulesTest` › `manyAffectedUsersRaisePriority` | ✅ Pass |
| TC23 | Boundary | Auto-close timing | Resolved, then 71 h and 73 h pass | Not closed at 71 h; CLOSED at 73 h | `PersistenceAndOperationsTest` › `resolvedIncidentsAutoClose` | ✅ Pass |
| TC24 | Boundary | Brute-force protection | 5 wrong passwords, then right one; wait 16 min | Locked after 5; unlocked after the window | `PersistenceAndOperationsTest` › `loginLocksAfterFiveFailures` | ✅ Pass |
| TC25 | Boundary | Capacity limit in points | Max 10: P1 (8) then P2 (5), then P4 (1) | P2 rejected; P4 fits (9/10) | `SecurityAndValidationTest` › `workloadPointsAreEnforced` | ✅ Pass |
| TC26 | Invalid input | Title too short | Title "Hi" | ValidationException | `SecurityAndValidationTest` › `invalidIncidentInputIsRejected [1]` | ✅ Pass |
| TC27 | Invalid input | Description too short | Description "short" | ValidationException | `SecurityAndValidationTest` › `invalidIncidentInputIsRejected [2]` | ✅ Pass |
| TC28 | Invalid input | Unknown impact value | Impact "HUGE" | ValidationException listing valid values | `SecurityAndValidationTest` › `invalidIncidentInputIsRejected [3]` | ✅ Pass |
| TC29 | Invalid input | Zero affected users | affectedUsers = 0 | ValidationException | `SecurityAndValidationTest` › `invalidIncidentInputIsRejected [4]` | ✅ Pass |
| TC30 | Invalid input | Non-existent service / category | Service "NOPE", category "ALIENS" | ServiceNotFound / CategoryNotFound; no incident ID consumed | `SecurityAndValidationTest` › `unknownServiceAndCategory` | ✅ Pass |
| TC31 | Invalid input | Weak credentials | "short", "onlyletters", "not-an-email" | ValidationException each time | `SecurityAndValidationTest` › `weakPasswordsAndBadEmailsRejected` | ✅ Pass |
| TC32 | Invalid input | Re-using an ID or email | Existing E101 / ravi@corp.in | ValidationException | `SecurityAndValidationTest` › `duplicateRegistrationRejected` | ✅ Pass |
| TC33 | Exceptions | Illegal transition | NEW → CLOSE | InvalidStateTransitionException | `LifecycleTest` › `cannotCloseNewIncident` | ✅ Pass |
| TC34 | Exceptions | Illegal transition, no partial data | Resolve while ASSIGNED | InvalidStateTransitionException; no resolution stored | `LifecycleTest` › `cannotResolveBeforeWorkStarts` | ✅ Pass |
| TC35 | Exceptions | No SLA policy configured | Empty policy book, P1 | SLAConfigurationException | `RulesTest` › `missingSlaConfiguration` | ✅ Pass |
| TC36 | Exceptions | Technician unavailable | All technicians unavailable | Incident kept CLASSIFIED; TechnicianUnavailableException; manual assign works later | `StrategyAndIntelligenceTest` › `noCapacityLeavesIncidentForManualAssignment` | ✅ Pass |
| TC37 | Exceptions | Circular service dependency | DB → Reporting, DB → DB | DependencyCycleException | `StrategyAndIntelligenceTest` › `dependencyCyclesAreRejected` | ✅ Pass |
| TC38 | Exceptions | Duplicate incident | 3 payment reports; 3rd with blockDuplicates | First two linked both ways; third rejected with original's ID | `StrategyAndIntelligenceTest` › `duplicatesAreLinkedAndCanBeBlocked` | ✅ Pass |
| TC39 | Exceptions | Network failure in a notification channel | SMS channel throws on send | Incident still ASSIGNED; failure logged for admin | `PersistenceAndOperationsTest` › `brokenNotificationChannelDoesNotBreakWorkflow` | ✅ Pass |
| TC40 | Authorization | Invalid login | Wrong password; unknown email | AuthenticationException, same message for both | `SecurityAndValidationTest` › `loginWorksAndRejectsWrongPassword` | ✅ Pass |
| TC41 | Authorization | Deactivated account | Admin deactivates E102 | Login fails; reporting blocked | `SecurityAndValidationTest` › `deactivatedUserCannotLoginOrAct` | ✅ Pass |
| TC42 | Authorization | Unauthorized operation | Employee calls resolve | UnauthorizedOperationException | `SecurityAndValidationTest` › `employeeCannotResolve` | ✅ Pass |
| TC43 | Authorization | Wrong technician | Non-assignee acknowledges | UnauthorizedOperationException | `SecurityAndValidationTest` › `otherTechnicianCannotAcknowledge` | ✅ Pass |
| TC44 | Authorization | Role boundaries | Employee changes strategy / views another's incident / reports | UnauthorizedOperationException each time | `SecurityAndValidationTest` › `employeeCannotConfigureOrSeeOthersIncidents` | ✅ Pass |
| TC45 | Authorization | Note visibility | Internal technician note | Hidden from reporter, visible to technician | `SecurityAndValidationTest` › `internalNotesHiddenFromEmployees` | ✅ Pass |
| TC46 | Authorization | Password protection | Create user | Password verifies; plain text never stored or exposed | `SecurityAndValidationTest` › `passwordIsHashedNotStored` | ✅ Pass |
| TC47 | Business rules | UI buttons come from the State | ASSIGNED incident; CLOSED state | [ASSIGN, ACKNOWLEDGE]; none for CLOSED | `LifecycleTest` › `allowedActionsReflectTheState` | ✅ Pass |
| TC48 | Business rules | SLA pause | Request info, wait 120 min, answer | Status PAUSED; deadline moved by exactly 120 min | `LifecycleTest` › `slaPausesWhileAwaitingInfo` | ✅ Pass |
| TC49 | Business rules | Feedback timing | Feedback before and after closure | Rejected before; rating 4 stored after | `LifecycleTest` › `feedbackOnlyAfterResolution` | ✅ Pass |
| TC50 | Business rules | ITIL matrix strategy | MEDIUM/MEDIUM on criticality-5 service | P2 (bumped from P3) | `RulesTest` › `matrixBumpsCriticalServices` | ✅ Pass |
| TC51 | Business rules | Switch priority strategy | setPriorityStrategy("matrix") | Explanation shows matrix strategy | `RulesTest` › `prioritySwapAtRuntime` | ✅ Pass |
| TC52 | Business rules | Re-prioritisation | Printer P4 reassessed to ORGANIZATION/CRITICAL/2000 | P3, 8-hour SLA, technician points 1 → 3 | `RulesTest` › `reassessmentUpdatesPrioritySlaAndWorkloadPoints` | ✅ Pass |
| TC53 | Business rules | Per-service SLA | Payment P1 policy = 15 min | Incident gets 15-min target | `RulesTest` › `serviceSpecificSlaOverridesDefault` | ✅ Pass |
| TC54 | Business rules | SLA monitoring | Advance 24 min, then 10 more | Warning at 80%, breach after 30 min, never repeated | `RulesTest` › `slaWarningThenBreachReportedOnce` | ✅ Pass |
| TC55 | Business rules | Automatic escalation | Unacknowledged P1 for 6 min, then 36 min | TEAM_LEAD, then IT_MANAGER; manager notified | `RulesTest` › `autoEscalationClimbsTheChain` | ✅ Pass |
| TC56 | Business rules | No escalation once acknowledged | Acknowledged P1, wait 40 min | No escalation | `RulesTest` › `acknowledgedIncidentsAreNotEscalated` | ✅ Pass |
| TC57 | Business rules | Root-cause correlation | Payment + SSO incidents | Suggested root = Authentication SSO | `StrategyAndIntelligenceTest` › `correlationPointsToSharedRootCause` | ✅ Pass |
| TC58 | Business rules | What-if simulation | Core Database fails | 4 services impacted, 2 business-critical; Reporting impacts none | `StrategyAndIntelligenceTest` › `whatIfBlastRadius` | ✅ Pass |
| TC59 | Business rules | Predictive SLA risk | Unacknowledged P1 after 3 min | MEDIUM risk: "not acknowledged, 60% of response time used" | `StrategyAndIntelligenceTest` › `slaRiskFlagsUnacknowledgedIncidentsEarly` | ✅ Pass |
| TC60 | Business rules | Suggested resolution | Similar incident after one was fixed | Suggests earlier fix and root cause | `StrategyAndIntelligenceTest` › `resolutionSuggestionsComeFromHistory` | ✅ Pass |

## Bug resolution log

Issues found and fixed while building the domain layer:

| # | Problem found | Fix |
|---|---|---|
| 1 | Rejected duplicate reports still consumed an incident ID, leaving gaps (INC1001, INC1003…) | `IncidentFactory.discard()` returns the ID; tested in TC30 and TC38 |
| 2 | An illegal transition could leave partial data behind (e.g. a stored resolution on a non-resolved incident) | Every action validates the transition *before* changing any data; tested in TC34 |
| 3 | Root-cause ranking picked Core Database over SSO even when SSO itself was reported down | Ranking now prefers services with direct reports, then the most fundamental; tested in TC57 |
| 4 | SLA risk said "LOW" for an unacknowledged P1 close to its 5-minute response deadline | Risk now considers the response deadline too; tested in TC59 |
| 5 | A failing notification channel (e.g. SMS outage) would abort the whole report | Each delivery is isolated and failures are logged; tested in TC39 |
| 6 | After a restart, technician workloads would read 0 and new incidents restarted at INC1001 | Workloads and history rebuilt from incidents; numbering continues; tested in TC06 |
| 7 | Priority explanation lost its display order when copied | Kept in insertion order (`LinkedHashMap`) |
