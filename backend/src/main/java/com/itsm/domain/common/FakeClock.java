package com.itsm.domain.common;

import java.time.Duration;
import java.time.Instant;

public class FakeClock implements Clock {
    private Instant now;

    public FakeClock() { this(Instant.parse("2026-11-07T04:30:00Z")); }   // 10:00 IST
    public FakeClock(Instant start) { this.now = start; }

    @Override public Instant now() { return now; }

    public void advanceMinutes(long minutes) { now = now.plus(Duration.ofMinutes(minutes)); }
    public void advance(Duration d) { now = now.plus(d); }
}
