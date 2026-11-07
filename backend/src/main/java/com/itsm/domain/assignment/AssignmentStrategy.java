package com.itsm.domain.assignment;

import com.itsm.domain.exception.TechnicianUnavailableException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * STRATEGY PATTERN #2 (and TEMPLATE METHOD): technician assignment.
 *
 * The template is fixed: filter eligible → score each → sort → pick the best.
 * Subclasses only supply {@link #score}. Every result carries human-readable reasons.
 */
public abstract class AssignmentStrategy {

    public abstract String name();

    /** Does this strategy insist on a skill match for the incident's category? */
    protected boolean requiresSkill() { return true; }

    protected abstract Candidate score(Incident incident, Technician technician);

    /** Available, with spare capacity for this priority, and (if required) skilled. */
    public List<Technician> eligible(Incident incident, List<Technician> all) {
        List<Technician> pool = all.stream()
            .filter(t -> t.hasCapacityFor(incident.getPriority()))
            .toList();
        if (requiresSkill() && incident.getCategory() != null) {
            List<Technician> skilled = pool.stream().filter(t -> t.skillLevel(incident.getCategory()) > 0).toList();
            if (!skilled.isEmpty()) return skilled;   // otherwise fall back to anyone free
        }
        return pool;
    }

    public List<Candidate> rank(Incident incident, List<Technician> all) {
        List<Candidate> out = new ArrayList<>();
        for (Technician t : eligible(incident, all)) out.add(score(incident, t));
        out.sort(Comparator.comparingDouble(Candidate::score).reversed()
            .thenComparingInt(c -> c.technician().workloadPoints())
            .thenComparing(c -> c.technician().getUserId()));
        return out;
    }

    public Candidate select(Incident incident, List<Technician> all) {
        List<Candidate> ranked = rank(incident, all);
        if (ranked.isEmpty()) {
            throw new TechnicianUnavailableException(
                "No technician has capacity for " + incident.getIncidentId() + " (" + incident.getPriority() + ").");
        }
        return ranked.get(0);
    }
}
