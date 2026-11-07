package com.itsm.domain.exception;

public class DependencyCycleException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public DependencyCycleException(String message) { super("DEPENDENCY_CYCLE", message); }
    @Override public int httpStatus() { return 409; }
}
