package com.itsm.domain.exception;

public class TechnicianUnavailableException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public TechnicianUnavailableException(String message) { super("TECHNICIAN_UNAVAILABLE", message); }
    @Override public int httpStatus() { return 409; }
}
