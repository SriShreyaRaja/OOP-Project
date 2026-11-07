package com.itsm.domain.catalog;

import com.itsm.domain.exception.ValidationException;

import java.util.*;

/**
 * An IT service such as "Payment Application".
 * Dependencies are stored as service IDs; the {@link ServiceCatalog} owns the graph
 * so it can reject cycles and compute blast radius.
 */
public class ITService {
    private final String serviceId;
    private final String name;
    private final int businessCriticality;               // 1 (nice-to-have) .. 5 (business-critical)
    private final String defaultCategory;
    private final Set<String> keywords;
    private final Set<String> dependsOn = new LinkedHashSet<>();
    private String owner;

    public ITService(String serviceId, String name, int businessCriticality,
                     String defaultCategory, String... keywords) {
        if (serviceId == null || serviceId.isBlank() || name == null || name.isBlank()) {
            throw new ValidationException("Service id and name are required.");
        }
        if (businessCriticality < 1 || businessCriticality > 5) {
            throw new ValidationException("businessCriticality must be 1..5.");
        }
        this.serviceId = serviceId;
        this.name = name;
        this.businessCriticality = businessCriticality;
        this.defaultCategory = defaultCategory.toUpperCase();
        this.keywords = new HashSet<>();
        for (String k : keywords) this.keywords.add(k.toLowerCase());
        this.owner = "Unassigned";
    }

    public String getServiceId() { return serviceId; }
    public String getName() { return name; }
    public int getBusinessCriticality() { return businessCriticality; }
    public String getDefaultCategory() { return defaultCategory; }
    public Set<String> getKeywords() { return Collections.unmodifiableSet(keywords); }
    public Set<String> getDependsOn() { return Collections.unmodifiableSet(dependsOn); }
    public String getOwner() { return owner; }
    public void setOwner(String owner) { this.owner = owner; }

    /** Package-private: only the catalog may add edges (it checks for cycles first). */
    void addDependencyUnchecked(String upstreamId) { dependsOn.add(upstreamId); }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("serviceId", serviceId);
        m.put("name", name);
        m.put("businessCriticality", businessCriticality);
        m.put("defaultCategory", defaultCategory);
        m.put("dependsOn", List.copyOf(dependsOn));
        m.put("owner", owner);
        return m;
    }

    @Override public String toString() { return name + " (" + serviceId + ")"; }
}
