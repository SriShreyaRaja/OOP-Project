package com.itsm.domain.priority;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.common.Impact;
import com.itsm.domain.common.Urgency;

/**
 * STRATEGY PATTERN #1: how to turn an assessment into a priority.
 * Admins can swap the active strategy at runtime; incidents never know which one ran.
 */
public interface PriorityStrategy {
    String name();
    PriorityResult calculate(Impact impact, Urgency urgency, ITService service, int affectedUsers);
}
