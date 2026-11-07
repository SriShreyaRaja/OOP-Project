package com.itsm.domain.incident;

import java.time.Instant;

/** A comment on an incident. Internal notes are visible to support staff only. */
public record Note(String authorId, String text, Instant at, boolean internal) {}
