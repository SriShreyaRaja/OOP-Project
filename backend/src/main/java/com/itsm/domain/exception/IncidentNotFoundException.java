package com.itsm.domain.exception;

public class IncidentNotFoundException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public IncidentNotFoundException(String message) { super("INCIDENT_NOT_FOUND", message); }
    @Override public int httpStatus() { return 404; }
}
