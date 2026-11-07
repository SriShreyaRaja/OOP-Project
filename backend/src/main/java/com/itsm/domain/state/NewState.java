package com.itsm.domain.state;

final class NewState extends IncidentState {
    @Override public String name() { return "NEW"; }
    @Override public IncidentState classify() { return States.CLASSIFIED; }
}
