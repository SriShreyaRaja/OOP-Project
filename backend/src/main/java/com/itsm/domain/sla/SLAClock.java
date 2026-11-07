package com.itsm.domain.sla;

import com.itsm.domain.common.SLAStatus;
import com.itsm.domain.common.TimeFormat;

import java.time.Duration;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Per-incident SLA timer.
 *
 * Supports PAUSE/RESUME: while the technician waits for the reporter to answer
 * (AWAITING_INFO), the clock stops and both deadlines move forward by the paused time.
 * That keeps the SLA fair to technicians, as real ITSM tools do.
 */
public class SLAClock {
    private SLAPolicy policy;
    private final Instant startedAt;
    private Instant pausedSince;
    private Duration pausedTotal = Duration.ZERO;
    private Instant respondedAt;
    private Instant resolvedAt;
    private boolean responseBreached;
    private boolean resolutionBreached;
    private boolean warningSent;
    private boolean breachNotified;

    public SLAClock(SLAPolicy policy, Instant startedAt) {
        this.policy = policy;
        this.startedAt = startedAt;
    }

    public SLAPolicy getPolicy() { return policy; }

    // ---- persistence (Member 3) ---------------------------------------------------
    public Instant getPausedSince() { return pausedSince; }
    public Duration getPausedTotal() { return pausedTotal; }
    public Instant getRespondedAt() { return respondedAt; }
    public Instant getResolvedAt() { return resolvedAt; }

    /** Rebuild a clock exactly as it was saved. */
    public static SLAClock restore(SLAPolicy policy, Instant startedAt, Instant pausedSince, Duration pausedTotal,
                                   Instant respondedAt, Instant resolvedAt, boolean responseBreached,
                                   boolean resolutionBreached, boolean warningSent, boolean breachNotified) {
        SLAClock c = new SLAClock(policy, startedAt);
        c.pausedSince = pausedSince;
        c.pausedTotal = pausedTotal == null ? Duration.ZERO : pausedTotal;
        c.respondedAt = respondedAt;
        c.resolvedAt = resolvedAt;
        c.responseBreached = responseBreached;
        c.resolutionBreached = resolutionBreached;
        c.warningSent = warningSent;
        c.breachNotified = breachNotified;
        return c;
    }

    /** On re-prioritisation the deadlines stay anchored to the original creation time. */
    public void reprioritize(SLAPolicy newPolicy) { this.policy = newPolicy; }

    public Instant responseDue() { return startedAt.plus(policy.responseTarget()).plus(pausedTotal); }
    public Instant resolutionDue() { return startedAt.plus(policy.resolutionTarget()).plus(pausedTotal); }

    // ---- pause / resume -------------------------------------------------------------
    public boolean isPaused() { return pausedSince != null; }

    public void pause(Instant now) { if (pausedSince == null) pausedSince = now; }

    public void resume(Instant now) {
        if (pausedSince != null) {
            pausedTotal = pausedTotal.plus(Duration.between(pausedSince, now));
            pausedSince = null;
        }
    }

    // ---- milestones -----------------------------------------------------------------
    public void markResponded(Instant now) {
        if (respondedAt == null) {
            respondedAt = now;
            responseBreached = now.isAfter(responseDue());
        }
    }

    public void markResolved(Instant now) {
        resume(now);
        resolvedAt = now;
        if (now.isAfter(resolutionDue())) resolutionBreached = true;
    }

    public void reopen() { resolvedAt = null; }

    public boolean isResponded() { return respondedAt != null; }
    public boolean isResponseBreached() { return responseBreached; }
    public boolean isResolutionBreached() { return resolutionBreached; }

    // one-shot flags so the monitor notifies only once
    public boolean isWarningSent() { return warningSent; }
    public void markWarningSent() { warningSent = true; }
    public boolean isBreachNotified() { return breachNotified; }
    public void markBreachNotified() { breachNotified = true; }

    // ---- evaluation -----------------------------------------------------------------
    private Instant effectiveNow(Instant now) { return isPaused() ? pausedSince : now; }

    private double fractionOf(Duration target, Instant now) {
        Duration elapsed = Duration.between(startedAt, effectiveNow(now)).minus(pausedTotal);
        return Math.max(0.0, (double) elapsed.toMillis() / target.toMillis());
    }

    /** 0.0 = just started, 1.0 = resolution deadline reached. */
    public double usedFraction(Instant now) { return fractionOf(policy.resolutionTarget(), now); }
    public double responseUsedFraction(Instant now) { return fractionOf(policy.responseTarget(), now); }

    public Duration timeRemaining(Instant now) { return Duration.between(effectiveNow(now), resolutionDue()); }

    public SLAStatus status(Instant now) {
        if (resolvedAt != null) return resolutionBreached ? SLAStatus.BREACHED : SLAStatus.MET;
        Instant t = effectiveNow(now);
        if (resolutionBreached || responseBreached || t.isAfter(resolutionDue())) return SLAStatus.BREACHED;
        if (respondedAt == null && t.isAfter(responseDue())) return SLAStatus.BREACHED;
        if (isPaused()) return SLAStatus.PAUSED;
        if (usedFraction(now) >= policy.warningThreshold()) return SLAStatus.AT_RISK;
        return SLAStatus.ON_TRACK;
    }

    public Map<String, Object> toMap(Instant now) {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("priority", policy.priority().name());
        m.put("responseDue", TimeFormat.both(responseDue()));
        m.put("resolutionDue", TimeFormat.both(resolutionDue()));
        m.put("responded", respondedAt != null);
        m.put("status", status(now).name());
        m.put("usedPercent", Math.round(usedFraction(now) * 1000) / 10.0);
        m.put("minutesRemaining", timeRemaining(now).toMinutes());
        m.put("paused", isPaused());
        return m;
    }
}
