package com.itsm.domain.persistence;

import com.itsm.domain.incident.Feedback;
import com.itsm.domain.incident.Note;
import com.itsm.domain.incident.Resolution;

import java.time.Instant;
import java.util.List;
import java.util.Map;

/**
 * Plain data version of an Incident: every field is a String, number, boolean, Instant or a
 * list of simple records, so it maps directly onto database tables.
 *
 * Member 3: save {@code incident.toRecord()} and rebuild with {@code desk.restoreIncident(record)}.
 *
 * Suggested tables (see docs/DATABASE_DESIGN.md):
 *   incidents(...one column per scalar field below...)
 *   incident_notes(incident_id FK, author_id, text, at, internal)
 *   incident_resolutions(incident_id FK, description, root_cause, preventive_action, technician_id, at)
 */
public record IncidentRecord(
        String incidentId, String title, String description, String reporterId, String serviceId,
        String impact, String urgency, int affectedUsers, Instant createdAt,
        String status, String category, Double categoryConfidence, String priority,
        Map<String, Object> priorityExplanation,
        String assigneeId, String previousAssigneeId, String assignmentReason,
        Instant resolvedAt, Instant closedAt,
        Integer feedbackRating, String feedbackComment, Instant feedbackAt,
        int escalationLevel, String escalatedTo, List<String> relatedIncidents, int reopenCount,
        // SLA clock
        Instant slaPausedSince, long slaPausedSeconds, Instant slaRespondedAt, Instant slaResolvedAt,
        boolean slaResponseBreached, boolean slaResolutionBreached, boolean slaWarningSent, boolean slaBreachNotified,
        // child rows
        List<Note> notes, List<Resolution> resolutions) {

    public IncidentRecord {
        priorityExplanation = priorityExplanation == null ? Map.of() : priorityExplanation;
        relatedIncidents = relatedIncidents == null ? List.of() : List.copyOf(relatedIncidents);
        notes = notes == null ? List.of() : List.copyOf(notes);
        resolutions = resolutions == null ? List.of() : List.copyOf(resolutions);
    }

    public Feedback feedback() {
        return feedbackRating == null ? null : new Feedback(feedbackRating, feedbackComment, feedbackAt);
    }
}
