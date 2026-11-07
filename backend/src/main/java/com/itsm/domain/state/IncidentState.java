package com.itsm.domain.state;

import com.itsm.domain.exception.InvalidStateTransitionException;

import java.util.Arrays;
import java.util.List;

/**
 * STATE PATTERN: the incident lifecycle.
 *
 * <pre>
 *  NEW → CLASSIFIED → ASSIGNED → ACKNOWLEDGED → IN_PROGRESS → RESOLVED → VERIFIED → CLOSED
 *                       ↑  ↺ reassign                │    ↑        │          │
 *                       │                            ▼    │        └─reopen─┬─┘
 *                       │                     AWAITING_INFO               ▼
 *                       └────────────────────────────────────────── REOPENED
 *                                              (SLA clock paused)
 * </pre>
 *
 * Every action defaults to "illegal" here. Each concrete state overrides ONLY the
 * actions that are legal from it, so NEW → CLOSED is impossible by construction
 * rather than by a long if/else chain. Adding a state (e.g. PENDING_VENDOR) means one
 * new class plus one override in the state that leads to it.
 *
 * States hold no data, so each is a shared singleton (see {@link States}).
 */
public abstract class IncidentState {

    public abstract String name();

    /** Counts as an open incident in reports and queues. */
    public boolean isOpen() { return true; }

    /** Does the SLA clock tick in this state? */
    public boolean slaRunning() { return true; }

    protected final IncidentState illegal(Action action) {
        throw new InvalidStateTransitionException(
            "Cannot " + action.name().toLowerCase().replace('_', ' ')
            + " an incident that is " + name() + ".");
    }

    public IncidentState classify()    { return illegal(Action.CLASSIFY); }
    public IncidentState assign()      { return illegal(Action.ASSIGN); }
    public IncidentState acknowledge() { return illegal(Action.ACKNOWLEDGE); }
    public IncidentState startWork()   { return illegal(Action.START_WORK); }
    public IncidentState requestInfo() { return illegal(Action.REQUEST_INFO); }
    public IncidentState provideInfo() { return illegal(Action.PROVIDE_INFO); }
    public IncidentState resolve()     { return illegal(Action.RESOLVE); }
    public IncidentState verify()      { return illegal(Action.VERIFY); }
    public IncidentState reopen()      { return illegal(Action.REOPEN); }
    public IncidentState close()       { return illegal(Action.CLOSE); }

    /** Polymorphic dispatch from an Action value to the matching method. */
    public final IncidentState next(Action action) {
        return switch (action) {
            case CLASSIFY -> classify();
            case ASSIGN -> assign();
            case ACKNOWLEDGE -> acknowledge();
            case START_WORK -> startWork();
            case REQUEST_INFO -> requestInfo();
            case PROVIDE_INFO -> provideInfo();
            case RESOLVE -> resolve();
            case VERIFY -> verify();
            case REOPEN -> reopen();
            case CLOSE -> close();
        };
    }

    public final boolean allows(Action action) {
        try {
            next(action);
            return true;
        } catch (InvalidStateTransitionException e) {
            return false;
        }
    }

    /** Exactly the buttons the UI should show right now. */
    public final List<Action> allowedActions() {
        return Arrays.stream(Action.values()).filter(this::allows).toList();
    }

    @Override public final String toString() { return name(); }
}
