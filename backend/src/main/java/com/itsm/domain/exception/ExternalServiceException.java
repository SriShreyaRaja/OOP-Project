package com.itsm.domain.exception;

/** Network / third-party failure (e.g. the SMS or email provider is unreachable). */
public class ExternalServiceException extends ITSMException {
    private static final long serialVersionUID = 1L;

    public ExternalServiceException(String message, Throwable cause) {
        super("EXTERNAL_SERVICE_FAILURE", message, cause);
    }

    @Override public int httpStatus() { return 502; }
}
