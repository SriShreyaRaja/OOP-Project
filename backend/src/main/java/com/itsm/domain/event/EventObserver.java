package com.itsm.domain.event;

/** OBSERVER PATTERN: anything that wants to react to incident events. */
@FunctionalInterface
public interface EventObserver {
    void onEvent(DomainEvent event);
}
