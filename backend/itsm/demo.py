"""
Runs the three workflows required for the video demo. A FakeClock fast-forwards time so
SLA warnings, breaches and escalations happen in seconds instead of hours.

    cd backend
    python -m itsm.demo        (or double-click run_demo.bat)
"""
from __future__ import annotations

import sys

from itsm.domain import sample_data
from itsm.domain.common import FakeClock, both_times
from itsm.domain.exceptions import ITSMError
from itsm.domain.service_desk import IncidentRequest, SearchCriteria

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")       # so ═ → × show correctly on Windows


def banner(title: str) -> None:
    print(f"\n{'═' * 78}\n  {title}\n{'═' * 78}")


def expect_failure(label: str, action) -> None:
    try:
        action()
        print(f"{label} → allowed?!")
    except ITSMError as e:
        print(f"{label:<34} → {e.code}: {e.message}")


def main() -> None:
    clock = FakeClock()
    org = sample_data.build(clock)
    desk = org.desk
    print("Clock starts at", both_times(clock.now()))

    # ──────────────────────────────────────────────────────────────────────────
    banner("WORKFLOW 1: Employee reports → system prioritises → technician assigned → notified")
    ravi = desk.login("ravi@corp.in", sample_data.PASSWORD)
    inc = desk.report_incident(ravi, IncidentRequest.builder(
        "Payment application unavailable",
        "Users are unable to complete transactions on the payment application.")
        .impact("ORGANIZATION").urgency("CRITICAL").affected_users(600).build())
    print(f"{inc.incident_id}: service={inc.service.name} category={inc.category} "
          f"priority={inc.priority} status={inc.status}")
    print("Why this priority?")
    for k, v in inc.priority_explanation.items():
        print(f"   {k:<20} {v}")
    tara = inc.assignee
    print(f"Assigned: {tara.user_id} — {inc.assignment_reason}")
    print("SLA resolution due:", both_times(inc.sla.resolution_due()))
    print("Buttons Tara should see:", [a.name for a in inc.actions_for(tara)])
    print("Buttons Ravi should see:", [a.name for a in inc.actions_for(ravi)], "(nothing yet)")
    print("Tara's inbox:", [n.subject for n in desk.inbox(tara)])
    print("Emails sent:", len(desk.channel("email").outbox))

    # ──────────────────────────────────────────────────────────────────────────
    banner("WORKFLOW 2: Technician investigates → SLA monitored → resolved → user notified")
    iid = inc.incident_id
    clock.advance(minutes=3); desk.acknowledge(tara, iid)
    clock.advance(minutes=2); desk.start_work(tara, iid)
    desk.add_note(tara, iid, "Gateway returns 503; checking DB connection pool.", internal=True)
    clock.advance(minutes=2); desk.request_info(tara, iid, "Which branch are you in?")
    print("Status:", inc.status, "| SLA:", inc.sla.status(desk.now()).name)
    clock.advance(minutes=30)
    print(f"30 min later, still waiting on Ravi. SLA: {inc.sla.status(desk.now()).name} | "
          f"used: {inc.sla.used_fraction(desk.now()):.0%} (clock paused)")
    desk.provide_info(ravi, iid, "Hyderabad branch, all counters.")
    clock.advance(minutes=17)
    print("Monitor run:", desk.run_monitor())
    clock.advance(minutes=1)
    desk.resolve(tara, iid, "Restarted DB connection pool and raised max connections to 200.",
                 "Connection pool exhaustion after traffic spike", "Alert at 80% pool usage")
    desk.verify(ravi, iid)
    desk.close(ravi, iid)
    desk.give_feedback(ravi, iid, 5, "Quick fix, thanks!")
    print(f"Final: {inc.status} | SLA: {inc.sla.status(desk.now()).name} | "
          f"Tara's workload now {tara.workload_points} pts")
    print("Ravi's inbox:", [n.subject for n in desk.inbox(ravi)])
    print("\nAudit trail:\n" + desk.audit.timeline(iid))

    # ──────────────────────────────────────────────────────────────────────────
    banner("WORKFLOW 3: Multiple incidents → duplicates detected → correlated → escalated")
    a = desk.report_incident(org.get("emp2"), IncidentRequest.builder(
        "Payment transaction failing", "Customer payment transaction failing at checkout with error.")
        .impact("HIGH").urgency("HIGH").affected_users(120).build())
    b = desk.report_incident(org.get("emp3"), IncidentRequest.builder(
        "Unable to make payment", "We are unable to make payment from the finance portal.")
        .impact("HIGH").urgency("HIGH").affected_users(40).build())
    c = desk.report_incident(org.get("emp3"), IncidentRequest.builder(
        "SSO login down for everyone", "Cannot login through SSO, authentication error on all apps.")
        .impact("ORGANIZATION").urgency("CRITICAL").affected_users(900).build())
    for x in (a, b, c):
        print(f"{x.incident_id} {x.priority.name} {x.category:<15} "
              f"assigned={x.assignee.user_id if x.assignee else '-'} related={sorted(x.related_incidents)}")
    expect_failure("4th report of the same outage", lambda: desk.report_incident(ravi, IncidentRequest.builder(
        "Payment app not working", "Payment transaction failing for us too.")
        .impact("HIGH").urgency("HIGH").block_duplicates().build()))

    manager = org.get("manager")
    print("\nLikely root cause (correlation over the service dependency graph):")
    for k in desk.correlations(manager)[:3]:
        print("  ", k.explanation)
    print("\nWhat if Core Database failed?")
    print("  ", desk.simulate_failure(manager, "SVC-DB"))

    clock.advance(minutes=3)
    print("\nPredictive SLA risk (3 min in, before any warning fires):")
    for r in desk.sla_risks(manager):
        print(f"   {r.incident_id} {r.level:<8} {r.risk:.2f}  {', '.join(r.factors)}")
    clock.advance(minutes=17)
    print("\nMonitor after 20 min with nobody acknowledging:", desk.run_monitor())
    print("Admin's inbox:", [n.subject for n in desk.inbox(org.get("admin"))])

    # ──────────────────────────────────────────────────────────────────────────
    banner("REPORTS & SEARCH")
    print(desk.overview(manager))
    for row in desk.technician_workload(manager):
        print("  ", row)
    for row in desk.service_analysis(manager):
        print("  ", row)
    print("Open, escalated P1s:", [i.incident_id for i in desk.search(
        manager, SearchCriteria.where().priority("P1").open_only().escalated())])
    print(f"Suggested fixes for {a.incident_id}:", desk.suggest_resolutions(manager, a.incident_id))

    # ──────────────────────────────────────────────────────────────────────────
    banner("SWAPPING STRATEGY AT RUNTIME (no code changes)")
    desk.set_assignment_strategy(org.get("admin"), "load")
    w = desk.report_incident(org.get("emp2"), IncidentRequest.builder(
        "Wifi keeps dropping", "Office wifi network disconnects every few minutes on floor 3.").build())
    print(f"{w.incident_id} → {w.assignee.user_id if w.assignee else '-'} | {w.assignment_reason}")

    # ──────────────────────────────────────────────────────────────────────────
    banner("ILLEGAL ACTIONS ARE BLOCKED")
    expect_failure("Close an ASSIGNED incident", lambda: desk.close(org.get("admin"), w.incident_id))
    expect_failure("Employee resolves", lambda: desk.resolve(org.get("emp2"), w.incident_id,
                                                             "I fixed it myself somehow", "unknown"))
    expect_failure("Wrong technician acknowledges", lambda: desk.acknowledge(org.get("t_db"), w.incident_id))
    expect_failure("Bad login", lambda: desk.login("ravi@corp.in", "wrong-pass1"))
    expect_failure("Cyclic dependency", lambda: desk.add_dependency(org.get("admin"), "SVC-DB", "SVC-PAY"))
    expect_failure("Employee views others' incident", lambda: desk.get_incident(org.get("emp1"), w.incident_id))


if __name__ == "__main__":
    main()
