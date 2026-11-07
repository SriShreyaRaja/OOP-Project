package com.itsm.domain.exception;

public class AuthenticationException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public AuthenticationException(String message) { super("INVALID_LOGIN", message); }
    @Override public int httpStatus() { return 401; }
}
