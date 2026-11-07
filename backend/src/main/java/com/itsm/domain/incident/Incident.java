package com.itsm.domain.incident;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.common.*;
import com.itsm.domain.event.DomainEvent;
import com.itsm.domain.exception.InvalidStateTransitionException;
import com.itsm.domain.exception.UnauthorizedOperationException;
import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.persistence.IncidentRecord;
import com.itsm.domain.sla.SLAPolicyBook;
import com.itsm.domain.sla.SLAClock;
import com.itsm.domain.sla.SLAPolicy;
import com.itsm.domain.state.Action;
import com.itsm.domain.state.IncidentState;
import com.itsm.domain.state.States;
import com.itsm.domain.user.Technician;
import com.itsm.domain.user.User;

import java.time.Duration;
import java.time.Instant;
import java.util.function.Function;
import java.util.*;

/**
 * The Incident aggregate: the heart of the domain.
 *
 * Encapsulation: every field is private and there are no setters. State only changes
 * through business methods, each of which
 *   1. checks the actor's permission,
 *   2. asks the current {@link IncidentState} for the next state (State pattern),
 *   3. updates its data,
 *   4. records a {@link DomainEvent} (picked up later by audit + notifications).
 *
 * Composition: an Incident OWNS its notes, resolutions, SLA clock and feedback.
 * Association: it REFERENCES a reporter, a technician and a service, which live on their own.
 */
public class Incident {
    private final String incidentId;
    private final String title;
    private final String description;
    private final User reporter;
    private final ITService service;
    private final Instant createdAt;
    private Impact impact;
    private Urgency urgency;
    private int affectedUsers;

    private IncidentState state = States.NEW;
    private String category;
    private Double categoryConfidence;
    private Priority priority;
    private Map<String, Object> priorityExplanation = Map.of();
    private SLAClock sla;
    private Technician assignee;
    private Technician previousAssignee;
    private String assignmentReason = "";
    private final List<Note> notes = new ArrayList<>();
    private final List<Resolution> resolutions = new ArrayList<>();
    private Instant resolvedAt;
    private Instant closedAt;
    private Feedback feedback;
    private int escalationLevel;
    private Role escalatedTo;
    private final Set<String> relatedIncidents = new TreeSet<>();
    private int reopenCount;
    private final List<DomainEvent> pendingEvents = new ArrayList<>();

    public Incident(String incidentId, String title, String description, User reporter,
                    ITService service, Impact impact, Urgency urgency, int affectedUsers,
                    Instant createdAt) {
        if (title == null || title.strip().length() < 5) {
            throw new ValidationException("Title must be at least 5 characters.");
        }
        if (description == null || description.strip().length() < 10) {
            throw new ValidationException("Description must be at least 10 characters.");
        }
        if (affectedUsers < 1) throw new ValidationException("affectedUsers must be at least 1.");
        this.incidentId = Objects.requireNonNull(incidentId);
        this.title = title.strip();
        this.description = description.strip();
        this.reporter = Objects.requireNonNull(reporter, "reporter");
        this.service = Objects.requireNonNull(service, "service");
        this.impact = Objects.requireNonNull(impact, "impact");
        this.urgency = Objects.requireNonNull(urgency, "urgency");
        this.affectedUsers = affectedUsers;
        this.createdAt = createdAt;
    }

    // ══════════════════════════ read-only accessors ══════════════════════════
    public String getIncidentId() { return incidentId; }
    public String getTitle() { return title; }
    public String getDescription() { return description; }
    public User getReporter() { return reporter; }
    public ITService getService() { return service; }
    public Impact getImpact() { return impact; }
    public Urgency getUrgency() { return urgency; }
    public int getAffectedUsers() { return affectedUsers; }
    public Instant getCreatedAt() { return createdAt; }
    public IncidentState getState() { return state; }
    public String getStatus() { return state.name(); }
    public boolean isOpen() { return state.isOpen(); }
    public String getCategory() { return category; }
    public Priority getPriority() { return priority; }
    public Map<String, Object> getPriorityExplanation() { return priorityExplanation; }
    public SLAClock getSla() { return sla; }
    public Optional<Technician> getAssignee() { return Optional.ofNullable(assignee); }
    public Optional<Technician> getPreviousAssignee() { return Optional.ofNullable(previousAssignee); }
    public String getAssignmentReason() { return assignmentReason; }
    public List<Resolution> getResolutions() { return Collections.unmodifiableList(resolutions); }
    public Optional<Resolution> currentResolution() {
        return resolvedAt == null || resolutions.isEmpty() ? Optional.empty()
                : Optional.of(resolutions.get(resolutions.size() - 1));
    }
    public Instant getResolvedAt() { return resolvedAt; }
    public Instant getClosedAt() { return closedAt; }
    public Optional<Feedback> getFeedback() { return Optional.ofNullable(feedback); }
    public int getEscalationLevel() { return escalationLevel; }
    public Set<String> getRelatedIncidents() { return Collections.unmodifiableSet(relatedIncidents); }
    public int getReopenCount() { return reopenCount; }
    public List<Action> allowedActions() { return state.allowedActions(); }

    public List<Note> getNotes() { return Collections.unmodifiableList(notes); }

    /** Employees never see internal technician notes. */
    public List<Note> visibleNotes(User viewer) {
        boolean staff = viewer.can(Permission.WORK_INCIDENT) || viewer.can(Permission.VIEW_ALL_INCIDENTS);
        return notes.stream().filter(n -> staff || !n.internal()).toList();
    }

    // ══════════════════════════ internal helpers ═════════════════════════════
    private List<String> stakeholders(String... extra) {
        List<String> ids = new ArrayList<>();
        ids.add(reporter.getUserId());
        if (assignee != null) ids.add(assignee.getUserId());
        ids.addAll(Arrays.asList(extra));
        return ids;
    }

    private void emit(EventType type, User actor, Instant now, String text, String prev, String next,
                      List<String> recipients, boolean urgent) {
        pendingEvents.add(new DomainEvent(type, incidentId, actor.getUserId(), now, text, prev, next,
                recipients, urgent || priority == Priority.P1));
    }

    private void emit(EventType type, User actor, Instant now, String text) {
        emit(type, actor, now, text, null, null, List.of(), false);
    }

    /** Ask the current state for the next one (throws if illegal), keep the SLA clock in sync. */
    private void transition(Action action, User actor, Instant now, EventType type,
                            String text, List<String> recipients) {
        IncidentState prev = state;
        state = checkedNext(action);
        if (sla != null) {
            if (state.slaRunning()) sla.resume(now);
            else if (state == States.AWAITING_INFO) sla.pause(now);
        }
        emit(type, actor, now, text, prev.name(), state.name(), recipients, false);
    }

    private IncidentState checkedNext(Action action) {
        if (!state.allows(action)) {
            throw new InvalidStateTransitionException("Cannot " + action.name().toLowerCase().replace('_', ' ')
                + " " + incidentId + " while it is " + state.name() + ". Allowed now: " + allowedActions() + ".");
        }
        return state.next(action);
    }

    private void requireAssigneeOrLead(User actor) {
        boolean isAssignee = assignee != null && assignee.getUserId().equals(actor.getUserId());
        if (!isAssignee && !actor.can(Permission.REASSIGN_INCIDENT)) {
            throw new UnauthorizedOperationException("Only the assigned technician can do this on " + incidentId + ".");
        }
    }

    private void requireReporterOrAdmin(User actor) {
        if (!actor.getUserId().equals(reporter.getUserId()) && !actor.can(Permission.CLOSE_INCIDENT)) {
            throw new UnauthorizedOperationException("Only the reporter or an administrator can do this on " + incidentId + ".");
        }
    }

    private static String requireText(String text, String what) {
        if (text == null || text.isBlank()) throw new ValidationException(what + " cannot be empty.");
        return text.strip();
    }

    /** Hand pending events to the caller (the ServiceDesk publishes them after saving). */
    public List<DomainEvent> pullEvents() {
        List<DomainEvent> out = List.copyOf(pendingEvents);
        pendingEvents.clear();
        return out;
    }

    // ══════════════════════════ lifecycle operations ═════════════════════════
    public void recordCreation(Instant now) {
        emit(EventType.INCIDENT_CREATED, reporter, now,
             "created by " + reporter.role() + " " + reporter.getUserId(),
             null, state.name(), List.of(reporter.getUserId()), false);
    }

    public void classify(String newCategory, User actor, Instant now, Double confidence) {
        String cat = requireText(newCategory, "Category").toUpperCase();
        checkedNext(Action.CLASSIFY);                        // validate before mutating
        category = cat;
        categoryConfidence = confidence;
        String how = confidence == null ? "" : String.format(" (auto-suggested, %.0f%% confidence)", confidence * 100);
        transition(Action.CLASSIFY, actor, now, EventType.INCIDENT_CLASSIFIED,
                   "classified as " + category + how, List.of());
    }

    /** Sets priority and (first time) starts the SLA clock; later calls re-prioritise. */
    public void applyPriority(Priority newPriority, Map<String, Object> explanation, SLAPolicy policy,
                              User actor, Instant now) {
        Priority old = priority;
        priority = Objects.requireNonNull(newPriority);
        priorityExplanation = Collections.unmodifiableMap(new LinkedHashMap<>(explanation));
        if (sla == null) {
            sla = new SLAClock(policy, createdAt);
            emit(EventType.PRIORITY_CALCULATED, actor, now,
                 "priority calculated as " + priority.name() + " (score " + explanation.get("score") + ")");
        } else if (old != priority) {
            sla.reprioritize(policy);
            if (assignee != null) assignee.updatePriority(incidentId, priority);
            emit(EventType.PRIORITY_CHANGED, actor, now, "priority changed " + old.name() + " → " + priority.name(),
                 null, null, stakeholders(), false);
        }
    }

    /** Correct the assessment (e.g. more users turned out to be affected). Caller re-runs priority. */
    public void reassess(Impact newImpact, Urgency newUrgency, Integer newAffectedUsers) {
        if (!isOpen()) throw new ValidationException("Cannot reassess a " + getStatus() + " incident.");
        if (newImpact != null) impact = newImpact;
        if (newUrgency != null) urgency = newUrgency;
        if (newAffectedUsers != null) {
            if (newAffectedUsers < 1) throw new ValidationException("affectedUsers must be at least 1.");
            affectedUsers = newAffectedUsers;
        }
    }

    public void assign(Technician technician, User actor, Instant now, String reason) {
        Objects.requireNonNull(technician, "technician");
        if (priority == null) throw new ValidationException("Priority must be calculated before assignment.");
        if (technician.equals(assignee)) return;                   // already theirs
        checkedNext(Action.ASSIGN);                                 // validate first
        technician.takeIncident(incidentId, priority);              // may throw workload/availability
        if (assignee != null && !assignee.equals(technician)) assignee.releaseIncident(incidentId);
        if (assignee != null) previousAssignee = assignee;
        assignee = technician;
        assignmentReason = reason == null ? "" : reason;
        transition(Action.ASSIGN, actor, now, EventType.INCIDENT_ASSIGNED,
                   "assigned to Technician " + technician.getUserId() + (reason == null || reason.isBlank() ? "" : " — " + reason),
                   List.of(reporter.getUserId(), technician.getUserId()));
    }

    public void acknowledge(User actor, Instant now) {
        actor.require(Permission.WORK_INCIDENT);
        requireAssigneeOrLead(actor);
        transition(Action.ACKNOWLEDGE, actor, now, EventType.STATUS_CHANGED,
                   "acknowledged by " + actor.getUserId(), List.of(reporter.getUserId()));
        if (sla != null) sla.markResponded(now);
    }

    public void startWork(User actor, Instant now) {
        actor.require(Permission.WORK_INCIDENT);
        requireAssigneeOrLead(actor);
        transition(Action.START_WORK, actor, now, EventType.STATUS_CHANGED,
                   "investigation started", List.of(reporter.getUserId()));
    }

    public void addNote(User actor, String text, boolean internal, Instant now) {
        String body = requireText(text, "Note");
        boolean isReporter = actor.getUserId().equals(reporter.getUserId());
        if (internal || !isReporter) actor.require(Permission.WORK_INCIDENT);
        if (!isOpen()) throw new ValidationException("Cannot add notes to a " + getStatus() + " incident.");
        notes.add(new Note(actor.getUserId(), body, now, internal));
        emit(EventType.NOTE_ADDED, actor, now, (internal ? "internal " : "") + "note added by " + actor.getUserId());
    }

    public void requestInfo(User actor, String question, Instant now) {
        actor.require(Permission.REQUEST_INFO);
        requireAssigneeOrLead(actor);
        String q = requireText(question, "Question");
        checkedNext(Action.REQUEST_INFO);
        notes.add(new Note(actor.getUserId(), "QUESTION: " + q, now, false));
        transition(Action.REQUEST_INFO, actor, now, EventType.INFO_REQUESTED,
                   "more information requested (SLA paused): " + q, List.of(reporter.getUserId()));
    }

    public void provideInfo(User actor, String info, Instant now) {
        if (!actor.getUserId().equals(reporter.getUserId())) {
            throw new UnauthorizedOperationException("Only the reporter can answer information requests.");
        }
        String a = requireText(info, "Answer");
        checkedNext(Action.PROVIDE_INFO);
        notes.add(new Note(actor.getUserId(), "ANSWER: " + a, now, false));
        transition(Action.PROVIDE_INFO, actor, now, EventType.INFO_PROVIDED,
                   "reporter provided information (SLA resumed)", stakeholders());
    }

    public void resolve(User actor, String fix, String rootCause, String preventiveAction, Instant now) {
        actor.require(Permission.RESOLVE_INCIDENT);
        requireAssigneeOrLead(actor);
        checkedNext(Action.RESOLVE);
        Resolution r = new Resolution(fix, rootCause, preventiveAction, actor.getUserId(), now);
        resolutions.add(r);
        resolvedAt = now;
        transition(Action.RESOLVE, actor, now, EventType.INCIDENT_RESOLVED,
                   "resolved — root cause: " + r.rootCause(), stakeholders());
        if (sla != null) sla.markResolved(now);
        if (assignee != null) assignee.recordResolution(incidentId, service.getServiceId());
    }

    public void verify(User actor, Instant now) {
        requireReporterOrAdmin(actor);
        transition(Action.VERIFY, actor, now, EventType.STATUS_CHANGED,
                   "resolution verified by " + actor.getUserId(), stakeholders());
    }

    /** The fix did not hold. The previous technician is remembered for sticky reassignment. */
    public void reopen(User actor, String reason, Instant now) {
        requireReporterOrAdmin(actor);
        String why = requireText(reason, "Reopen reason");
        transition(Action.REOPEN, actor, now, EventType.INCIDENT_REOPENED, "reopened: " + why, stakeholders());
        reopenCount++;
        resolvedAt = null;
        if (sla != null) sla.reopen();
        previousAssignee = assignee;   // their workload was already released at resolve time
        assignee = null;
    }

    public void close(User actor, Instant now) {
        requireReporterOrAdmin(actor);
        transition(Action.CLOSE, actor, now, EventType.INCIDENT_CLOSED, "incident CLOSED", stakeholders());
        closedAt = now;
    }

    public void giveFeedback(User actor, int rating, String comment, Instant now) {
        if (!actor.getUserId().equals(reporter.getUserId())) {
            throw new UnauthorizedOperationException("Only the reporter can give feedback.");
        }
        if (isOpen()) throw new ValidationException("Feedback is only allowed after resolution.");
        feedback = new Feedback(rating, comment == null ? "" : comment, now);
        emit(EventType.FEEDBACK_GIVEN, actor, now, "feedback " + rating + "/5 received");
    }

    // ══════════════════════════ automation hooks ═════════════════════════════
    public void linkRelated(String otherId, User actor, Instant now, String why) {
        if (!otherId.equals(incidentId) && relatedIncidents.add(otherId)) {
            emit(EventType.INCIDENT_LINKED, actor, now, "linked to " + otherId + " (" + why + ")");
        }
    }

    public void escalate(int level, Role target, List<String> targetUsers, User actor, Instant now) {
        if (level <= escalationLevel) return;
        escalationLevel = level;
        escalatedTo = target;
        List<String> who = new ArrayList<>(targetUsers);
        who.addAll(stakeholders());
        emit(EventType.INCIDENT_ESCALATED, actor, now,
             "escalated to level " + level + " (" + target + ")", null, null, who, true);
    }

    public void recordSystemEvent(EventType type, String text, User actor, Instant now,
                                  List<String> recipients, boolean urgent) {
        emit(type, actor, now, text, null, null, recipients, urgent);
    }

    // ══════════════════════════ persistence ══════════════════════════════════
    /** Flatten to plain data for the database. */
    public IncidentRecord toRecord() {
        return new IncidentRecord(incidentId, title, description, reporter.getUserId(), service.getServiceId(),
            impact.name(), urgency.name(), affectedUsers, createdAt,
            state.name(), category, categoryConfidence, priority == null ? null : priority.name(),
            priorityExplanation,
            assignee == null ? null : assignee.getUserId(),
            previousAssignee == null ? null : previousAssignee.getUserId(), assignmentReason,
            resolvedAt, closedAt,
            feedback == null ? null : feedback.rating(), feedback == null ? null : feedback.comment(),
            feedback == null ? null : feedback.at(),
            escalationLevel, escalatedTo == null ? null : escalatedTo.name(), List.copyOf(relatedIncidents), reopenCount,
            sla == null ? null : sla.getPausedSince(), sla == null ? 0 : sla.getPausedTotal().toSeconds(),
            sla == null ? null : sla.getRespondedAt(), sla == null ? null : sla.getResolvedAt(),
            sla != null && sla.isResponseBreached(), sla != null && sla.isResolutionBreached(),
            sla != null && sla.isWarningSent(), sla != null && sla.isBreachNotified(),
            notes, resolutions);
    }

    /**
     * Rebuild an incident from saved data. No events are emitted (nothing "happened";
     * we are just reloading). Technician workloads are rebuilt by the ServiceDesk afterwards.
     */
    public static Incident restore(IncidentRecord r, Function<String, User> users,
                                   Function<String, ITService> services, SLAPolicyBook slaBook) {
        Incident i = new Incident(r.incidentId(), r.title(), r.description(), users.apply(r.reporterId()),
            services.apply(r.serviceId()), Impact.valueOf(r.impact()), Urgency.valueOf(r.urgency()),
            r.affectedUsers(), r.createdAt());
        i.state = States.fromName(r.status());
        i.category = r.category();
        i.categoryConfidence = r.categoryConfidence();
        i.priority = r.priority() == null ? null : Priority.valueOf(r.priority());
        i.priorityExplanation = Collections.unmodifiableMap(new LinkedHashMap<>(r.priorityExplanation()));
        if (i.priority != null) {
            i.sla = SLAClock.restore(slaBook.policyFor(i.priority, r.serviceId()), r.createdAt(),
                r.slaPausedSince(), Duration.ofSeconds(r.slaPausedSeconds()), r.slaRespondedAt(), r.slaResolvedAt(),
                r.slaResponseBreached(), r.slaResolutionBreached(), r.slaWarningSent(), r.slaBreachNotified());
        }
        i.assignee = r.assigneeId() == null ? null : (Technician) users.apply(r.assigneeId());
        i.previousAssignee = r.previousAssigneeId() == null ? null : (Technician) users.apply(r.previousAssigneeId());
        i.assignmentReason = r.assignmentReason() == null ? "" : r.assignmentReason();
        i.resolvedAt = r.resolvedAt();
        i.closedAt = r.closedAt();
        i.feedback = r.feedback();
        i.escalationLevel = r.escalationLevel();
        i.escalatedTo = r.escalatedTo() == null ? null : Role.valueOf(r.escalatedTo());
        i.relatedIncidents.addAll(r.relatedIncidents());
        i.reopenCount = r.reopenCount();
        i.notes.addAll(r.notes());
        i.resolutions.addAll(r.resolutions());
        return i;
    }

    // ══════════════════════════ serialization ════════════════════════════════
    /** Flat map for the API/JSON layer. */
    public Map<String, Object> toMap(Instant now) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("incidentId", incidentId);
        m.put("title", title);
        m.put("description", description);
        m.put("reporterId", reporter.getUserId());
        m.put("serviceId", service.getServiceId());
        m.put("serviceName", service.getName());
        m.put("category", category);
        m.put("categoryConfidence", categoryConfidence);
        m.put("impact", impact.name());
        m.put("urgency", urgency.name());
        m.put("affectedUsers", affectedUsers);
        m.put("priority", priority == null ? null : priority.name());
        m.put("priorityExplanation", priorityExplanation);
        m.put("status", state.name());
        m.put("allowedActions", allowedActions().stream().map(Enum::name).toList());
        m.put("assignedTo", assignee == null ? null : assignee.getUserId());
        m.put("assignmentReason", assignmentReason);
        m.put("sla", sla == null ? null : sla.toMap(now));
        m.put("resolution", currentResolution().map(Resolution::description).orElse(null));
        m.put("rootCause", currentResolution().map(Resolution::rootCause).orElse(null));
        m.put("createdAt", TimeFormat.both(createdAt));
        m.put("createdAtIso", createdAt.toString());          // machine-readable, for sorting in the UI
        m.put("resolvedAt", resolvedAt == null ? null : TimeFormat.both(resolvedAt));
        m.put("closedAt", closedAt == null ? null : TimeFormat.both(closedAt));
        m.put("escalationLevel", escalationLevel);
        m.put("escalatedTo", escalatedTo == null ? null : escalatedTo.name());
        m.put("relatedIncidents", List.copyOf(relatedIncidents));
        m.put("reopenCount", reopenCount);
        m.put("feedbackRating", feedback == null ? null : feedback.rating());
        return m;
    }

    @Override
    public String toString() {
        return "Incident[" + incidentId + " " + (priority == null ? "--" : priority.name()) + " "
                + state.name() + " '" + title + "']";
    }
}
