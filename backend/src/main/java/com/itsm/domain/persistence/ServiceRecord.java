package com.itsm.domain.persistence;

import com.itsm.domain.catalog.ITService;

import java.util.List;

/** One row of the services table. dependsOn/keywords can be stored with {@link Codec#encodeList}. */
public record ServiceRecord(String serviceId, String name, int businessCriticality, String defaultCategory,
                            List<String> keywords, List<String> dependsOn, String owner) {

    public ServiceRecord {
        keywords = keywords == null ? List.of() : List.copyOf(keywords);
        dependsOn = dependsOn == null ? List.of() : List.copyOf(dependsOn);
    }

    public static ServiceRecord from(ITService s) {
        return new ServiceRecord(s.getServiceId(), s.getName(), s.getBusinessCriticality(), s.getDefaultCategory(),
                List.copyOf(s.getKeywords()), List.copyOf(s.getDependsOn()), s.getOwner());
    }

    /** Builds the service WITHOUT dependencies; the desk adds those once every service exists. */
    public ITService toServiceWithoutDependencies() {
        ITService s = new ITService(serviceId, name, businessCriticality, defaultCategory, keywords.toArray(String[]::new));
        s.setOwner(owner);
        return s;
    }
}
