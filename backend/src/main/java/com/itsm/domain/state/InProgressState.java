package com.itsm.domain.state;

final class InProgressState extends IncidentState {
    @Override public String name() { return "IN_PROGRESS"; }
    @Override public IncidentState assign() { return States.ASSIGNED; }
    @Override public IncidentState requestInfo() { return States.AWAITING_INFO; }
    @Override public IncidentState resolve() { return States.RESOLVED; }
}
