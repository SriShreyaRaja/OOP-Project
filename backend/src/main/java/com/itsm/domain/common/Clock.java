package com.itsm.domain.common;

import java.time.Instant;

/**
 * Time abstraction. The domain never calls Instant.now() directly, so tests and the
 * demo can fast-forward time (see {@link FakeClock}) to trigger SLA breaches instantly.
 */
@FunctionalInterface
public interface Clock {
    Instant now();

    static Clock system() { return Instant::now; }
}
