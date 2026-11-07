package com.itsm.domain.persistence;

import com.itsm.domain.catalog.Category;
import com.itsm.domain.event.DomainEvent;
import com.itsm.domain.sla.SLAPolicy;

import java.util.List;

/**
 * THE ONE INTERFACE MEMBER 3 IMPLEMENTS to give the system a real database.
 *
 * How it works ("write-through"): the domain keeps live objects in memory for speed and
 * calls save…() every time something changes, so the database is always up to date.
 * On startup, {@code desk.attachStorage(adapter)} calls load…() and rebuilds everything.
 *
 * Only users, incidents and services are required. Everything else has a default that does
 * nothing, so a first version can implement just six methods and add the rest later.
 *
 * Every method should wrap SQL errors in {@code PersistenceException} so the API returns a
 * clean "DATABASE_FAILURE" (HTTP 503) instead of crashing.
 */
public interface StorageAdapter {

    void saveUser(UserRecord user);
    List<UserRecord> loadUsers();

    void saveIncident(IncidentRecord incident);
    List<IncidentRecord> loadIncidents();

    void saveService(ServiceRecord service);
    List<ServiceRecord> loadServices();

    default void saveAuditEvent(DomainEvent event) {}
    default List<DomainEvent> loadAuditEvents() { return List.of(); }

    default void saveCategory(Category category) {}
    default List<Category> loadCategories() { return List.of(); }

    default void saveSlaPolicy(SLAPolicy policy) {}
    default List<SLAPolicy> loadSlaPolicies() { return List.of(); }

    /** Used when no database is attached (tests, demo). */
    StorageAdapter NONE = new StorageAdapter() {
        public void saveUser(UserRecord u) {}
        public List<UserRecord> loadUsers() { return List.of(); }
        public void saveIncident(IncidentRecord i) {}
        public List<IncidentRecord> loadIncidents() { return List.of(); }
        public void saveService(ServiceRecord s) {}
        public List<ServiceRecord> loadServices() { return List.of(); }
    };
}
