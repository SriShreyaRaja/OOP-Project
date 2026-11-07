package com.itsm.domain.state;

/** Fix delivered. Reporter can verify or reopen; auto-close is allowed if they stay silent. */
final class ResolvedState extends IncidentState {
    @Override public String name() { return "RESOLVED"; }
    @Override public boolean isOpen() { return false; }
    @Override public boolean slaRunning() { return false; }
    @Override public IncidentState verify() { return States.VERIFIED; }
    @Override public IncidentState reopen() { return States.REOPENED; }
    @Override public IncidentState close() { return States.CLOSED; }
}
