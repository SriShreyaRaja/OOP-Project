package com.itsm.domain.exception;

public class InvalidStateTransitionException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public InvalidStateTransitionException(String message) { super("INVALID_STATE_TRANSITION", message); }
    @Override public int httpStatus() { return 409; }
}
