package com.itsm.demo;

import com.itsm.domain.common.FakeClock;
import com.itsm.domain.common.TimeFormat;
import com.itsm.domain.desk.*;
import com.itsm.domain.exception.ITSMException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.notification.EmailChannel;
import com.itsm.domain.notification.Notification;
import com.itsm.domain.user.Technician;
import com.itsm.domain.user.User;

/**
 * Runs the three workflows required for the video demo, with a FakeClock so SLA
 * warnings, breaches and escalations happen in seconds instead of hours.
 *
 *   mvn -q compile exec:java            (or run this class from your IDE)
 */
public class Demo {
    static void banner(String t) {
        System.out.println("\n" + "═".repeat(78) + "\n  " + t + "\n" + "═".repeat(78));
    }

    interface Step { void run(); }

    static void expectFailure(String label, Step s) {
        try {
            s.run();
            System.out.println(label + " → allowed?!");
        } catch (ITSMException e) {
            System.out.printf("%-34s → %s: %s%n", label, e.getCode(), e.getMessage());
        }
    }

    public static void main(String[] args) {
        FakeClock clock = new FakeClock();
        SampleData.Org org = SampleData.build(clock);
        ServiceDesk desk = org.desk();
        System.out.println("Clock starts at " + TimeFormat.both(clock.now()));

        // ─────────────────────────────────────────────────────────────────────
        banner("WORKFLOW 1: Employee reports → system prioritises → technician assigned → notified");
        User ravi = desk.login("ravi@corp.in", SampleData.PASSWORD);
        Incident inc = desk.reportIncident(ravi, IncidentRequest.builder(
                "Payment application unavailable",
                "Users are unable to complete transactions on the payment application.")
            .impact("ORGANIZATION").urgency("CRITICAL").affectedUsers(600).build());
        System.out.printf("%s: service=%s category=%s priority=%s status=%s%n", inc.getIncidentId(),
            inc.getService().getName(), inc.getCategory(), inc.getPriority(), inc.getStatus());
        System.out.println("Why this priority?");
        inc.getPriorityExplanation().forEach((k, v) -> System.out.printf("   %-20s %s%n", k, v));
        System.out.println("Assigned: " + inc.getAssignee().orElseThrow().getUserId() + " — " + inc.getAssignmentReason());
        System.out.println("SLA resolution due: " + TimeFormat.both(inc.getSla().resolutionDue()));
        System.out.println("Buttons the UI should show now: " + inc.allowedActions());
        Technician tara = inc.getAssignee().orElseThrow();
        System.out.println("Tara's inbox: " + desk.inbox(tara).stream().map(Notification::subject).toList());
        System.out.println("Emails sent: " + desk.channel("email", EmailChannel.class).outbox().size());

        // ─────────────────────────────────────────────────────────────────────
        banner("WORKFLOW 2: Technician investigates → SLA monitored → resolved → user notified");
        String id = inc.getIncidentId();
        clock.advanceMinutes(3); desk.acknowledge(tara, id);
        clock.advanceMinutes(2); desk.startWork(tara, id);
        desk.addNote(tara, id, "Gateway returns 503; checking DB connection pool.", true);
        clock.advanceMinutes(2); desk.requestInfo(tara, id, "Which branch are you in?");
        System.out.println("Status: " + inc.getStatus() + " | SLA: " + inc.getSla().status(desk.now()));
        clock.advanceMinutes(30);
        System.out.printf("30 min later, still waiting on Ravi. SLA: %s | used: %.0f%% (clock paused)%n",
            inc.getSla().status(desk.now()), inc.getSla().usedFraction(desk.now()) * 100);
        desk.provideInfo(ravi, id, "Hyderabad branch, all counters.");
        clock.advanceMinutes(17);
        System.out.println("Monitor run: " + desk.runMonitor());
        clock.advanceMinutes(1);
        desk.resolve(tara, id, "Restarted DB connection pool and raised max connections to 200.",
                     "Connection pool exhaustion after traffic spike", "Alert at 80% pool usage");
        desk.verify(ravi, id);
        desk.close(ravi, id);
        desk.giveFeedback(ravi, id, 5, "Quick fix, thanks!");
        System.out.println("Final: " + inc.getStatus() + " | SLA: " + inc.getSla().status(desk.now())
            + " | Tara's workload now " + tara.workloadPoints() + " pts");
        System.out.println("Ravi's inbox: " + desk.inbox(ravi).stream().map(Notification::subject).toList());
        System.out.println("\nAudit trail:\n" + desk.audit().timeline(id));

        // ─────────────────────────────────────────────────────────────────────
        banner("WORKFLOW 3: Multiple incidents → duplicates detected → correlated → escalated");
        Incident a = desk.reportIncident(org.get("emp2"), IncidentRequest.builder("Payment transaction failing",
                "Customer payment transaction failing at checkout with error.")
            .impact("HIGH").urgency("HIGH").affectedUsers(120).build());
        Incident b = desk.reportIncident(org.get("emp3"), IncidentRequest.builder("Unable to make payment",
                "We are unable to make payment from the finance portal.")
            .impact("HIGH").urgency("HIGH").affectedUsers(40).build());
        Incident c = desk.reportIncident(org.get("emp3"), IncidentRequest.builder("SSO login down for everyone",
                "Cannot login through SSO, authentication error on all apps.")
            .impact("ORGANIZATION").urgency("CRITICAL").affectedUsers(900).build());
        for (Incident x : new Incident[]{a, b, c}) {
            System.out.printf("%s %s %-15s assigned=%s related=%s%n", x.getIncidentId(), x.getPriority().name(),
                x.getCategory(), x.getAssignee().map(User::getUserId).orElse("-"), x.getRelatedIncidents());
        }
        expectFailure("4th report of the same outage", () -> desk.reportIncident(ravi,
            IncidentRequest.builder("Payment app not working", "Payment transaction failing for us too.")
                .impact("HIGH").urgency("HIGH").blockDuplicates().build()));

        System.out.println("\nLikely root cause (correlation over the service dependency graph):");
        desk.correlations(org.get("manager")).stream().limit(3).forEach(k -> System.out.println("   " + k.explanation()));

        System.out.println("\nWhat if Core Database failed?");
        System.out.println("   " + desk.simulateFailure(org.get("manager"), "SVC-DB"));

        clock.advanceMinutes(3);
        System.out.println("\nPredictive SLA risk (3 min in, before any warning fires):");
        desk.slaRisks(org.get("manager")).forEach(r ->
            System.out.printf("   %s %-8s %.2f  %s%n", r.incidentId(), r.level(), r.risk(), String.join(", ", r.factors())));

        clock.advanceMinutes(17);
        System.out.println("\nMonitor after 20 min with nobody acknowledging: " + desk.runMonitor());
        System.out.println("Admin's inbox: " + desk.inbox(org.get("admin")).stream().map(Notification::subject).toList());

        // ─────────────────────────────────────────────────────────────────────
        banner("REPORTS & SEARCH");
        User meera = org.get("manager");
        System.out.println(desk.overview(meera));
        desk.technicianWorkload(meera).forEach(r -> System.out.println("   " + r));
        desk.serviceAnalysis(meera).forEach(r -> System.out.println("   " + r));
        System.out.println("Open, escalated P1s: " + desk.search(meera,
            SearchCriteria.where().priority("P1").openOnly().escalated()).stream().map(Incident::getIncidentId).toList());
        System.out.println("Suggested fixes for " + a.getIncidentId() + ": " + desk.suggestResolutions(meera, a.getIncidentId()));

        // ─────────────────────────────────────────────────────────────────────
        banner("SWAPPING STRATEGY AT RUNTIME (no code changes)");
        desk.setAssignmentStrategy(org.get("admin"), "load");
        Incident w = desk.reportIncident(org.get("emp2"), IncidentRequest.builder("Wifi keeps dropping",
                "Office wifi network disconnects every few minutes on floor 3.").build());
        System.out.println(w.getIncidentId() + " → " + w.getAssignee().map(User::getUserId).orElse("-")
            + " | " + w.getAssignmentReason());

        // ─────────────────────────────────────────────────────────────────────
        banner("ILLEGAL ACTIONS ARE BLOCKED");
        expectFailure("Close an ASSIGNED incident", () -> desk.close(org.get("admin"), w.getIncidentId()));
        expectFailure("Employee resolves", () -> desk.resolve(org.get("emp2"), w.getIncidentId(),
            "I fixed it myself somehow", "unknown", null));
        expectFailure("Wrong technician acknowledges", () -> desk.acknowledge(org.get("tDb"), w.getIncidentId()));
        expectFailure("Bad login", () -> desk.login("ravi@corp.in", "wrong-pass1"));
        expectFailure("Cyclic dependency", () -> desk.addDependency(org.get("admin"), "SVC-DB", "SVC-PAY"));
        expectFailure("Employee views others' incident", () -> desk.getIncident(org.get("emp1"), w.getIncidentId()));
    }
}
