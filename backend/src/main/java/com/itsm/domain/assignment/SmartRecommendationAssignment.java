package com.itsm.domain.assignment;

import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;

import java.util.List;

/**
 * Intelligent Feature D: Smart Technician Recommendation.
 * <pre>
 * score = w_skill·skill/5 + w_load·(1 − load) + w_history·min(fixes on this service, 5)/5
 *       + w_experience·min(years, 10)/10
 * </pre>
 * Weights are configurable by an admin and normalised to sum to 1.
 */
public class SmartRecommendationAssignment extends AssignmentStrategy {
    private final double wSkill, wLoad, wHistory, wExperience;

    public SmartRecommendationAssignment() { this(0.4, 0.3, 0.2, 0.1); }

    public SmartRecommendationAssignment(double skill, double load, double history, double experience) {
        double total = skill + load + history + experience;
        if (skill < 0 || load < 0 || history < 0 || experience < 0 || total <= 0) {
            throw new ValidationException("Weights must be non-negative and not all zero.");
        }
        wSkill = skill / total;
        wLoad = load / total;
        wHistory = history / total;
        wExperience = experience / total;
    }

    @Override public String name() { return "smart"; }

    @Override
    protected Candidate score(Incident incident, Technician t) {
        int skill = t.skillLevel(incident.getCategory());
        int history = t.experienceWith(incident.getService().getServiceId());
        double s = wSkill * skill / 5.0
                 + wLoad * (1 - t.loadRatio())
                 + wHistory * Math.min(history, 5) / 5.0
                 + wExperience * Math.min(t.getYearsExperience(), 10) / 10.0;
        return new Candidate(t, Math.round(s * 1000) / 1000.0, List.of(
            "skill " + skill + "/5",
            "workload " + t.workloadPoints() + "/" + t.getMaxWorkloadPoints(),
            "fixed " + incident.getService().getName() + " " + history + "×",
            t.getYearsExperience() + "y exp"));
    }
}
