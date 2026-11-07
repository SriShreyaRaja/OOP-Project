package com.itsm.domain.desk;

import com.itsm.domain.incident.Incident;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;

/**
 * Search/filter with 12 criteria, combined with AND. BUILDER + composed predicates:
 * <pre>
 *   SearchCriteria.where().priority("P1").category("NETWORK").openOnly()
 * </pre>
 * Each method adds one Predicate; unset criteria simply aren't added.
 */
public final class SearchCriteria {
    private final List<Predicate<Incident>> filters = new ArrayList<>();
    private String slaStatus;

    private SearchCriteria() {}

    public static SearchCriteria where() { return new SearchCriteria(); }

    private SearchCriteria add(Predicate<Incident> p) { filters.add(p); return this; }

    public SearchCriteria incidentId(String id) { return add(i -> i.getIncidentId().equalsIgnoreCase(id)); }
    public SearchCriteria status(String s) { return add(i -> i.getStatus().equalsIgnoreCase(s)); }
    public SearchCriteria priority(String p) { return add(i -> i.getPriority() != null && i.getPriority().name().equalsIgnoreCase(p)); }
    public SearchCriteria category(String c) { return add(i -> c.equalsIgnoreCase(i.getCategory())); }
    public SearchCriteria service(String sid) { return add(i -> i.getService().getServiceId().equals(sid)); }
    public SearchCriteria technician(String tid) {
        return add(i -> i.getAssignee().map(t -> t.getUserId().equals(tid)).orElse(false));
    }
    public SearchCriteria reporter(String uid) { return add(i -> i.getReporter().getUserId().equals(uid)); }
    public SearchCriteria createdFrom(Instant t) { return add(i -> !i.getCreatedAt().isBefore(t)); }
    public SearchCriteria createdTo(Instant t) { return add(i -> !i.getCreatedAt().isAfter(t)); }
    public SearchCriteria text(String q) {
        String needle = q.toLowerCase();
        return add(i -> (i.getTitle() + " " + i.getDescription()).toLowerCase().contains(needle));
    }
    public SearchCriteria openOnly() { return add(Incident::isOpen); }
    public SearchCriteria escalated() { return add(i -> i.getEscalationLevel() > 0); }

    /** SLA status depends on "now", so the desk evaluates it at search time. */
    public SearchCriteria slaStatus(String status) { this.slaStatus = status; return this; }

    Predicate<Incident> toPredicate(Instant now) {
        Predicate<Incident> p = i -> true;
        for (Predicate<Incident> f : filters) p = p.and(f);
        if (slaStatus != null) {
            p = p.and(i -> i.getSla() != null && i.getSla().status(now).name().equalsIgnoreCase(slaStatus));
        }
        return p;
    }
}
