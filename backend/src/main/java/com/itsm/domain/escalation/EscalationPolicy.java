package com.itsm.domain.escalation;

import com.itsm.domain.common.Priority;
import com.itsm.domain.common.Role;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.state.States;

import java.time.Duration;
import java.time.Instant;
import java.util.EnumMap;
import java.util.Map;
import java.util.Optional;
import java.util.Set;

/**
 * Intelligent Feature C: Automatic Escalation.
 * A P1/P2 incident that nobody has acknowledged climbs:
 *   Technician → Team Lead → System Administrator → IT Manager
 * Thresholds (minutes since creation) are configurable per priority.
 */
public class EscalationPolicy {
    private static final Set<String> WATCHED = Set.of(
        States.CLASSIFIED.name(), States.ASSIGNED.name(), States.REOPENED.name());

    private final Map<Priority, int[]> thresholds = new EnumMap<>(Priority.class);

    public EscalationPolicy() {
        thresholds.put(Priority.P1, new int[]{5, 15, 30});
        thresholds.put(Priority.P2, new int[]{15, 45, 90});
    }

    public void configure(Priority p, int teamLeadMin, int sysAdminMin, int managerMin) {
        thresholds.put(p, new int[]{teamLeadMin, sysAdminMin, managerMin});
    }

    private Optional<EscalationHandler> chainFor(Priority p) {
        int[] t = thresholds.get(p);
        if (t == null) return Optional.empty();
        EscalationHandler head = new EscalationHandler(1, Role.TEAM_LEAD, Duration.ofMinutes(t[0]));
        head.setNext(new EscalationHandler(2, Role.SYSTEM_ADMIN, Duration.ofMinutes(t[1])))
            .setNext(new EscalationHandler(3, Role.IT_MANAGER, Duration.ofMinutes(t[2])));
        return Optional.of(head);
    }

    /** The level to escalate to now, or empty if nothing should happen. */
    public Optional<EscalationHandler> evaluate(Incident incident, Instant now) {
        if (incident.getPriority() == null || !WATCHED.contains(incident.getStatus())) return Optional.empty();
        Duration waited = Duration.between(incident.getCreatedAt(), now);
        return chainFor(incident.getPriority())
            .flatMap(chain -> chain.handle(waited))
            .filter(h -> h.level() > incident.getEscalationLevel());
    }
}
