package com.itsm.domain.intelligence;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.catalog.ServiceCatalog;

import java.util.List;

/**
 * "What if this service failed?" Read-only blast-radius analysis over the dependency graph.
 * Lets an IT manager see business exposure before maintenance or during an outage.
 */
public class WhatIfSimulator {
    public record BlastRadius(String failedServiceId, String failedServiceName,
                              List<String> impactedServiceNames, int impactedCount,
                              int businessCriticalImpacted, int exposureScore) {}

    private final ServiceCatalog catalog;

    public WhatIfSimulator(ServiceCatalog catalog) { this.catalog = catalog; }

    public BlastRadius simulateFailure(String serviceId) {
        ITService failed = catalog.get(serviceId);
        List<ITService> impacted = catalog.downstreamOf(serviceId).stream().map(catalog::get).toList();
        int critical = (int) impacted.stream().filter(s -> s.getBusinessCriticality() >= 5).count();
        int exposure = failed.getBusinessCriticality()
                + impacted.stream().mapToInt(ITService::getBusinessCriticality).sum();
        return new BlastRadius(serviceId, failed.getName(),
                impacted.stream().map(ITService::getName).toList(), impacted.size(), critical, exposure);
    }
}
