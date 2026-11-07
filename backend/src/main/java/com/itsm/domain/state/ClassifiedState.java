package com.itsm.domain.state;

/** Category, priority and SLA known. Re-classification is allowed. */
final class ClassifiedState extends IncidentState {
    @Override public String name() { return "CLASSIFIED"; }
    @Override public IncidentState classify() { return States.CLASSIFIED; }
    @Override public IncidentState assign() { return States.ASSIGNED; }
}
