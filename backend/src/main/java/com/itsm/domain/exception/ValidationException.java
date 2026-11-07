package com.itsm.domain.exception;

public class ValidationException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public ValidationException(String message) { super("INVALID_INPUT", message); }
    @Override public int httpStatus() { return 400; }
}
