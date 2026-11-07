package com.itsm.domain.event;

import com.itsm.domain.common.EventType;

import java.util.*;

/**
 * The subject in the Observer pattern.
 * The Incident never calls "send email" or "write audit". It records events; the bus
 * hands each one to every subscribed observer. New reactions = new observer, zero
 * changes to Incident.
 */
public class EventBus {
    private final List<EventObserver> global = new ArrayList<>();
    private final Map<EventType, List<EventObserver>> byType = new EnumMap<>(EventType.class);

    public void subscribe(EventObserver observer) { global.add(observer); }

    public void subscribe(EventObserver observer, EventType... types) {
        for (EventType t : types) byType.computeIfAbsent(t, k -> new ArrayList<>()).add(observer);
    }

    public void publish(DomainEvent event) {
        global.forEach(o -> o.onEvent(event));
        byType.getOrDefault(event.type(), List.of()).forEach(o -> o.onEvent(event));
    }
}
