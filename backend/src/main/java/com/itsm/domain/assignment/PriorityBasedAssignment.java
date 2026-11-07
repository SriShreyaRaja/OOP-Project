package com.itsm.domain.assignment;

import com.itsm.domain.common.Priority;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;

import java.util.List;

/** Critical work (P1/P2) goes to the most experienced; routine work (P3/P4) to the least loaded. */
public class PriorityBasedAssignment extends AssignmentStrategy {
    @Override public String name() { return "priority"; }

    @Override
    protected Candidate score(Incident incident, Technician t) {
        Priority p = incident.getPriority();
        if (p == Priority.P1 || p == Priority.P2) {
            double s = t.getYearsExperience() + t.skillLevel(incident.getCategory());
            return new Candidate(t, s, List.of("critical work → " + t.getYearsExperience() + "y experience + skill "
                    + t.skillLevel(incident.getCategory())));
        }
        return new Candidate(t, 1.0 - t.loadRatio(), List.of("routine work → workload "
                + t.workloadPoints() + "/" + t.getMaxWorkloadPoints()));
    }
}
