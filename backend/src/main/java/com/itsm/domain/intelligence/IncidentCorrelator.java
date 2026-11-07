package com.itsm.domain.intelligence;

import com.itsm.domain.catalog.ServiceCatalog;
import com.itsm.domain.incident.Incident;

import java.util.*;

/**
 * Intelligent Feature B: Incident Correlation / root-cause hint.
 *
 * If several open incidents hit services that all depend on the same upstream service,
 * that service is the likely root cause. Ranking: covers the most incidents, then a
 * service that is itself reported broken, then the most fundamental (fewest dependencies).
 */
public class IncidentCorrelator {
    public record Correlation(String suspectedRootServiceId, String serviceName,
                              List<String> incidentIds, int directReports, String explanation) {}

    private final ServiceCatalog catalog;
    private final int minIncidents;

    public IncidentCorrelator(ServiceCatalog catalog, int minIncidents) {
        this.catalog = catalog;
        this.minIncidents = minIncidents;
    }

    public List<Correlation> correlate(List<Incident> openIncidents) {
        Map<String, SortedSet<String>> byUpstream = new HashMap<>();
        Map<String, Integer> direct = new HashMap<>();
        for (Incident inc : openIncidents) {
            String sid = inc.getService().getServiceId();
            direct.merge(sid, 1, Integer::sum);
            Set<String> roots = new HashSet<>(catalog.upstreamOf(sid));
            roots.add(sid);
            for (String up : roots) byUpstream.computeIfAbsent(up, k -> new TreeSet<>()).add(inc.getIncidentId());
        }
        List<Correlation> out = new ArrayList<>();
        byUpstream.forEach((up, ids) -> {
            if (ids.size() < minIncidents) return;
            int d = direct.getOrDefault(up, 0);
            String name = catalog.get(up).getName();
            out.add(new Correlation(up, name, List.copyOf(ids), d,
                ids.size() + " open incidents share a dependency on " + name
                    + (d > 0 ? " (" + d + " reported directly on it)" : "")));
        });
        out.sort(Comparator.<Correlation>comparingInt(c -> -c.incidentIds().size())
            .thenComparingInt(c -> -c.directReports())
            .thenComparingInt(c -> catalog.upstreamOf(c.suspectedRootServiceId()).size())
            .thenComparing(Correlation::suspectedRootServiceId));
        return out;
    }
}
