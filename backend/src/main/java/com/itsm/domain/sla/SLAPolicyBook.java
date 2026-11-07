package com.itsm.domain.sla;

import com.itsm.domain.common.Priority;
import com.itsm.domain.exception.SLAConfigurationException;

import java.time.Duration;
import java.util.HashMap;
import java.util.Map;

/** Finds the applicable SLA: a service-specific policy beats the default one. */
public class SLAPolicyBook {
    private record Key(String serviceId, Priority priority) {}

    private final Map<Key, SLAPolicy> policies = new HashMap<>();

    public void add(SLAPolicy policy) { policies.put(new Key(policy.serviceId(), policy.priority()), policy); }

    public SLAPolicy policyFor(Priority priority, String serviceId) {
        SLAPolicy p = policies.get(new Key(serviceId, priority));
        if (p == null) p = policies.get(new Key(null, priority));
        if (p == null) throw new SLAConfigurationException("No SLA policy configured for " + priority.name() + ".");
        return p;
    }

    /** The exact table from the project brief. */
    public static SLAPolicyBook withDefaults() {
        SLAPolicyBook book = new SLAPolicyBook();
        book.add(SLAPolicy.of(Priority.P1, Duration.ofMinutes(5), Duration.ofMinutes(30)));
        book.add(SLAPolicy.of(Priority.P2, Duration.ofMinutes(15), Duration.ofHours(2)));
        book.add(SLAPolicy.of(Priority.P3, Duration.ofHours(1), Duration.ofHours(8)));
        book.add(SLAPolicy.of(Priority.P4, Duration.ofHours(4), Duration.ofHours(24)));
        return book;
    }
}
