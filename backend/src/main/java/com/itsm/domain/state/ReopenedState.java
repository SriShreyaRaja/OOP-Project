package com.itsm.domain.state;

/** The fix did not hold. Must be (re)assigned before work restarts. */
final class ReopenedState extends IncidentState {
    @Override public String name() { return "REOPENED"; }
    @Override public IncidentState assign() { return States.ASSIGNED; }
}
