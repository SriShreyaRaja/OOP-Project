package com.itsm.domain.assignment;

import com.itsm.domain.exception.ValidationException;

import java.util.Map;
import java.util.function.Supplier;

/** Registry so an admin can pick a strategy by name (e.g. from a dropdown). */
public final class AssignmentStrategies {
    private static final Map<String, Supplier<AssignmentStrategy>> REGISTRY = Map.of(
        "skill", SkillBasedAssignment::new,
        "load", LoadBasedAssignment::new,
        "round_robin", RoundRobinAssignment::new,
        "priority", PriorityBasedAssignment::new,
        "smart", SmartRecommendationAssignment::new);

    private AssignmentStrategies() {}

    public static AssignmentStrategy byName(String name) {
        Supplier<AssignmentStrategy> s = REGISTRY.get(name);
        if (s == null) throw new ValidationException("Unknown assignment strategy '" + name + "'. Options: " + REGISTRY.keySet());
        return s.get();
    }
}
