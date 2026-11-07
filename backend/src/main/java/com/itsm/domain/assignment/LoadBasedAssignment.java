package com.itsm.domain.assignment;

import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;

import java.util.List;

/** Whoever has the most spare capacity (in workload points). Skill not required. */
public class LoadBasedAssignment extends AssignmentStrategy {
    @Override public String name() { return "load"; }
    @Override protected boolean requiresSkill() { return false; }

    @Override
    protected Candidate score(Incident incident, Technician t) {
        return new Candidate(t, 1.0 - t.loadRatio(),
            List.of("workload " + t.workloadPoints() + "/" + t.getMaxWorkloadPoints() + " points"));
    }
}
