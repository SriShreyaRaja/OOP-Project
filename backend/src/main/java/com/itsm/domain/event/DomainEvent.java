package com.itsm.domain.event;

import com.itsm.domain.common.EventType;
import com.itsm.domain.common.TimeFormat;

import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/**
 * Something important that happened to an incident. Immutable.
 * Also serves as an audit record: timestamp, user, action, incident, previous/new state, description.
 */
public record DomainEvent(EventType type, String incidentId, String actorId, Instant at,
                          String description, String previousState, String newState,
                          List<String> recipients, boolean urgent) {

    public DomainEvent {
        recipients = List.copyOf(recipients);
    }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("event", type.name());
        m.put("incidentId", incidentId);
        m.put("actor", actorId);
        m.put("at", at.toString());
        m.put("atDisplay", TimeFormat.both(at));
        m.put("description", description);
        m.put("previousState", previousState);
        m.put("newState", newState);
        return m;
    }
}
