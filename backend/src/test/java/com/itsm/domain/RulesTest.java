package com.itsm.domain;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.common.Impact;
import com.itsm.domain.common.Priority;
import com.itsm.domain.common.Role;
import com.itsm.domain.common.Urgency;
import com.itsm.domain.desk.Reports;
import com.itsm.domain.exception.SLAConfigurationException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.priority.MatrixPriorityStrategy;
import com.itsm.domain.priority.PriorityResult;
import com.itsm.domain.priority.WeightedScorePriorityStrategy;
import com.itsm.domain.sla.SLAPolicy;
import com.itsm.domain.sla.SLAPolicyBook;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Business rules: priority, SLA, escalation")
class RulesTest extends TestSupport {

    @ParameterizedTest(name = "{0}×{1}×crit{2} → {3}")
    @CsvSource({
        "LOW,LOW,1,P4",                  // 1
        "MEDIUM,MEDIUM,3,P3",            // 12
        "HIGH,MEDIUM,4,P2",              // 24, exactly on P2 boundary
        "ORGANIZATION,CRITICAL,3,P1",    // 48, exactly on P1 boundary
        "HIGH,HIGH,2,P3"                 // 18
    })
    void weightedPriorityThresholds(Impact impact, Urgency urgency, int crit, Priority expected) {
        ITService s = new ITService("S", "Svc", crit, "SOFTWARE");
        assertEquals(expected, new WeightedScorePriorityStrategy().calculate(impact, urgency, s, 1).priority());
    }

    @Test void manyAffectedUsersRaisePriority() {
        ITService s = new ITService("S", "Svc", 2, "SOFTWARE");
        var w = new WeightedScorePriorityStrategy();
        assertEquals(Priority.P3, w.calculate(Impact.HIGH, Urgency.HIGH, s, 1).priority());           // 18
        assertEquals(Priority.P2, w.calculate(Impact.HIGH, Urgency.HIGH, s, 10_000).priority());      // 18×1.4=25.2
    }

    @Test void matrixBumpsCriticalServices() {
        PriorityResult r = new MatrixPriorityStrategy().calculate(Impact.MEDIUM, Urgency.MEDIUM,
                new ITService("S", "Core", 5, "DATABASE"), 1);
        assertEquals(Priority.P2, r.priority());
        assertEquals(true, r.explanation().get("criticalServiceBump"));
    }

    @Test void prioritySwapAtRuntime() {
        desk.setPriorityStrategy(u("admin"), "matrix");
        assertEquals("matrix", reportPayment().getPriorityExplanation().get("strategy"));
    }

    @Test void reassessmentUpdatesPrioritySlaAndWorkloadPoints() {
        Incident i = desk.reportIncident(u("emp2"), com.itsm.domain.desk.IncidentRequest.builder(
            "Printer jammed", "The second floor printer is jammed again").service("SVC-PRINT")
            .impact("LOW").urgency("LOW").build());
        assertEquals(Priority.P4, i.getPriority());
        int before = assignee(i).workloadPoints();
        desk.reassess(u("lead"), i.getIncidentId(), "ORGANIZATION", "CRITICAL", 2000);
        // 4 × 4 × 1 (printing is low-criticality) × 1.33 boost = 21.3 → P3
        assertEquals(Priority.P3, i.getPriority());
        assertEquals(Duration.ofHours(8), i.getSla().getPolicy().resolutionTarget());
        assertEquals(before - 1 + 3, assignee(i).workloadPoints());
    }

    @Test void serviceSpecificSlaOverridesDefault() {
        desk.configureSla(u("admin"), new SLAPolicy(Priority.P1, Duration.ofMinutes(2), Duration.ofMinutes(15), 0.75, "SVC-PAY"));
        assertEquals(Duration.ofMinutes(15), reportPayment().getSla().getPolicy().resolutionTarget());
    }

    @Test void missingSlaConfiguration() {
        assertThrows(SLAConfigurationException.class, () -> new SLAPolicyBook().policyFor(Priority.P1, null));
    }

    @Test void slaWarningThenBreachReportedOnce() {
        Incident i = reportPayment();
        desk.acknowledge(assignee(i), i.getIncidentId());
        clock.advanceMinutes(24);
        assertEquals(List.of(i.getIncidentId()), desk.runMonitor().warnings());
        clock.advanceMinutes(10);
        assertEquals(List.of(i.getIncidentId()), desk.runMonitor().breaches());
        assertTrue(desk.runMonitor().breaches().isEmpty(), "breach must not be re-announced");
    }

    @Test void autoEscalationClimbsTheChain() {
        Incident i = reportPayment();
        clock.advanceMinutes(6);
        assertEquals(List.of(Map.entry(i.getIncidentId(), Role.TEAM_LEAD)), desk.runMonitor().escalations());
        clock.advanceMinutes(30);
        assertEquals(List.of(Map.entry(i.getIncidentId(), Role.IT_MANAGER)), desk.runMonitor().escalations());
        assertFalse(desk.inbox(u("manager")).isEmpty());
    }

    @Test void acknowledgedIncidentsAreNotEscalated() {
        Incident i = reportPayment();
        desk.acknowledge(assignee(i), i.getIncidentId());
        clock.advanceMinutes(40);
        Reports.MonitorResult r = desk.runMonitor();
        assertTrue(r.escalations().isEmpty());
    }
}
