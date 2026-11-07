package com.itsm.domain.exception;

/** Thrown when a report looks like an already-open incident. Carries the original's ID. */
public class DuplicateIncidentException extends ITSMException {
    private static final long serialVersionUID = 1L;
    private final String originalIncidentId;
    private final double similarity;

    public DuplicateIncidentException(String originalIncidentId, double similarity) {
        super("DUPLICATE_INCIDENT", String.format(
            "Looks like a duplicate of %s (similarity %.2f). Add details there instead.",
            originalIncidentId, similarity));
        this.originalIncidentId = originalIncidentId;
        this.similarity = similarity;
    }

    public String getOriginalIncidentId() { return originalIncidentId; }
    public double getSimilarity() { return similarity; }
    @Override public int httpStatus() { return 409; }
}
