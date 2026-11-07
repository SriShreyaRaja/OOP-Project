package com.itsm.domain.incident;

import com.itsm.domain.exception.ValidationException;

import java.time.Instant;

/**
 * What fixed the incident. Root cause and preventive action are recorded so the
 * "suggested resolution" feature and problem analysis have real knowledge to reuse.
 * Every resolution is kept, including ones that were later reopened.
 */
public record Resolution(String description, String rootCause, String preventiveAction,
                         String technicianId, Instant at) {
    public Resolution {
        if (description == null || description.strip().length() < 10) {
            throw new ValidationException("Resolution must describe the fix (min 10 characters).");
        }
        if (rootCause == null || rootCause.isBlank()) {
            throw new ValidationException("Root cause is required.");
        }
        preventiveAction = preventiveAction == null ? "" : preventiveAction;
    }
}
