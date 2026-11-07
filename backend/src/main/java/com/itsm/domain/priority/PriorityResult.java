package com.itsm.domain.priority;

import com.itsm.domain.common.Priority;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

/** A priority plus the full reasoning behind it ("why is this P1?"). */
public record PriorityResult(Priority priority, double score, Map<String, Object> explanation) {
    public PriorityResult {
        explanation = Collections.unmodifiableMap(new LinkedHashMap<>(explanation));   // keeps display order
    }
}
