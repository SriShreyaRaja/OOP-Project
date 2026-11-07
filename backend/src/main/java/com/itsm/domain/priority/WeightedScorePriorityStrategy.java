package com.itsm.domain.priority;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.common.Impact;
import com.itsm.domain.common.Priority;
import com.itsm.domain.common.Urgency;

import java.util.LinkedHashMap;
import java.util.Map;

/**
 * The formula from the brief, extended with a user-count boost:
 * <pre>
 *   base  = Impact(1-4) × Urgency(1-4) × Business Criticality(1-5)     (max 80)
 *   boost = 1 + 0.1 × log10(affected users)       1 user → ×1.0 · 1,000 users → ×1.3
 *   score = base × boost
 *   P1 ≥ 48 · P2 ≥ 24 · P3 ≥ 10 · else P4
 * </pre>
 * The log keeps the boost modest: many users matter, but a trivial problem can't
 * become critical just because it's widespread.
 */
public class WeightedScorePriorityStrategy implements PriorityStrategy {
    public static final double P1 = 48, P2 = 24, P3 = 10;

    @Override public String name() { return "weighted"; }

    @Override
    public PriorityResult calculate(Impact impact, Urgency urgency, ITService service, int affectedUsers) {
        int base = impact.weight() * urgency.weight() * service.getBusinessCriticality();
        double boost = 1 + 0.1 * Math.log10(Math.max(1, affectedUsers));
        double score = Math.round(base * boost * 10) / 10.0;
        Priority p = score >= P1 ? Priority.P1 : score >= P2 ? Priority.P2 : score >= P3 ? Priority.P3 : Priority.P4;

        Map<String, Object> why = new LinkedHashMap<>();
        why.put("strategy", name());
        why.put("formula", "Impact × Urgency × Criticality × UserBoost");
        why.put("impact", impact + " (" + impact.weight() + ")");
        why.put("urgency", urgency + " (" + urgency.weight() + ")");
        why.put("businessCriticality", service.getName() + " (" + service.getBusinessCriticality() + ")");
        why.put("affectedUsers", affectedUsers);
        why.put("userBoost", Math.round(boost * 100) / 100.0);
        why.put("score", score);
        why.put("thresholds", "P1≥48, P2≥24, P3≥10, else P4");
        why.put("result", p.toString());
        return new PriorityResult(p, score, why);
    }
}
