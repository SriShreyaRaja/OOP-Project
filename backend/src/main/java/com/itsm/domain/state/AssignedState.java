package com.itsm.domain.state;

final class AssignedState extends IncidentState {
    @Override public String name() { return "ASSIGNED"; }
    @Override public IncidentState assign() { return States.ASSIGNED; }
    @Override public IncidentState acknowledge() { return States.ACKNOWLEDGED; }
}
