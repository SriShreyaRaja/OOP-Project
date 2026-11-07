package com.itsm.domain.state;

import com.itsm.domain.exception.InvalidStateTransitionException;

import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

/** Shared singleton instances of every state, plus lookup by name for persistence. */
public final class States {
    public static final IncidentState NEW = new NewState();
    public static final IncidentState CLASSIFIED = new ClassifiedState();
    public static final IncidentState ASSIGNED = new AssignedState();
    public static final IncidentState ACKNOWLEDGED = new AcknowledgedState();
    public static final IncidentState IN_PROGRESS = new InProgressState();
    public static final IncidentState AWAITING_INFO = new AwaitingInfoState();
    public static final IncidentState RESOLVED = new ResolvedState();
    public static final IncidentState VERIFIED = new VerifiedState();
    public static final IncidentState REOPENED = new ReopenedState();
    public static final IncidentState CLOSED = new ClosedState();

    private static final Map<String, IncidentState> BY_NAME = Stream.of(
            NEW, CLASSIFIED, ASSIGNED, ACKNOWLEDGED, IN_PROGRESS, AWAITING_INFO,
            RESOLVED, VERIFIED, REOPENED, CLOSED)
        .collect(Collectors.toUnmodifiableMap(IncidentState::name, Function.identity()));

    private States() {}

    /** Member 3: rebuild the state object from the status string stored in the database. */
    public static IncidentState fromName(String name) {
        IncidentState s = BY_NAME.get(name);
        if (s == null) throw new InvalidStateTransitionException("Unknown state '" + name + "'.");
        return s;
    }
}
