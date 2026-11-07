package com.itsm.domain.exception;

public class ServiceNotFoundException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public ServiceNotFoundException(String message) { super("SERVICE_NOT_FOUND", message); }
    @Override public int httpStatus() { return 404; }
}
