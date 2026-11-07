package com.itsm.domain.repository;

import com.itsm.domain.incident.Incident;

import java.util.*;
import java.util.concurrent.ConcurrentHashMap;

/** HashMap-backed: O(1) lookup by ID. Used for tests/demo until the DB version exists. */
public class InMemoryIncidentRepository implements IncidentRepository {
    private final Map<String, Incident> items = new ConcurrentHashMap<>();

    @Override public void save(Incident incident) { items.put(incident.getIncidentId(), incident); }
    @Override public Optional<Incident> findById(String id) { return Optional.ofNullable(items.get(id)); }

    @Override public List<Incident> findAll() {
        List<Incident> all = new ArrayList<>(items.values());
        all.sort(Comparator.comparing(Incident::getCreatedAt).thenComparing(Incident::getIncidentId));
        return all;
    }
}
