package com.itsm.domain.desk;

import com.itsm.domain.assignment.AssignmentStrategies;
import com.itsm.domain.assignment.AssignmentStrategy;
import com.itsm.domain.assignment.Candidate;
import com.itsm.domain.assignment.SmartRecommendationAssignment;
import com.itsm.domain.catalog.Category;
import com.itsm.domain.catalog.CategoryRegistry;
import com.itsm.domain.catalog.ITService;
import com.itsm.domain.catalog.ServiceCatalog;
import com.itsm.domain.common.*;
import com.itsm.domain.event.AuditLog;
import com.itsm.domain.event.DomainEvent;
import com.itsm.domain.event.EventBus;
import com.itsm.domain.event.EventObserver;
import com.itsm.domain.exception.*;
import com.itsm.domain.factory.IncidentFactory;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.intelligence.*;
import com.itsm.domain.notification.EmailChannel;
import com.itsm.domain.notification.InAppChannel;
import com.itsm.domain.notification.Notification;
import com.itsm.domain.notification.NotificationChannel;
import com.itsm.domain.notification.NotificationService;
import com.itsm.domain.priority.PriorityResult;
import com.itsm.domain.priority.PriorityStrategies;
import com.itsm.domain.priority.PriorityStrategy;
import com.itsm.domain.priority.WeightedScorePriorityStrategy;
import com.itsm.domain.persistence.IncidentRecord;
import com.itsm.domain.persistence.ServiceRecord;
import com.itsm.domain.persistence.StorageAdapter;
import com.itsm.domain.persistence.UserRecord;
import com.itsm.domain.repository.*;
import com.itsm.domain.sla.SLAClock;
import com.itsm.domain.sla.SLAPolicy;
import com.itsm.domain.sla.SLAPolicyBook;
import com.itsm.domain.escalation.EscalationPolicy;
import com.itsm.domain.user.SystemAccount;
import com.itsm.domain.user.Technician;
import com.itsm.domain.user.User;

import java.time.Duration;
import java.time.Instant;
import java.util.*;
import java.util.function.BiConsumer;
import java.util.stream.Collectors;

/**
 * FACADE: the single entry point into the domain.
 *
 * Thread-safe: every public method is synchronized, so a web server handling many requests
 * at once can share one ServiceDesk safely. (Simple and correct; fine for this scale.)
 *
 * Member 3's REST controllers should call ONLY public methods of this class, e.g.
 * <pre>
 *   &#64;PostMapping("/incidents")
 *   Map&lt;String,Object&gt; report(&#64;RequestBody ReportDto dto, User user) {
 *       return desk.reportIncident(user, dto.toRequest()).toMap(desk.now());
 *   }
 * </pre>
 * {@link #reportIncident} runs the full 14-step scenario from the project brief.
 */
public class ServiceDesk {
    private final Clock clock;
    private final ServiceCatalog catalog = new ServiceCatalog();
    private final CategoryRegistry categories = CategoryRegistry.withDefaults();
    private final SLAPolicyBook slaBook = SLAPolicyBook.withDefaults();
    private final IncidentRepository incidents;
    private final UserRepository users;
    private final SystemAccount system = new SystemAccount();
    private final IncidentFactory factory;

    private PriorityStrategy priorityStrategy = new WeightedScorePriorityStrategy();
    private AssignmentStrategy assignmentStrategy = new SmartRecommendationAssignment();
    private DuplicateDetector duplicateDetector = new KeywordDuplicateDetector();
    private final EscalationPolicy escalation = new EscalationPolicy();
    private final IncidentCorrelator correlator;
    private final SLARiskAnalyzer riskAnalyzer = new SLARiskAnalyzer();
    private final ResolutionSuggester resolutionSuggester = new ResolutionSuggester();
    private final WhatIfSimulator whatIf;

    private StorageAdapter storage = StorageAdapter.NONE;
    private Duration autoCloseAfter = Duration.ofHours(72);
    private final Map<String, Deque<Instant>> failedLogins = new HashMap<>();
    private static final int MAX_FAILED_LOGINS = 5;
    private static final Duration LOCKOUT_WINDOW = Duration.ofMinutes(15);

    private final EventBus bus = new EventBus();
    private final AuditLog audit = new AuditLog();
    private final NotificationService notifier;

    public ServiceDesk(Clock clock, IncidentRepository incidents, UserRepository users) {
        this.clock = clock;
        this.incidents = incidents;
        this.users = users;
        this.factory = new IncidentFactory(catalog, clock, 1001);
        this.correlator = new IncidentCorrelator(catalog, 2);
        this.whatIf = new WhatIfSimulator(catalog);
        this.notifier = new NotificationService(this::lookupUser);
        notifier.registerChannel(new InAppChannel());
        notifier.registerChannel(new EmailChannel());
        bus.subscribe(audit);       // Observer #1: audit trail
        bus.subscribe(notifier);    // Observer #2: notifications
    }

    public ServiceDesk(Clock clock) {
        this(clock, new InMemoryIncidentRepository(), new InMemoryUserRepository());
    }

    // ═════════════════════════════ infrastructure ══════════════════════════════
    public synchronized Instant now() { return clock.now(); }
    public synchronized ServiceCatalog catalog() { return catalog; }
    public synchronized CategoryRegistry categories() { return categories; }
    public synchronized AuditLog audit() { return audit; }
    public synchronized IncidentFactory factory() { return factory; }
    public synchronized AssignmentStrategy assignmentStrategy() { return assignmentStrategy; }
    public synchronized PriorityStrategy priorityStrategy() { return priorityStrategy; }

    /** Extra observers, e.g. Member 3's database audit writer or a WebSocket pusher. */
    public synchronized void subscribe(EventObserver observer) { bus.subscribe(observer); }
    public synchronized void addNotificationChannel(NotificationChannel channel) { notifier.registerChannel(channel); }
    public synchronized <T extends NotificationChannel> T channel(String name, Class<T> type) { return notifier.channel(name, type); }
    public synchronized void setDuplicateDetector(DuplicateDetector detector) { this.duplicateDetector = Objects.requireNonNull(detector); }

    private Optional<User> lookupUser(String id) {
        return SystemAccount.ID.equals(id) ? Optional.of(system) : users.findById(id);
    }

    public synchronized User user(String id) {
        return lookupUser(id).orElseThrow(() -> new UserNotFoundException("User '" + id + "' not found."));
    }

    // ═════════════════════════════ persistence ═════════════════════════════════
    /**
     * Connect a database (Member 3's StorageAdapter) and reload everything saved in it.
     * Call once at startup, before handling requests. From then on every change is saved
     * automatically (write-through). Order matters: SLA → categories → services → users →
     * incidents → technician workloads → audit history.
     */
    public synchronized void attachStorage(StorageAdapter adapter) {
        this.storage = Objects.requireNonNull(adapter);
        adapter.loadSlaPolicies().forEach(slaBook::add);
        adapter.loadCategories().forEach(categories::register);

        List<ServiceRecord> services = adapter.loadServices();
        services.forEach(r -> catalog.add(r.toServiceWithoutDependencies()));
        services.forEach(r -> r.dependsOn().forEach(up -> catalog.addDependency(r.serviceId(), up)));

        adapter.loadUsers().forEach(r -> users.save(r.toUser()));

        for (IncidentRecord r : adapter.loadIncidents()) {
            Incident inc = Incident.restore(r, this::user, catalog::get, slaBook);
            incidents.save(inc);
            factory.continueAfter(inc.getIncidentId());
        }
        rebuildTechnicianStats();
        audit.restore(adapter.loadAuditEvents());
        bus.subscribe(adapter::saveAuditEvent);        // keep the audit trail flowing to the DB
    }

    /** Workload and history are derived from incidents, so they never drift out of sync. */
    private void rebuildTechnicianStats() {
        for (Technician t : users.technicians()) {
            Map<String, Integer> history = new HashMap<>();
            int resolved = 0;
            for (Incident i : incidents.findAll()) {
                for (var r : i.getResolutions()) {
                    if (r.technicianId().equals(t.getUserId())) {
                        resolved++;
                        history.merge(i.getService().getServiceId(), 1, Integer::sum);
                    }
                }
            }
            t.restoreHistory(resolved, history);
        }
        for (Incident i : incidents.findAll()) {
            if (i.isOpen()) i.getAssignee().ifPresent(t -> t.restoreWorkload(i.getIncidentId(), i.getPriority()));
        }
    }

    /** True when nothing has been set up yet (use it to decide whether to seed sample data). */
    public synchronized boolean isEmpty() { return users.findAll().isEmpty(); }

    private void persist(User u) { storage.saveUser(UserRecord.from(u)); }

    private Incident find(String id) {
        return incidents.findById(id).orElseThrow(() -> new IncidentNotFoundException("Incident '" + id + "' not found."));
    }

    /** Save, then publish pending events, so observers always see persisted state. */
    private Incident commit(Incident incident) {
        incidents.save(incident);
        storage.saveIncident(incident.toRecord());
        for (DomainEvent e : incident.pullEvents()) bus.publish(e);
        return incident;
    }

    private List<String> idsOf(Role... roles) {
        List<String> ids = new ArrayList<>();
        for (Role r : roles) users.byRole(r).forEach(u -> ids.add(u.getUserId()));
        return ids;
    }

    // ═════════════════════════════ authentication ══════════════════════════════
    /**
     * Same error for "no such user" and "wrong password" (doesn't reveal which emails exist).
     * After 5 failures in 15 minutes the account is temporarily locked (brute-force protection).
     */
    public synchronized User login(String email, String password) {
        String key = email == null ? "" : email.trim().toLowerCase();
        Instant now = now();
        Deque<Instant> fails = failedLogins.computeIfAbsent(key, k -> new ArrayDeque<>());
        while (!fails.isEmpty() && fails.peekFirst().isBefore(now.minus(LOCKOUT_WINDOW))) fails.pollFirst();
        if (fails.size() >= MAX_FAILED_LOGINS) {
            throw new AuthenticationException("Too many failed attempts. Try again in 15 minutes.");
        }
        Optional<User> user = users.findByEmail(key).filter(u -> u.checkPassword(password));
        if (user.isEmpty()) {
            fails.addLast(now);
            throw new AuthenticationException("Invalid email or password.");
        }
        fails.clear();
        return user.get();
    }

    public synchronized void changePassword(User user, String oldPassword, String newPassword) {
        user.changePassword(oldPassword, newPassword);
        persist(user);
    }

    // ═════════════════════════════ administration ══════════════════════════════
    public synchronized User registerUser(User admin, User newUser) {
        admin.require(Permission.MANAGE_USERS);
        if (users.findById(newUser.getUserId()).isPresent()) {
            throw new ValidationException("User id " + newUser.getUserId() + " already exists.");
        }
        if (users.findByEmail(newUser.getEmail()).isPresent()) {
            throw new ValidationException("Email " + newUser.getEmail() + " is already registered.");
        }
        users.save(newUser);
        persist(newUser);
        return newUser;
    }

    /** First-run setup: create the initial administrator when no users exist yet. */
    public synchronized void registerUserBootstrap(User firstAdmin) {
        if (!users.findAll().isEmpty()) throw new UnauthorizedOperationException("Bootstrap is only allowed on an empty system.");
        firstAdmin.require(Permission.MANAGE_USERS);
        users.save(firstAdmin);
        persist(firstAdmin);
    }

    public synchronized void deactivateUser(User admin, String userId) {
        admin.require(Permission.MANAGE_USERS);
        User u = user(userId);
        if (u.equals(admin)) throw new ValidationException("You cannot deactivate your own account.");
        u.deactivate();
        persist(u);
    }

    /** Admin "manage technicians": replace a technician's skills. */
    public synchronized void updateTechnicianSkills(User admin, String technicianId, Map<String, Integer> skills) {
        admin.require(Permission.MANAGE_USERS);
        Technician t = technician(technicianId);
        t.replaceSkills(skills);
        persist(t);
    }

    /** A technician can mark themselves away/back; admins and team leads can do it for anyone. */
    public synchronized void setAvailability(User actor, String technicianId, boolean available) {
        Technician t = technician(technicianId);
        if (!actor.equals(t) && !actor.can(Permission.MANAGE_USERS) && !actor.can(Permission.REASSIGN_INCIDENT)) {
            throw new UnauthorizedOperationException("You cannot change " + technicianId + "'s availability.");
        }
        t.setAvailable(available);
        persist(t);
    }

    private Technician technician(String id) {
        if (user(id) instanceof Technician t) return t;
        throw new ValidationException(id + " is not a technician.");
    }

    public synchronized void addService(User admin, ITService service) {
        admin.require(Permission.MANAGE_SERVICES);
        catalog.add(service);
        storage.saveService(ServiceRecord.from(service));
    }

    public synchronized void addDependency(User admin, String serviceId, String dependsOnId) {
        admin.require(Permission.MANAGE_SERVICES);
        catalog.addDependency(serviceId, dependsOnId);
        storage.saveService(ServiceRecord.from(catalog.get(serviceId)));
    }

    public synchronized void addCategory(User admin, String name, Set<String> keywords, String description) {
        admin.require(Permission.CONFIGURE_CATEGORIES);
        Category c = new Category(name, description, keywords);
        categories.register(c);
        storage.saveCategory(c);
    }

    public synchronized void configureSla(User admin, SLAPolicy policy) {
        admin.require(Permission.CONFIGURE_SLA);
        slaBook.add(policy);
        storage.saveSlaPolicy(policy);
    }

    public synchronized void configureEscalation(User admin, Priority p, int teamLeadMin, int sysAdminMin, int managerMin) {
        admin.require(Permission.CONFIGURE_SLA);
        escalation.configure(p, teamLeadMin, sysAdminMin, managerMin);
    }

    /** Resolved incidents the reporter never verifies are closed automatically after this long. */
    public synchronized void setAutoCloseAfter(User admin, Duration after) {
        admin.require(Permission.CONFIGURE_SLA);
        if (after.isNegative() || after.isZero()) throw new ValidationException("Auto-close period must be positive.");
        autoCloseAfter = after;
    }

    public synchronized void setAssignmentStrategy(User admin, String name) {
        admin.require(Permission.CONFIGURE_STRATEGY);
        assignmentStrategy = AssignmentStrategies.byName(name);
    }

    public synchronized void setAssignmentStrategy(User admin, AssignmentStrategy strategy) {
        admin.require(Permission.CONFIGURE_STRATEGY);
        assignmentStrategy = Objects.requireNonNull(strategy);
    }

    public synchronized void setPriorityStrategy(User admin, String name) {
        admin.require(Permission.CONFIGURE_STRATEGY);
        priorityStrategy = PriorityStrategies.byName(name);
    }

    // ═════════════════════════════ main workflow ═══════════════════════════════
    /**
     * The 14-step scenario: create → classify → identify service → business impact →
     * priority → SLA → find technicians → assign → notify → (track) → (monitor SLA) →
     * record everything → (close) → (reports).
     */
    public synchronized Incident reportIncident(User reporter, IncidentRequest req) {
        reporter.require(Permission.REPORT_INCIDENT);
        Instant now = now();

        // Validate a user-chosen category BEFORE consuming an ID
        if (req.category() != null) categories.get(req.category());

        // Steps 1, 3, 4: create; affected service given or guessed; impact captured
        Incident inc = factory.create(reporter, req.title(), req.description(), req.serviceId(),
                                      req.impact(), req.urgency(), req.affectedUsers());

        // Duplicate check before spending a technician on it
        List<DuplicateDetector.Match> dupes = duplicateDetector.findDuplicates(inc, incidents.findOpen());
        if (!dupes.isEmpty() && req.blockDuplicates()) {
            factory.discard(inc.getIncidentId());
            throw new DuplicateIncidentException(dupes.get(0).incidentId(), dupes.get(0).score());
        }
        inc.recordCreation(now);

        // Step 2: classify (user's choice → auto-suggestion → service default)
        if (req.category() != null) {
            inc.classify(req.category(), reporter, now, null);
        } else {
            Optional<CategoryRegistry.Suggestion> s = categories.suggest(req.title() + " " + req.description());
            if (s.isPresent()) inc.classify(s.get().category(), system, now, s.get().confidence());
            else inc.classify(inc.getService().getDefaultCategory(), system, now, null);
        }

        // Steps 5, 6: priority + SLA
        applyPriority(inc, now);

        // Link likely duplicates both ways
        for (DuplicateDetector.Match d : dupes) {
            inc.linkRelated(d.incidentId(), system, now, "possible duplicate, " + d.reason() + " " + d.score());
            Incident other = find(d.incidentId());
            other.linkRelated(inc.getIncidentId(), system, now, "possible duplicate");
            commit(other);
        }

        // Steps 7, 8, 9: find technician, assign, notify (via events)
        if (req.autoAssign()) {
            try {
                autoAssign(inc, now);
            } catch (TechnicianUnavailableException e) {
                inc.recordSystemEvent(EventType.SYSTEM_NOTICE, "auto-assignment failed: " + e.getMessage(),
                                      system, now, idsOf(Role.TEAM_LEAD), true);
            }
        }
        return commit(inc);   // step 12: every step above is now in the audit trail
    }

    private void applyPriority(Incident inc, Instant now) {
        PriorityResult r = priorityStrategy.calculate(inc.getImpact(), inc.getUrgency(),
                                                      inc.getService(), inc.getAffectedUsers());
        SLAPolicy policy = slaBook.policyFor(r.priority(), inc.getService().getServiceId());
        inc.applyPriority(r.priority(), r.explanation(), policy, system, now);
    }

    private void autoAssign(Incident inc, Instant now) {
        Candidate c = assignmentStrategy.select(inc, users.technicians());
        inc.assign(c.technician(), system, now,
                   assignmentStrategy.name() + " strategy: " + String.join(", ", c.reasons()));
    }

    public synchronized Incident getIncident(User viewer, String id) {
        Incident inc = find(id);
        boolean mine = inc.getReporter().equals(viewer)
                || inc.getAssignee().map(viewer::equals).orElse(false);
        if (!mine && !viewer.can(Permission.VIEW_ALL_INCIDENTS)) {
            throw new UnauthorizedOperationException("You cannot view " + id + ".");
        }
        return inc;
    }

    public synchronized List<Candidate> recommendTechnicians(User viewer, String id, int top) {
        Incident inc = getIncident(viewer, id);
        List<Candidate> ranked = assignmentStrategy.rank(inc, users.technicians());
        return ranked.subList(0, Math.min(top, ranked.size()));
    }

    public synchronized Incident assignManually(User actor, String id, String technicianId) {
        actor.require(Permission.REASSIGN_INCIDENT);
        Incident inc = find(id);
        User u = user(technicianId);
        if (!(u instanceof Technician tech)) throw new ValidationException(technicianId + " is not a technician.");
        inc.assign(tech, actor, now(), "manual assignment by " + actor.getUserId());
        return commit(inc);
    }

    public synchronized Incident reassess(User actor, String id, String impact, String urgency, Integer affectedUsers) {
        actor.require(Permission.REASSIGN_INCIDENT);
        Incident inc = find(id);
        inc.reassess(impact == null ? null : IncidentFactory.parse(Impact.class, impact, "impact"),
                     urgency == null ? null : IncidentFactory.parse(Urgency.class, urgency, "urgency"),
                     affectedUsers);
        applyPriority(inc, now());
        return commit(inc);
    }

    private Incident act(String id, BiConsumer<Incident, Instant> action) {
        Incident inc = find(id);
        action.accept(inc, now());
        return commit(inc);
    }

    public synchronized Incident acknowledge(User u, String id) { return act(id, (i, t) -> i.acknowledge(u, t)); }
    public synchronized Incident startWork(User u, String id) { return act(id, (i, t) -> i.startWork(u, t)); }
    public synchronized Incident addNote(User u, String id, String text, boolean internal) {
        return act(id, (i, t) -> i.addNote(u, text, internal, t));
    }
    public synchronized Incident requestInfo(User u, String id, String question) { return act(id, (i, t) -> i.requestInfo(u, question, t)); }
    public synchronized Incident provideInfo(User u, String id, String answer) { return act(id, (i, t) -> i.provideInfo(u, answer, t)); }
    public synchronized Incident resolve(User u, String id, String fix, String rootCause, String preventiveAction) {
        return act(id, (i, t) -> i.resolve(u, fix, rootCause, preventiveAction, t));
    }
    public synchronized Incident verify(User u, String id) { return act(id, (i, t) -> i.verify(u, t)); }
    public synchronized Incident close(User u, String id) { return act(id, (i, t) -> i.close(u, t)); }
    public synchronized Incident giveFeedback(User u, String id, int rating, String comment) {
        return act(id, (i, t) -> i.giveFeedback(u, rating, comment, t));
    }

    /**
     * Reopen, then STICKY REASSIGNMENT: the technician who knows the incident gets it back
     * if they have capacity; otherwise the normal strategy picks someone else.
     */
    public synchronized Incident reopen(User u, String id, String reason) {
        Incident inc = find(id);
        Instant now = now();
        inc.reopen(u, reason, now);
        Optional<Technician> prev = inc.getPreviousAssignee().filter(t -> t.hasCapacityFor(inc.getPriority()));
        try {
            if (prev.isPresent()) inc.assign(prev.get(), system, now, "sticky reassignment: worked on it before");
            else autoAssign(inc, now);
        } catch (TechnicianUnavailableException e) {
            inc.recordSystemEvent(EventType.SYSTEM_NOTICE, "reassignment failed: " + e.getMessage(),
                                  system, now, idsOf(Role.TEAM_LEAD), true);
        }
        return commit(inc);
    }

    // ═════════════════════════════ background monitoring ═══════════════════════
    /**
     * Call every minute from a scheduler (Member 3: Spring &#64;Scheduled or a
     * ScheduledExecutorService). Sends each SLA warning/breach once and performs
     * automatic escalation.
     */
    public synchronized Reports.MonitorResult runMonitor() {
        Instant now = now();
        List<String> warnings = new ArrayList<>(), breaches = new ArrayList<>();
        List<Map.Entry<String, Role>> escalations = new ArrayList<>();
        List<String> autoClosed = new ArrayList<>();
        List<String> managers = idsOf(Role.TEAM_LEAD, Role.IT_MANAGER);

        for (Incident inc : incidents.findAll()) {
            if ("RESOLVED".equals(inc.getStatus()) && inc.getResolvedAt() != null
                    && !inc.getResolvedAt().plus(autoCloseAfter).isAfter(now)) {
                inc.close(system, now);
                autoClosed.add(inc.getIncidentId());
                commit(inc);
            }
        }

        for (Incident inc : incidents.findOpen()) {
            SLAClock sla = inc.getSla();
            if (sla == null) continue;
            SLAStatus status = sla.status(now);
            if (status == SLAStatus.AT_RISK && !sla.isWarningSent()) {
                sla.markWarningSent();
                inc.recordSystemEvent(EventType.SLA_WARNING, String.format(
                    "SLA warning: %.0f%% of resolution time used", sla.usedFraction(now) * 100),
                    system, now, withAssignee(inc, managers), false);
                warnings.add(inc.getIncidentId());
            } else if (status == SLAStatus.BREACHED && !sla.isBreachNotified()) {
                sla.markBreachNotified();
                inc.recordSystemEvent(EventType.SLA_BREACHED, "SLA VIOLATED for " + inc.getPriority().name(),
                    system, now, withAssignee(inc, managers), true);
                breaches.add(inc.getIncidentId());
            }
            escalation.evaluate(inc, now).ifPresent(h -> {
                inc.escalate(h.level(), h.role(), idsOf(h.role()), system, now);
                escalations.add(Map.entry(inc.getIncidentId(), h.role()));
            });
            commit(inc);
        }
        return new Reports.MonitorResult(warnings, breaches, escalations, autoClosed);
    }

    private static List<String> withAssignee(Incident inc, List<String> base) {
        List<String> ids = new ArrayList<>(base);
        inc.getAssignee().ifPresent(t -> ids.add(t.getUserId()));
        return ids;
    }

    // ═════════════════════════════ intelligence ════════════════════════════════
    public synchronized List<IncidentCorrelator.Correlation> correlations(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        return correlator.correlate(incidents.findOpen());
    }

    public synchronized List<SLARiskAnalyzer.SLARisk> slaRisks(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        Instant now = now();
        return incidents.findOpen().stream()
            .map(i -> riskAnalyzer.assess(i, now)).flatMap(Optional::stream)
            .sorted(Comparator.comparingDouble(SLARiskAnalyzer.SLARisk::risk).reversed())
            .toList();
    }

    public synchronized List<ResolutionSuggester.Suggestion> suggestResolutions(User viewer, String id) {
        Incident inc = getIncident(viewer, id);
        List<Incident> history = incidents.findAll().stream().filter(i -> !i.getResolutions().isEmpty()).toList();
        return resolutionSuggester.suggest(inc, history, 3);
    }

    public synchronized WhatIfSimulator.BlastRadius simulateFailure(User viewer, String serviceId) {
        viewer.require(Permission.VIEW_REPORTS);
        return whatIf.simulateFailure(serviceId);
    }

    // ═════════════════════════════ search & reports ════════════════════════════
    public synchronized List<Incident> search(User viewer, SearchCriteria criteria) {
        Instant now = now();
        boolean all = viewer.can(Permission.VIEW_ALL_INCIDENTS);
        return incidents.findAll().stream()
            .filter(i -> all || i.getReporter().equals(viewer) || i.getAssignee().map(viewer::equals).orElse(false))
            .filter(criteria.toPredicate(now))
            .sorted(Comparator.comparingInt((Incident i) -> i.getPriority() == null ? 9 : i.getPriority().rank())
                              .thenComparing(Incident::getCreatedAt))
            .toList();
    }

    /** Technician workspace: my open incidents, most urgent first (priority, then SLA time left). */
    public synchronized List<Incident> myQueue(Technician technician) {
        Instant now = now();
        return incidents.findOpen().stream()
            .filter(i -> i.getAssignee().map(technician::equals).orElse(false))
            .sorted(Comparator.comparingInt((Incident i) -> i.getPriority().rank())
                .thenComparing(i -> i.getSla() == null ? Duration.ZERO : i.getSla().timeRemaining(now)))
            .toList();
    }

    /** Employee portal: everything I reported, newest first. */
    public synchronized List<Incident> myIncidents(User reporter) {
        return incidents.findAll().stream().filter(i -> i.getReporter().equals(reporter))
            .sorted(Comparator.comparing(Incident::getCreatedAt).reversed()).toList();
    }

    /** Admin: monitor SLA violations. */
    public synchronized List<Incident> slaViolations(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        return search(viewer, SearchCriteria.where().slaStatus("BREACHED"));
    }

    /** Admin: the system-wide audit log, newest first. */
    public synchronized List<DomainEvent> allAuditLogs(User viewer) {
        viewer.require(Permission.VIEW_AUDIT);
        List<DomainEvent> all = new ArrayList<>(audit.all());
        Collections.reverse(all);
        return all;
    }

    public synchronized List<String> notificationFailures(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        return notifier.deliveryFailures();
    }

    public synchronized List<DomainEvent> auditTrail(User viewer, String incidentId) {
        Incident inc = find(incidentId);
        if (!viewer.can(Permission.VIEW_AUDIT) && !inc.getReporter().equals(viewer)
                && !inc.getAssignee().map(viewer::equals).orElse(false)) {
            throw new UnauthorizedOperationException("You cannot view the audit trail of " + incidentId + ".");
        }
        return audit.forIncident(incidentId);
    }

    public synchronized List<Notification> inbox(User user) {
        return channel("in_app", InAppChannel.class).inbox(user.getUserId());
    }

    public synchronized Reports.Overview overview(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        Instant now = now();
        List<Incident> all = incidents.findAll();
        long breached = all.stream().filter(i -> i.getSla() != null && i.getSla().status(now) == SLAStatus.BREACHED).count();
        List<Incident> resolved = all.stream().filter(i -> i.getResolvedAt() != null).toList();
        double mttr = resolved.stream()
            .mapToLong(i -> Duration.between(i.getCreatedAt(), i.getResolvedAt()).toMinutes()).average().orElse(0);
        double mtta = all.stream().filter(i -> i.getSla() != null && i.getSla().getRespondedAt() != null)
            .mapToLong(i -> Duration.between(i.getCreatedAt(), i.getSla().getRespondedAt()).toMinutes()).average().orElse(0);
        OptionalDouble fb = all.stream().flatMap(i -> i.getFeedback().stream()).mapToInt(f -> f.rating()).average();
        long withSla = all.stream().filter(i -> i.getSla() != null).count();
        return new Reports.Overview(
            all.size(),
            (int) all.stream().filter(Incident::isOpen).count(),
            (int) all.stream().filter(i -> i.isOpen() && i.getPriority() == Priority.P1).count(),
            resolved.size(),
            (int) breached,
            withSla == 0 ? 100.0 : Math.round(1000.0 * (withSla - breached) / withSla) / 10.0,
            Math.round(mtta * 10) / 10.0,
            Math.round(mttr * 10) / 10.0,
            fb.isPresent() ? Math.round(fb.getAsDouble() * 100) / 100.0 : null,
            all.stream().collect(Collectors.groupingBy(Incident::getStatus, TreeMap::new, Collectors.counting())),
            all.stream().filter(i -> i.getPriority() != null)
               .collect(Collectors.groupingBy(i -> i.getPriority().name(), TreeMap::new, Collectors.counting())));
    }

    public synchronized List<Reports.TechnicianWorkload> technicianWorkload(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        return users.technicians().stream()
            .sorted(Comparator.comparingInt(Technician::workloadPoints).reversed().thenComparing(Technician::getUserId))
            .map(t -> new Reports.TechnicianWorkload(t.getUserId(), t.getName(), t.activeCount(),
                    t.workloadPoints(), t.getMaxWorkloadPoints(), t.getResolvedCount(), t.isAvailable()))
            .toList();
    }

    /** Per-service counts plus live health: DOWN if an open P1 hits it, DEGRADED if anything is open. */
    public synchronized List<Reports.ServiceAnalysis> serviceAnalysis(User viewer) {
        viewer.require(Permission.VIEW_REPORTS);
        List<Incident> all = incidents.findAll();
        List<Reports.ServiceAnalysis> out = new ArrayList<>();
        for (ITService s : catalog.all()) {
            List<Incident> mine = all.stream().filter(i -> i.getService() == s).toList();
            long open = mine.stream().filter(Incident::isOpen).count();
            boolean p1 = mine.stream().anyMatch(i -> i.isOpen() && i.getPriority() == Priority.P1);
            ServiceHealth h = p1 ? ServiceHealth.DOWN : open > 0 ? ServiceHealth.DEGRADED : ServiceHealth.OPERATIONAL;
            out.add(new Reports.ServiceAnalysis(s.getServiceId(), s.getName(), mine.size(), open, h));
        }
        out.sort(Comparator.comparingLong(Reports.ServiceAnalysis::totalIncidents).reversed()
                           .thenComparing(Reports.ServiceAnalysis::serviceId));
        return out;
    }
}
