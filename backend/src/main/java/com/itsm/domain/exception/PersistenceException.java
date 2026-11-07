package com.itsm.domain.exception;

/** Database failure. Member 3 wraps SQLException in this so the API answers 503 cleanly. */
public class PersistenceException extends ITSMException {
    private static final long serialVersionUID = 1L;

    public PersistenceException(String message, Throwable cause) {
        super("DATABASE_FAILURE", message, cause);
    }

    @Override public int httpStatus() { return 503; }
}
