package com.itsm.domain.state;

/** Terminal. A recurrence is a new incident linked to this one. */
final class ClosedState extends IncidentState {
    @Override public String name() { return "CLOSED"; }
    @Override public boolean isOpen() { return false; }
    @Override public boolean slaRunning() { return false; }
}
