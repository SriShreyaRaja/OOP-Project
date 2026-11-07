package com.itsm.domain.exception;

public class UnauthorizedOperationException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public UnauthorizedOperationException(String message) { super("UNAUTHORIZED_OPERATION", message); }
    @Override public int httpStatus() { return 403; }
}
