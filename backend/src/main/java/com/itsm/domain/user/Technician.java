package com.itsm.domain.user;

import com.itsm.domain.common.Permission;
import com.itsm.domain.common.Priority;
import com.itsm.domain.common.Role;
import com.itsm.domain.exception.TechnicianUnavailableException;
import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.exception.WorkloadExceededException;

import java.util.*;

/**
 * A support engineer.
 *
 * Workload is measured in POINTS, not incident count: a P1 costs 8 points, a P4
 * costs 1 (see {@link Priority#workloadPoints()}). Ten printer jams are not the
 * same load as one payment outage.
 */
public class Technician extends User {
    private static final Set<Permission> PERMS = EnumSet.of(
        Permission.REPORT_INCIDENT, Permission.VIEW_OWN_INCIDENTS, Permission.WORK_INCIDENT,
        Permission.RESOLVE_INCIDENT, Permission.REQUEST_INFO);

    private final Map<String, Integer> skills = new HashMap<>();          // CATEGORY -> 1..5
    private final Map<String, Priority> activeIncidents = new LinkedHashMap<>();
    private final Map<String, Integer> serviceHistory = new HashMap<>();  // serviceId -> resolved count
    private final int maxWorkloadPoints;
    private final double yearsExperience;
    private boolean available = true;
    private int resolvedCount;

    public Technician(String userId, String name, String email, String password,
                      Map<String, Integer> skills, int maxWorkloadPoints, double yearsExperience) {
        this(userId, name, email, PasswordHash.of(password), skills, maxWorkloadPoints, yearsExperience);
    }

    public Technician(String userId, String name, String email, PasswordHash hash,
                      Map<String, Integer> skills, int maxWorkloadPoints, double yearsExperience) {
        super(userId, name, email, hash);
        if (maxWorkloadPoints < Priority.P1.workloadPoints()) {
            throw new ValidationException("maxWorkloadPoints must allow at least one P1 incident.");
        }
        if (yearsExperience < 0) throw new ValidationException("Experience cannot be negative.");
        this.maxWorkloadPoints = maxWorkloadPoints;
        this.yearsExperience = yearsExperience;
        if (skills != null) skills.forEach((cat, lvl) -> this.skills.put(cat.toUpperCase(), checkLevel(lvl)));
    }

    private static int checkLevel(int level) {
        if (level < 1 || level > 5) throw new ValidationException("Skill level must be 1..5.");
        return level;
    }

    public void setSkill(String category, int level) {
        skills.put(category.toUpperCase(), checkLevel(level));
    }

    public int skillLevel(String category) {
        return category == null ? 0 : skills.getOrDefault(category.toUpperCase(), 0);
    }

    public Map<String, Integer> getSkills() { return Collections.unmodifiableMap(skills); }

    // ---- workload -----------------------------------------------------------------
    public int workloadPoints() {
        return activeIncidents.values().stream().mapToInt(Priority::workloadPoints).sum();
    }

    public int activeCount() { return activeIncidents.size(); }
    public int getMaxWorkloadPoints() { return maxWorkloadPoints; }
    public double loadRatio() { return (double) workloadPoints() / maxWorkloadPoints; }
    public double getYearsExperience() { return yearsExperience; }
    public int getResolvedCount() { return resolvedCount; }
    public Set<String> activeIncidentIds() { return Collections.unmodifiableSet(activeIncidents.keySet()); }

    public boolean isAvailable() { return isActive() && available; }
    public void setAvailable(boolean available) { this.available = available; }

    /** Can this technician absorb an incident of this priority right now? */
    public boolean hasCapacityFor(Priority priority) {
        return isAvailable() && workloadPoints() + priority.workloadPoints() <= maxWorkloadPoints;
    }

    public void takeIncident(String incidentId, Priority priority) {
        if (!isAvailable()) {
            throw new TechnicianUnavailableException("Technician " + getUserId() + " is unavailable.");
        }
        if (activeIncidents.containsKey(incidentId)) return;
        if (!hasCapacityFor(priority)) {
            throw new WorkloadExceededException(String.format(
                "Technician %s has %d/%d points; a %s needs %d more.",
                getUserId(), workloadPoints(), maxWorkloadPoints, priority.name(), priority.workloadPoints()));
        }
        activeIncidents.put(incidentId, priority);
    }

    /** Keeps points accurate if an assigned incident is re-prioritised. */
    public void updatePriority(String incidentId, Priority priority) {
        activeIncidents.computeIfPresent(incidentId, (k, v) -> priority);
    }

    public void releaseIncident(String incidentId) {
        activeIncidents.remove(incidentId);
    }

    public void recordResolution(String incidentId, String serviceId) {
        releaseIncident(incidentId);
        resolvedCount++;
        serviceHistory.merge(serviceId, 1, Integer::sum);
    }

    /** Replace all skills at once (admin "manage technicians"). */
    public void replaceSkills(Map<String, Integer> newSkills) {
        Map<String, Integer> checked = new HashMap<>();
        newSkills.forEach((cat, lvl) -> checked.put(cat.toUpperCase(), checkLevel(lvl)));
        skills.clear();
        skills.putAll(checked);
    }

    /** Persistence: rebuild derived stats from saved incidents after a restart. */
    public void restoreHistory(int resolved, Map<String, Integer> history) {
        resolvedCount = resolved;
        serviceHistory.clear();
        serviceHistory.putAll(history);
    }

    /** Persistence: re-attach an open incident after a restart (no capacity check — it was already accepted). */
    public void restoreWorkload(String incidentId, Priority priority) {
        activeIncidents.put(incidentId, priority);
    }

    public Map<String, Integer> getServiceHistory() { return Collections.unmodifiableMap(serviceHistory); }

    public int experienceWith(String serviceId) { return serviceHistory.getOrDefault(serviceId, 0); }

    @Override public Role role() { return Role.TECHNICIAN; }
    @Override public Set<Permission> permissions() { return PERMS; }

    @Override
    public Map<String, Object> toMap() {
        Map<String, Object> m = super.toMap();
        m.put("skills", getSkills());
        m.put("workloadPoints", workloadPoints());
        m.put("maxWorkloadPoints", maxWorkloadPoints);
        m.put("activeIncidents", activeCount());
        m.put("available", isAvailable());
        m.put("yearsExperience", yearsExperience);
        m.put("resolvedCount", resolvedCount);
        return m;
    }
}
