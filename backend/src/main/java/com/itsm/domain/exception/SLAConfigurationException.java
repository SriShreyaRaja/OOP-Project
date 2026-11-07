package com.itsm.domain.exception;

public class SLAConfigurationException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public SLAConfigurationException(String message) { super("MISSING_SLA_CONFIGURATION", message); }
    @Override public int httpStatus() { return 500; }
}
