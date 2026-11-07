package com.itsm.domain.assignment;

import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;

import java.util.List;

/** Best proficiency in the incident's category wins; experience breaks ties. */
public class SkillBasedAssignment extends AssignmentStrategy {
    @Override public String name() { return "skill"; }

    @Override
    protected Candidate score(Incident incident, Technician t) {
        int lvl = t.skillLevel(incident.getCategory());
        double score = lvl + Math.min(t.getYearsExperience(), 10) / 100.0;
        return new Candidate(t, score, List.of(incident.getCategory() + " skill " + lvl + "/5",
                                               t.getYearsExperience() + "y experience"));
    }
}
