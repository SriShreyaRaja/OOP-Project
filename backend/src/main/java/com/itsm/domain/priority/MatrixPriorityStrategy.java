package com.itsm.domain.priority;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.common.Impact;
import com.itsm.domain.common.Priority;
import com.itsm.domain.common.Urgency;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The classic ITIL impact/urgency matrix (by sum of the two levels), with a
 * one-level bump for business-critical services (criticality 5).
 */
public class MatrixPriorityStrategy implements PriorityStrategy {

    @Override public String name() { return "matrix"; }

    @Override
    public PriorityResult calculate(Impact impact, Urgency urgency, ITService service, int affectedUsers) {
        int sum = impact.weight() + urgency.weight();
        Priority p = sum >= 7 ? Priority.P1 : sum >= 5 ? Priority.P2 : sum == 4 ? Priority.P3 : Priority.P4;
        boolean bumped = false;
        if (service.getBusinessCriticality() == 5 && p != Priority.P1) {
            p = Priority.values()[p.ordinal() - 1];
            bumped = true;
        }
        Map<String, Object> why = new LinkedHashMap<>();
        why.put("strategy", name());
        why.put("formula", "ITIL matrix on Impact + Urgency, +1 level for critical services");
        why.put("impact", impact.name());
        why.put("urgency", urgency.name());
        why.put("matrixSum", sum);
        why.put("criticalServiceBump", bumped);
        why.put("score", (double) sum);
        why.put("result", p.toString());
        return new PriorityResult(p, sum, why);
    }
}
