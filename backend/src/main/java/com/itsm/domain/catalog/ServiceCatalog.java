package com.itsm.domain.catalog;

import com.itsm.domain.exception.DependencyCycleException;
import com.itsm.domain.exception.ServiceNotFoundException;
import com.itsm.domain.intelligence.TextSimilarity;

import java.util.*;

/**
 * Holds every IT service and the dependency graph between them.
 *
 * Edge direction: "Payment depends on Database" means a Database failure flows
 * DOWNSTREAM to Payment. Used for:
 *   - root-cause correlation   (walk UPSTREAM from failing services)
 *   - blast radius / what-if   (walk DOWNSTREAM from a failed service)
 */
public class ServiceCatalog {
    private final Map<String, ITService> services = new LinkedHashMap<>();

    public void add(ITService service) { services.put(service.getServiceId(), service); }

    public ITService get(String serviceId) {
        ITService s = services.get(serviceId);
        if (s == null) throw new ServiceNotFoundException("Service '" + serviceId + "' not found.");
        return s;
    }

    public boolean exists(String serviceId) { return services.containsKey(serviceId); }
    public List<ITService> all() { return List.copyOf(services.values()); }

    /** Declare that {@code serviceId} depends on {@code upstreamId}. Rejects cycles. */
    public void addDependency(String serviceId, String upstreamId) {
        ITService service = get(serviceId);
        get(upstreamId);
        if (serviceId.equals(upstreamId)) {
            throw new DependencyCycleException("A service cannot depend on itself.");
        }
        // Adding S -> U creates a cycle if U already (transitively) depends on S.
        if (upstreamOf(upstreamId).contains(serviceId)) {
            throw new DependencyCycleException(String.format(
                "%s already depends on %s; this would create a cycle.", upstreamId, serviceId));
        }
        service.addDependencyUnchecked(upstreamId);
    }

    /** Everything this service needs, directly or indirectly (iterative DFS). */
    public Set<String> upstreamOf(String serviceId) {
        Set<String> seen = new LinkedHashSet<>();
        Deque<String> stack = new ArrayDeque<>(get(serviceId).getDependsOn());
        while (!stack.isEmpty()) {
            String id = stack.pop();
            if (seen.add(id) && services.containsKey(id)) stack.addAll(services.get(id).getDependsOn());
        }
        return seen;
    }

    /** Everything that would be affected if this service failed (BFS, nearest first). */
    public List<String> downstreamOf(String serviceId) {
        get(serviceId);
        List<String> order = new ArrayList<>();
        Set<String> seen = new HashSet<>(Set.of(serviceId));
        Deque<String> queue = new ArrayDeque<>(List.of(serviceId));
        while (!queue.isEmpty()) {
            String current = queue.poll();
            for (ITService s : services.values()) {
                if (s.getDependsOn().contains(current) && seen.add(s.getServiceId())) {
                    order.add(s.getServiceId());
                    queue.add(s.getServiceId());
                }
            }
        }
        return order;
    }

    /** Pick the service whose name/keywords best match free text, or empty. */
    public Optional<ITService> guessService(String text) {
        Set<String> words = TextSimilarity.rawWords(text);
        ITService best = null;
        int bestHits = 0;
        for (ITService s : services.values()) {
            Set<String> vocab = new HashSet<>(TextSimilarity.rawWords(s.getName()));
            vocab.addAll(s.getKeywords());
            vocab.retainAll(words);
            if (vocab.size() > bestHits) {
                best = s;
                bestHits = vocab.size();
            }
        }
        return Optional.ofNullable(best);
    }
}
