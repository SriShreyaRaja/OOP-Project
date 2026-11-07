package com.itsm.domain.priority;

import com.itsm.domain.exception.ValidationException;

import java.util.Map;
import java.util.function.Supplier;

public final class PriorityStrategies {
    private static final Map<String, Supplier<PriorityStrategy>> REGISTRY = Map.of(
        "weighted", WeightedScorePriorityStrategy::new,
        "matrix", MatrixPriorityStrategy::new);

    private PriorityStrategies() {}

    public static PriorityStrategy byName(String name) {
        Supplier<PriorityStrategy> s = REGISTRY.get(name);
        if (s == null) throw new ValidationException("Unknown priority strategy '" + name + "'. Options: " + REGISTRY.keySet());
        return s.get();
    }
}
