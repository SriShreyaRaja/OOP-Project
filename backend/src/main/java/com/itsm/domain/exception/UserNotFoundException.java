package com.itsm.domain.exception;

public class UserNotFoundException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public UserNotFoundException(String message) { super("USER_NOT_FOUND", message); }
    @Override public int httpStatus() { return 404; }
}
