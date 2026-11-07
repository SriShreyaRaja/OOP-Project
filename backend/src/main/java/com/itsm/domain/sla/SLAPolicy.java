package com.itsm.domain.sla;

import com.itsm.domain.common.Priority;
import com.itsm.domain.exception.ValidationException;

import java.time.Duration;

/**
 * Response/resolution targets for one priority.
 * serviceId == null means "default for every service"; otherwise it overrides for that service.
 */
public record SLAPolicy(Priority priority, Duration responseTarget, Duration resolutionTarget,
                        double warningThreshold, String serviceId) {

    public SLAPolicy {
        if (responseTarget.isNegative() || responseTarget.isZero()
                || resolutionTarget.isNegative() || resolutionTarget.isZero()) {
            throw new ValidationException("SLA targets must be positive.");
        }
        if (responseTarget.compareTo(resolutionTarget) > 0) {
            throw new ValidationException("Response target cannot exceed resolution target.");
        }
        if (warningThreshold <= 0 || warningThreshold >= 1) {
            throw new ValidationException("warningThreshold must be between 0 and 1.");
        }
    }

    public static SLAPolicy of(Priority p, Duration response, Duration resolution) {
        return new SLAPolicy(p, response, resolution, 0.75, null);
    }
}
