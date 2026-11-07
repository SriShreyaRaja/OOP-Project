package com.itsm.domain;

import com.itsm.domain.common.SLAStatus;
import com.itsm.domain.event.DomainEvent;
import com.itsm.domain.exception.InvalidStateTransitionException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.notification.EmailChannel;
import com.itsm.domain.state.Action;
import com.itsm.domain.state.States;
import com.itsm.domain.user.Technician;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.time.Duration;
import java.util.List;
import java.util.Objects;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Incident lifecycle (State pattern) and the end-to-end workflow")
class LifecycleTest extends TestSupport {

    @Test void reportRunsTheFullPipeline() {
        Incident i = reportPayment();
        assertEquals("P1", i.getPriority().name());
        assertEquals("APPLICATION", i.getCategory());
        assertEquals("SVC-PAY", i.getService().getServiceId());
        assertEquals("ASSIGNED", i.getStatus());
        assertEquals(Duration.ofMinutes(30), i.getSla().getPolicy().resolutionTarget());
    }

    @Test void serviceIsGuessedFromTextWhenNotGiven() {
        assertEquals("SVC-PAY", reportPayment().getService().getServiceId());
    }

    @Test void completeLifecycleIsAuditedInOrder() {
        Incident i = reportPayment();
        fullLifecycle(i);
        List<String> states = desk.audit().forIncident(i.getIncidentId()).stream()
            .map(DomainEvent::newState).filter(Objects::nonNull).toList();
        assertEquals(List.of("NEW", "CLASSIFIED", "ASSIGNED", "ACKNOWLEDGED", "IN_PROGRESS",
                             "RESOLVED", "VERIFIED", "CLOSED"), states);
    }

    @Test void notificationsGoOutOnTwoChannels() {
        Incident i = reportPayment();
        String tid = assignee(i).getUserId();
        assertFalse(desk.inbox(assignee(i)).isEmpty());
        assertTrue(desk.channel("email", EmailChannel.class).outbox().stream().anyMatch(n -> n.recipientId().equals(tid)));
    }

    @Test void cannotCloseNewIncident() {
        assertThrows(InvalidStateTransitionException.class, States.NEW::close);
    }

    @Test void cannotResolveBeforeWorkStarts() {
        Incident i = reportPayment();
        assertThrows(InvalidStateTransitionException.class, () -> resolve(i));
        assertTrue(i.getResolutions().isEmpty(), "failed transition must not leave partial data");
    }

    @Test void allowedActionsReflectTheState() {
        Incident i = reportPayment();
        assertEquals(List.of(Action.ASSIGN, Action.ACKNOWLEDGE), i.allowedActions());
        assertTrue(States.CLOSED.allowedActions().isEmpty());
        assertEquals(States.IN_PROGRESS, States.fromName("IN_PROGRESS"));
    }

    @Test void slaPausesWhileAwaitingInfo() {
        Incident i = reportPayment();
        work(i);
        var dueBefore = i.getSla().resolutionDue();
        desk.requestInfo(assignee(i), i.getIncidentId(), "Which branch?");
        clock.advanceMinutes(120);
        assertEquals(SLAStatus.PAUSED, i.getSla().status(desk.now()));
        desk.provideInfo(u("emp1"), i.getIncidentId(), "Hyderabad");
        assertEquals(dueBefore.plus(Duration.ofMinutes(120)), i.getSla().resolutionDue());
    }

    @Test void reopenGoesBackToTheSameTechnician() {
        Incident i = reportPayment();
        Technician first = assignee(i);
        work(i);
        resolve(i);
        assertEquals(0, first.workloadPoints());
        desk.reopen(u("emp1"), i.getIncidentId(), "Still failing at counter 3");
        assertEquals("ASSIGNED", i.getStatus());
        assertEquals(first, assignee(i));
        assertTrue(i.getAssignmentReason().startsWith("sticky"));
        assertEquals(1, i.getReopenCount());
        assertEquals(1, i.getResolutions().size(), "previous resolution is kept as history");
    }

    @Test void feedbackOnlyAfterResolution() {
        Incident i = reportPayment();
        assertThrows(RuntimeException.class, () -> desk.giveFeedback(u("emp1"), i.getIncidentId(), 5, "great"));
        fullLifecycle(i);
        desk.giveFeedback(u("emp1"), i.getIncidentId(), 4, "ok");
        assertEquals(4, i.getFeedback().orElseThrow().rating());
    }
}
