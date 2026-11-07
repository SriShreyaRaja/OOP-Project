package com.itsm.domain.state;

final class VerifiedState extends IncidentState {
    @Override public String name() { return "VERIFIED"; }
    @Override public boolean isOpen() { return false; }
    @Override public boolean slaRunning() { return false; }
    @Override public IncidentState reopen() { return States.REOPENED; }
    @Override public IncidentState close() { return States.CLOSED; }
}
