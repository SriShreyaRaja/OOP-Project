package com.itsm.domain.state;

/** Waiting for the reporter. The SLA clock is PAUSED here. */
final class AwaitingInfoState extends IncidentState {
    @Override public String name() { return "AWAITING_INFO"; }
    @Override public boolean slaRunning() { return false; }
    @Override public IncidentState provideInfo() { return States.IN_PROGRESS; }
}
