package com.itsm.domain.exception;

/**
 * Root of the custom exception hierarchy.
 *
 * Every business-rule violation throws a specific subclass. The API layer
 * (Member 3) can catch ITSMException once and use {@link #getCode()} and
 * {@link #httpStatus()} to build the HTTP response; tests (Member 4) can
 * assert the exact subclass. Unchecked, so business methods stay readable.
 */
public class ITSMException extends RuntimeException {
    private static final long serialVersionUID = 1L;
    private final String code;

    public ITSMException(String code, String message) {
        super(message);
        this.code = code;
    }

    public ITSMException(String code, String message, Throwable cause) {
        super(message, cause);
        this.code = code;
    }

    public String getCode() { return code; }

    /** Suggested HTTP status, so the mapping lives in one place. */
    public int httpStatus() { return 400; }
}
