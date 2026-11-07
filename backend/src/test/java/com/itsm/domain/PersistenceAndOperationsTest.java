package com.itsm.domain;

import com.itsm.domain.common.FakeClock;
import com.itsm.domain.common.Json;
import com.itsm.domain.desk.IncidentRequest;
import com.itsm.domain.desk.SampleData;
import com.itsm.domain.desk.ServiceDesk;
import com.itsm.domain.exception.AuthenticationException;
import com.itsm.domain.exception.UnauthorizedOperationException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.notification.Notification;
import com.itsm.domain.notification.NotificationChannel;
import com.itsm.domain.persistence.InMemoryStorage;
import com.itsm.domain.persistence.UserRecord;
import com.itsm.domain.user.Technician;
import com.itsm.domain.user.User;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Persistence (save → restart → reload) and day-to-day operations")
class PersistenceAndOperationsTest extends TestSupport {

    @Test void everythingSurvivesARestart() {
        // Day 1: a desk backed by storage does real work
        FakeClock c = new FakeClock();
        InMemoryStorage db = new InMemoryStorage();
        ServiceDesk day1 = new ServiceDesk(c);
        day1.attachStorage(db);
        SampleData.Org o = SampleData.seed(day1);
        Incident open = day1.reportIncident(o.get("emp1"), paymentOutage().build());
        Technician tech = open.getAssignee().orElseThrow();
        day1.acknowledge(tech, open.getIncidentId());
        day1.startWork(tech, open.getIncidentId());
        day1.requestInfo(tech, open.getIncidentId(), "Which branch?");     // SLA paused
        Incident done = day1.reportIncident(o.get("emp2"), IncidentRequest.builder("Printer jammed",
            "The 2nd floor printer is jammed").service("SVC-PRINT").impact("LOW").urgency("LOW").build());
        Technician printerTech = done.getAssignee().orElseThrow();
        day1.acknowledge(printerTech, done.getIncidentId());
        day1.startWork(printerTech, done.getIncidentId());
        day1.resolve(printerTech, done.getIncidentId(), "Cleared the paper path and rollers.", "Worn roller", "Replace rollers yearly");

        // Day 2: brand-new desk, same database
        ServiceDesk day2 = new ServiceDesk(c);
        day2.attachStorage(db);
        assertFalse(day2.isEmpty());
        User ravi = day2.login("ravi@corp.in", SampleData.PASSWORD);           // password hash survived
        Incident reloaded = day2.getIncident(ravi, open.getIncidentId());
        assertEquals("AWAITING_INFO", reloaded.getStatus());
        assertTrue(reloaded.getSla().isPaused());
        assertEquals(open.getPriorityExplanation(), reloaded.getPriorityExplanation());
        Technician tech2 = (Technician) day2.user(tech.getUserId());
        assertEquals(8, tech2.workloadPoints(), "workload rebuilt from open incidents");
        assertEquals(1, ((Technician) day2.user(printerTech.getUserId())).getResolvedCount());
        assertEquals(day1.audit().all().size(), day2.audit().all().size());
        assertEquals("INC1003", day2.factory().peekNextId(), "numbering continues");

        // ...and work simply continues
        day2.provideInfo(ravi, open.getIncidentId(), "Hyderabad");
        assertEquals("IN_PROGRESS", reloaded.getStatus());
    }

    @Test void userRecordRoundTrip() {
        Technician t = org.tech("tNet");
        User back = UserRecord.from(t).toUser();
        assertInstanceOf(Technician.class, back);
        assertEquals(t.getSkills(), ((Technician) back).getSkills());
        assertTrue(back.checkPassword(SampleData.PASSWORD));
    }

    @Test void loginLocksAfterFiveFailures() {
        for (int k = 0; k < 5; k++) {
            assertThrows(AuthenticationException.class, () -> desk.login("ravi@corp.in", "wrongpass1"));
        }
        var ex = assertThrows(AuthenticationException.class, () -> desk.login("ravi@corp.in", SampleData.PASSWORD));
        assertTrue(ex.getMessage().contains("Too many"));
        clock.advanceMinutes(16);
        assertEquals("E101", desk.login("ravi@corp.in", SampleData.PASSWORD).getUserId());
    }

    @Test void resolvedIncidentsAutoClose() {
        Incident i = reportPayment();
        work(i);
        resolve(i);
        clock.advance(Duration.ofHours(71));
        assertTrue(desk.runMonitor().autoClosed().isEmpty());
        clock.advance(Duration.ofHours(2));
        assertEquals(List.of(i.getIncidentId()), desk.runMonitor().autoClosed());
        assertEquals("CLOSED", i.getStatus());
    }

    @Test void technicianQueueIsSortedByUrgency() {
        Technician tara = org.tech("tApp");
        desk.setAssignmentStrategy(u("admin"), "skill");
        Incident low = desk.reportIncident(u("emp2"), IncidentRequest.builder("Payment report typo",
            "Small label typo on the payment receipt page").service("SVC-PAY").impact("LOW").urgency("LOW").build());
        Incident high = reportPayment();
        assertEquals(List.of(high, low), desk.myQueue(tara));
        assertEquals(List.of(high), desk.myIncidents(u("emp1")));
    }

    @Test void manageTechnicians() {
        desk.updateTechnicianSkills(u("admin"), "T204", Map.of("CLOUD", 4));
        assertEquals(4, org.tech("tJr").skillLevel("CLOUD"));
        assertEquals(0, org.tech("tJr").skillLevel("HARDWARE"));
        desk.setAvailability(org.tech("tJr"), "T204", false);           // self
        assertFalse(org.tech("tJr").isAvailable());
        assertThrows(UnauthorizedOperationException.class, () -> desk.setAvailability(org.tech("tNet"), "T204", true));
        assertThrows(UnauthorizedOperationException.class, () -> desk.updateTechnicianSkills(u("lead"), "T204", Map.of()));
    }

    @Test void brokenNotificationChannelDoesNotBreakWorkflow() {
        desk.addNotificationChannel(new NotificationChannel() {
            public String name() { return "sms"; }
            public void send(Notification n) { throw new RuntimeException("SMS provider timeout"); }
        });
        Incident i = reportPayment();                         // P1 → urgent → uses SMS too
        assertEquals("ASSIGNED", i.getStatus());
        assertFalse(desk.notificationFailures(u("manager")).isEmpty());
    }

    @Test void adminViewsAuditLogAndViolations() {
        Incident i = reportPayment();
        clock.advanceMinutes(40);
        desk.runMonitor();
        assertEquals(List.of(i), desk.slaViolations(u("manager")));
        assertFalse(desk.allAuditLogs(u("admin")).isEmpty());
        assertThrows(UnauthorizedOperationException.class, () -> desk.allAuditLogs(u("tApp")));
    }

    @Test void incidentSerializesToJson() {
        String json = Json.write(reportPayment().toMap(desk.now()));
        assertTrue(json.startsWith("{\"incidentId\":\"INC1001\""));
        assertTrue(json.contains("\"allowedActions\":[\"ASSIGN\",\"ACKNOWLEDGE\"]"));
    }
}
