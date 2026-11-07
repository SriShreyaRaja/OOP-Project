package com.itsm.domain.exception;

public class WorkloadExceededException extends ITSMException {
    private static final long serialVersionUID = 1L;
    public WorkloadExceededException(String message) { super("WORKLOAD_EXCEEDED", message); }
    @Override public int httpStatus() { return 409; }
}
