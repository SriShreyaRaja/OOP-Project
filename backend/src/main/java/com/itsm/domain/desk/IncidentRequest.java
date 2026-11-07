package com.itsm.domain.desk;

import java.util.Objects;

/**
 * What a user submits when reporting an incident. Built with a fluent BUILDER so
 * callers only set what they know:
 * <pre>
 *   IncidentRequest.builder("Payment down", "Users cannot pay…")
 *       .impact("ORGANIZATION").urgency("CRITICAL").affectedUsers(600).build();
 * </pre>
 */
public record IncidentRequest(String title, String description, String serviceId, String impact,
                              String urgency, int affectedUsers, String category,
                              boolean blockDuplicates, boolean autoAssign) {

    public static Builder builder(String title, String description) { return new Builder(title, description); }

    public static final class Builder {
        private final String title, description;
        private String serviceId, category;
        private String impact = "MEDIUM", urgency = "MEDIUM";
        private int affectedUsers = 1;
        private boolean blockDuplicates, autoAssign = true;

        private Builder(String title, String description) {
            this.title = title;
            this.description = description;
        }

        public Builder service(String id) { this.serviceId = id; return this; }
        public Builder impact(String v) { this.impact = Objects.requireNonNull(v); return this; }
        public Builder urgency(String v) { this.urgency = Objects.requireNonNull(v); return this; }
        public Builder affectedUsers(int n) { this.affectedUsers = n; return this; }
        public Builder category(String c) { this.category = c; return this; }
        public Builder blockDuplicates() { this.blockDuplicates = true; return this; }
        public Builder manualAssignment() { this.autoAssign = false; return this; }

        public IncidentRequest build() {
            return new IncidentRequest(title, description, serviceId, impact, urgency, affectedUsers,
                                       category, blockDuplicates, autoAssign);
        }
    }
}
