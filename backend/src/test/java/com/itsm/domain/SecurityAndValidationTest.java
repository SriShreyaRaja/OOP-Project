package com.itsm.domain;

import com.itsm.domain.desk.IncidentRequest;
import com.itsm.domain.exception.*;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Employee;
import com.itsm.domain.user.Technician;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Authorization, authentication and input validation")
class SecurityAndValidationTest extends TestSupport {

    @Test void loginWorksAndRejectsWrongPassword() {
        assertEquals("E101", desk.login("ravi@corp.in", "Passw0rd!").getUserId());
        assertThrows(AuthenticationException.class, () -> desk.login("ravi@corp.in", "nope12345"));
        assertThrows(AuthenticationException.class, () -> desk.login("ghost@corp.in", "Passw0rd!"));
    }

    @Test void deactivatedUserCannotLoginOrAct() {
        desk.deactivateUser(u("admin"), "E102");
        assertThrows(AuthenticationException.class, () -> desk.login("sana@corp.in", "Passw0rd!"));
        assertThrows(UnauthorizedOperationException.class, () -> desk.reportIncident(u("emp2"), paymentOutage().build()));
    }

    @Test void employeeCannotResolve() {
        Incident i = reportPayment();
        assertThrows(UnauthorizedOperationException.class, () ->
            desk.resolve(u("emp1"), i.getIncidentId(), "I fixed it myself somehow", "unknown", null));
    }

    @Test void otherTechnicianCannotAcknowledge() {
        Incident i = reportPayment();
        Technician other = assignee(i).equals(org.tech("tNet")) ? org.tech("tDb") : org.tech("tNet");
        assertThrows(UnauthorizedOperationException.class, () -> desk.acknowledge(other, i.getIncidentId()));
    }

    @Test void employeeCannotConfigureOrSeeOthersIncidents() {
        Incident i = reportPayment();
        assertThrows(UnauthorizedOperationException.class, () -> desk.setAssignmentStrategy(u("emp1"), "load"));
        assertThrows(UnauthorizedOperationException.class, () -> desk.getIncident(u("emp2"), i.getIncidentId()));
        assertThrows(UnauthorizedOperationException.class, () -> desk.overview(u("emp1")));
    }

    @Test void internalNotesHiddenFromEmployees() {
        Incident i = reportPayment();
        desk.addNote(assignee(i), i.getIncidentId(), "DB creds rotated", true);
        assertTrue(i.visibleNotes(u("emp1")).isEmpty());
        assertEquals(1, i.visibleNotes(assignee(i)).size());
    }

    @ParameterizedTest
    @CsvSource(delimiter = '|', value = {
        "Hi           | Payment app is down for everyone | HIGH | 1",
        "Payment down | short                            | HIGH | 1",
        "Payment down | Payment app is down for us       | HUGE | 1",
        "Payment down | Payment app is down for us       | HIGH | 0"
    })
    void invalidIncidentInputIsRejected(String title, String desc, String impact, int users) {
        assertThrows(ValidationException.class, () -> desk.reportIncident(u("emp1"),
            IncidentRequest.builder(title, desc).service("SVC-PAY").impact(impact).affectedUsers(users).build()));
    }

    @Test void unknownServiceAndCategory() {
        assertThrows(ServiceNotFoundException.class, () -> desk.reportIncident(u("emp1"),
            IncidentRequest.builder("Thing broken", "Something is broken here").service("NOPE").build()));
        assertThrows(CategoryNotFoundException.class, () -> desk.reportIncident(u("emp1"),
            IncidentRequest.builder("Thing broken", "Something is broken here").service("SVC-PAY").category("ALIENS").build()));
        assertEquals("INC1001", desk.factory().peekNextId(), "rejected reports must not burn IDs");
    }

    @Test void weakPasswordsAndBadEmailsRejected() {
        assertThrows(ValidationException.class, () -> new Employee("E9", "X", "x@corp.in", "short", null));
        assertThrows(ValidationException.class, () -> new Employee("E9", "X", "x@corp.in", "onlyletters", null));
        assertThrows(ValidationException.class, () -> new Employee("E9", "X", "not-an-email", "longenough1", null));
    }

    @Test void duplicateRegistrationRejected() {
        assertThrows(ValidationException.class, () ->
            desk.registerUser(u("admin"), new Employee("E101", "Copy", "copy@corp.in", "Passw0rd!", null)));
        assertThrows(ValidationException.class, () ->
            desk.registerUser(u("admin"), new Employee("E999", "Copy", "ravi@corp.in", "Passw0rd!", null)));
    }

    @Test void passwordIsHashedNotStored() {
        Employee e = new Employee("E9", "X", "x@corp.in", "CorrectHorse1", null);
        assertTrue(e.checkPassword("CorrectHorse1"));
        assertFalse(e.checkPassword("wrong"));
        assertFalse(e.toMap().containsValue("CorrectHorse1"));
    }

    @Test void workloadPointsAreEnforced() {
        Technician t = new Technician("T9", "T", "t@corp.in", "Passw0rd1", Map.of("NETWORK", 3), 10, 1);
        t.takeIncident("INC1", com.itsm.domain.common.Priority.P1);   // 8 points
        assertThrows(WorkloadExceededException.class, () -> t.takeIncident("INC2", com.itsm.domain.common.Priority.P2));
        t.takeIncident("INC3", com.itsm.domain.common.Priority.P4);   // 1 point still fits
        assertEquals(9, t.workloadPoints());
    }
}
