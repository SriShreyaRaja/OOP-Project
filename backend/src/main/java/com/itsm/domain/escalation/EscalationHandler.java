package com.itsm.domain.escalation;

import com.itsm.domain.common.Role;

import java.time.Duration;
import java.util.Optional;

/**
 * CHAIN OF RESPONSIBILITY: one link in the escalation ladder.
 * If this level's waiting threshold has passed, it asks the next (higher) level
 * whether it should take over instead; the highest level whose threshold has
 * passed wins.
 */
public class EscalationHandler {
    private final int level;
    private final Role role;
    private final Duration after;
    private EscalationHandler next;

    public EscalationHandler(int level, Role role, Duration after) {
        this.level = level;
        this.role = role;
        this.after = after;
    }

    public EscalationHandler setNext(EscalationHandler next) {
        this.next = next;
        return next;
    }

    public Optional<EscalationHandler> handle(Duration waited) {
        if (waited.compareTo(after) < 0) return Optional.empty();
        Optional<EscalationHandler> higher = next == null ? Optional.empty() : next.handle(waited);
        return higher.isPresent() ? higher : Optional.of(this);
    }

    public int level() { return level; }
    public Role role() { return role; }
}
