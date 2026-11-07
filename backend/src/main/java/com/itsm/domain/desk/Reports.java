package com.itsm.domain.desk;

import com.itsm.domain.common.ServiceHealth;
import com.itsm.domain.common.Role;

import java.util.List;
import java.util.Map;

/** Read-only report shapes for dashboards (serialise straight to JSON). */
public final class Reports {
    private Reports() {}

    public record Overview(int totalIncidents, int openIncidents, int criticalOpen, int resolvedIncidents,
                           int slaViolations, double slaCompliancePercent,
                           double meanTimeToAcknowledgeMinutes, double meanTimeToResolveMinutes,
                           Double averageFeedback, Map<String, Long> byStatus, Map<String, Long> byPriority) {}

    public record TechnicianWorkload(String technicianId, String name, int activeIncidents,
                                     int workloadPoints, int maxPoints, int resolved, boolean available) {}

    public record ServiceAnalysis(String serviceId, String serviceName, long totalIncidents,
                                  long openIncidents, ServiceHealth health) {}

    public record MonitorResult(List<String> warnings, List<String> breaches,
                                List<Map.Entry<String, Role>> escalations, List<String> autoClosed) {
        public boolean isQuiet() {
            return warnings.isEmpty() && breaches.isEmpty() && escalations.isEmpty() && autoClosed.isEmpty();
        }
    }
}
