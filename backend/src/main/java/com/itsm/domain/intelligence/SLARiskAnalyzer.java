package com.itsm.domain.intelligence;

import com.itsm.domain.common.SLAStatus;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.sla.SLAClock;
import com.itsm.domain.user.Technician;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;

/**
 * Intelligent Feature E: predictive SLA risk, flagged BEFORE the standard 75% warning.
 * Factors: share of the response/resolution time used, whether anyone is assigned, how
 * loaded the assignee is, and whether the incident was reopened before.
 */
public class SLARiskAnalyzer {
    public record SLARisk(String incidentId, double risk, String level, List<String> factors) {}

    public Optional<SLARisk> assess(Incident incident, Instant now) {
        SLAClock sla = incident.getSla();
        if (!incident.isOpen() || sla == null) return Optional.empty();
        if (sla.status(now) == SLAStatus.BREACHED) {
            return Optional.of(new SLARisk(incident.getIncidentId(), 1.0, "BREACHED", List.of("SLA already violated")));
        }
        List<String> factors = new ArrayList<>();
        double used = Math.min(sla.usedFraction(now), 1.5);
        double risk = used * 0.6;
        factors.add(String.format("%.0f%% of resolution time used", used * 100));
        if (!sla.isResponded()) {
            double resp = Math.min(sla.responseUsedFraction(now), 1.5);
            if (resp * 0.6 > risk) {
                risk = resp * 0.6;
                factors.set(0, String.format("not acknowledged, %.0f%% of response time used", resp * 100));
            }
        }
        Optional<Technician> t = incident.getAssignee();
        if (t.isEmpty()) {
            risk += 0.25;
            factors.add("not assigned");
        } else {
            risk += t.get().loadRatio() * 0.2;
            factors.add(String.format("assignee load %.0f%%", t.get().loadRatio() * 100));
        }
        if (incident.getReopenCount() > 0) {
            risk += 0.1;
            factors.add("previously reopened");
        }
        risk = Math.round(Math.min(risk, 1.0) * 100) / 100.0;
        String level = risk >= 0.6 ? "HIGH" : risk >= 0.35 ? "MEDIUM" : "LOW";
        return Optional.of(new SLARisk(incident.getIncidentId(), risk, level, factors));
    }
}
