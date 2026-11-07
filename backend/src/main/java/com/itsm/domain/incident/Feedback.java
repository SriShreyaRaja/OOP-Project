package com.itsm.domain.incident;

import com.itsm.domain.exception.ValidationException;

import java.time.Instant;

public record Feedback(int rating, String comment, Instant at) {
    public Feedback {
        if (rating < 1 || rating > 5) throw new ValidationException("Rating must be 1..5.");
    }
}
