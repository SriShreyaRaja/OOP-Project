package com.itsm.domain;

import com.itsm.domain.assignment.*;
import com.itsm.domain.common.ServiceHealth;
import com.itsm.domain.desk.IncidentRequest;
import com.itsm.domain.desk.Reports;
import com.itsm.domain.desk.SearchCriteria;
import com.itsm.domain.exception.DependencyCycleException;
import com.itsm.domain.exception.DuplicateIncidentException;
import com.itsm.domain.exception.TechnicianUnavailableException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.intelligence.WhatIfSimulator;
import com.itsm.domain.user.Technician;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import java.util.List;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.*;

@DisplayName("Assignment strategies, intelligent features, search and reports")
class StrategyAndIntelligenceTest extends TestSupport {

    @Test void strategiesBehaveDifferently() {
        Incident i = desk.reportIncident(u("emp1"), paymentOutage().manualAssignment().build());
        List<Technician> techs = List.of(org.tech("lead"), org.tech("tApp"), org.tech("tNet"), org.tech("tDb"), org.tech("tJr"));
        assertEquals("T201", new SkillBasedAssignment().select(i, techs).technician().getUserId());
        assertEquals("L001", new PriorityBasedAssignment().select(i, techs).technician().getUserId());
        RoundRobinAssignment rr = new RoundRobinAssignment();
        assertNotEquals(rr.select(i, techs).technician(), rr.select(i, techs).technician());
        assertEquals(4, new SmartRecommendationAssignment().select(i, techs).reasons().size());
    }

    @Test void strategySwapAtRuntime() {
        desk.setAssignmentStrategy(u("admin"), "load");
        Incident i = desk.reportIncident(u("emp2"), IncidentRequest.builder("Wifi keeps dropping",
            "Office wifi disconnects every few minutes").build());
        assertTrue(i.getAssignmentReason().startsWith("load strategy"));
    }

    @Test void noCapacityLeavesIncidentForManualAssignment() {
        for (String k : List.of("lead", "tApp", "tNet", "tDb", "tJr")) org.tech(k).setAvailable(false);
        Incident i = reportPayment();
        assertEquals("CLASSIFIED", i.getStatus());
        assertThrows(TechnicianUnavailableException.class, () ->
            new SkillBasedAssignment().select(i, List.of(org.tech("tApp"))));
        org.tech("tApp").setAvailable(true);
        desk.assignManually(u("lead"), i.getIncidentId(), "T201");
        assertEquals("ASSIGNED", i.getStatus());
    }

    @Test void duplicatesAreLinkedAndCanBeBlocked() {
        Incident a = reportPayment();
        Incident b = desk.reportIncident(u("emp2"), IncidentRequest.builder("Payment transaction failing",
            "Payment transaction failing at checkout").impact("HIGH").urgency("HIGH").build());
        assertTrue(b.getRelatedIncidents().contains(a.getIncidentId()));
        assertTrue(a.getRelatedIncidents().contains(b.getIncidentId()));
        DuplicateIncidentException ex = assertThrows(DuplicateIncidentException.class, () ->
            desk.reportIncident(u("emp3"), IncidentRequest.builder("Unable to make payment",
                "Payment unavailable again for our team").blockDuplicates().build()));
        assertNotNull(ex.getOriginalIncidentId());
        assertEquals("INC1003", desk.factory().peekNextId());
    }

    @Test void correlationPointsToSharedRootCause() {
        reportPayment();
        desk.reportIncident(u("emp2"), IncidentRequest.builder("SSO login down", "Cannot login through SSO anywhere")
            .impact("ORGANIZATION").urgency("CRITICAL").build());
        assertEquals("SVC-AUTH", desk.correlations(u("manager")).get(0).suspectedRootServiceId());
    }

    @Test void dependencyCyclesAreRejected() {
        assertThrows(DependencyCycleException.class, () -> desk.addDependency(u("admin"), "SVC-DB", "SVC-RPT"));
        assertThrows(DependencyCycleException.class, () -> desk.addDependency(u("admin"), "SVC-DB", "SVC-DB"));
    }

    @Test void whatIfBlastRadius() {
        WhatIfSimulator.BlastRadius r = desk.simulateFailure(u("manager"), "SVC-DB");
        assertEquals(Set.of("Authentication SSO", "Payment Application", "Email & Calendar", "Finance Reporting"),
                     Set.copyOf(r.impactedServiceNames()));
        assertEquals(2, r.businessCriticalImpacted());
        assertEquals(0, desk.simulateFailure(u("manager"), "SVC-RPT").impactedCount());
    }

    @Test void slaRiskFlagsUnacknowledgedIncidentsEarly() {
        reportPayment();
        clock.advanceMinutes(3);
        var risk = desk.slaRisks(u("manager")).get(0);
        assertEquals("MEDIUM", risk.level());
        assertTrue(risk.factors().get(0).startsWith("not acknowledged"));
    }

    @Test void resolutionSuggestionsComeFromHistory() {
        Incident old = reportPayment();
        fullLifecycle(old);
        Incident fresh = desk.reportIncident(u("emp2"), IncidentRequest.builder("Payment transaction failing",
            "Payment transactions failing again").service("SVC-PAY").build());
        var s = desk.suggestResolutions(u("manager"), fresh.getIncidentId());
        assertEquals(old.getIncidentId(), s.get(0).fromIncidentId());
        assertEquals("Node memory leak", s.get(0).rootCause());
    }

    @Test void newCategoryWithoutCodeChange() {
        desk.addCategory(u("admin"), "IOT", Set.of("sensor", "thermostat"), "Smart building devices");
        Incident i = desk.reportIncident(u("emp1"), IncidentRequest.builder("Thermostat sensor offline",
            "The thermostat sensor in room 4 is offline").service("SVC-NET").build());
        assertEquals("IOT", i.getCategory());
    }

    @Test void searchSupportsManyCriteriaAndRespectsVisibility() {
        Incident a = reportPayment();
        desk.reportIncident(u("emp2"), IncidentRequest.builder("Printer jammed", "The 2nd floor printer is jammed")
            .service("SVC-PRINT").impact("LOW").urgency("LOW").build());
        var m = u("manager");
        assertEquals(List.of(a), desk.search(m, SearchCriteria.where().priority("P1")));
        assertEquals(1, desk.search(m, SearchCriteria.where().category("HARDWARE").openOnly()).size());
        assertEquals(1, desk.search(m, SearchCriteria.where().service("SVC-PAY").status("ASSIGNED")).size());
        assertEquals(2, desk.search(m, SearchCriteria.where().slaStatus("ON_TRACK")).size());
        assertEquals(1, desk.search(m, SearchCriteria.where().technician(assignee(a).getUserId()).text("payment")).size());
        assertTrue(desk.search(u("emp2"), SearchCriteria.where().text("payment")).isEmpty());
    }

    @Test void reportsAndServiceHealth() {
        Incident i = reportPayment();
        Reports.ServiceAnalysis pay = desk.serviceAnalysis(u("manager")).get(0);
        assertEquals(ServiceHealth.DOWN, pay.health());
        fullLifecycle(i);
        desk.giveFeedback(u("emp1"), i.getIncidentId(), 4, "ok");
        Reports.Overview o = desk.overview(u("manager"));
        assertEquals(1, o.totalIncidents());
        assertEquals(1, o.resolvedIncidents());
        assertEquals(0, o.openIncidents());
        assertEquals(4.0, o.averageFeedback());
        assertEquals(100.0, o.slaCompliancePercent());
    }
}
