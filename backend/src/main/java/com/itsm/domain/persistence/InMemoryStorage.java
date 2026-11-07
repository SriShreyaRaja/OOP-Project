package com.itsm.domain.persistence;

import com.itsm.domain.catalog.Category;
import com.itsm.domain.event.DomainEvent;
import com.itsm.domain.sla.SLAPolicy;

import java.util.*;

/**
 * A complete StorageAdapter that keeps records in maps. Used by the tests to prove
 * save → restart → reload works, and as a worked example for Member 3's JDBC version.
 */
public class InMemoryStorage implements StorageAdapter {
    private final Map<String, UserRecord> users = new LinkedHashMap<>();
    private final Map<String, IncidentRecord> incidents = new LinkedHashMap<>();
    private final Map<String, ServiceRecord> services = new LinkedHashMap<>();
    private final Map<String, Category> categories = new LinkedHashMap<>();
    private final Map<String, SLAPolicy> policies = new LinkedHashMap<>();
    private final List<DomainEvent> audit = new ArrayList<>();

    @Override public void saveUser(UserRecord u) { users.put(u.userId(), u); }
    @Override public List<UserRecord> loadUsers() { return List.copyOf(users.values()); }
    @Override public void saveIncident(IncidentRecord i) { incidents.put(i.incidentId(), i); }
    @Override public List<IncidentRecord> loadIncidents() { return List.copyOf(incidents.values()); }
    @Override public void saveService(ServiceRecord s) { services.put(s.serviceId(), s); }
    @Override public List<ServiceRecord> loadServices() { return List.copyOf(services.values()); }
    @Override public void saveAuditEvent(DomainEvent e) { audit.add(e); }
    @Override public List<DomainEvent> loadAuditEvents() { return List.copyOf(audit); }
    @Override public void saveCategory(Category c) { categories.put(c.getName(), c); }
    @Override public List<Category> loadCategories() { return List.copyOf(categories.values()); }
    @Override public void saveSlaPolicy(SLAPolicy p) { policies.put(p.serviceId() + "/" + p.priority(), p); }
    @Override public List<SLAPolicy> loadSlaPolicies() { return List.copyOf(policies.values()); }

    public int incidentCount() { return incidents.size(); }
}
