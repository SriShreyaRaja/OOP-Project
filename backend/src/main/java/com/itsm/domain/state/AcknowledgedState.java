package com.itsm.domain.state;

final class AcknowledgedState extends IncidentState {
    @Override public String name() { return "ACKNOWLEDGED"; }
    @Override public IncidentState assign() { return States.ASSIGNED; }
    @Override public IncidentState startWork() { return States.IN_PROGRESS; }
}
