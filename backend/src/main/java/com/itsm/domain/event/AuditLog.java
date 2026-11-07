package com.itsm.domain.event;

import com.itsm.domain.common.TimeFormat;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

/** Append-only, chronological history of every important action. */
public class AuditLog implements EventObserver {
    private final List<DomainEvent> entries = new ArrayList<>();

    @Override public void onEvent(DomainEvent event) { entries.add(event); }

    /** Reload saved history after a restart (does not re-publish anything). */
    public void restore(List<DomainEvent> saved) { entries.addAll(saved); }

    public List<DomainEvent> all() { return Collections.unmodifiableList(entries); }

    public List<DomainEvent> forIncident(String incidentId) {
        return entries.stream().filter(e -> e.incidentId().equals(incidentId)).toList();
    }

    /** Human-readable timeline, like the example in the project brief. */
    public String timeline(String incidentId) {
        return forIncident(incidentId).stream()
            .map(e -> TimeFormat.both(e.at()) + " – " + e.incidentId() + " " + e.description())
            .collect(Collectors.joining("\n"));
    }
}
