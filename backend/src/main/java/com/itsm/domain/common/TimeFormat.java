package com.itsm.domain.common;

import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.time.format.DateTimeFormatter;

/** Every user-facing time is shown in both UTC and IST. */
public final class TimeFormat {
    public static final ZoneId IST = ZoneId.of("Asia/Kolkata");
    private static final DateTimeFormatter UTC_FMT =
        DateTimeFormatter.ofPattern("yyyy-MM-dd HH:mm").withZone(ZoneOffset.UTC);
    private static final DateTimeFormatter IST_FMT =
        DateTimeFormatter.ofPattern("HH:mm").withZone(IST);

    private TimeFormat() {}

    /** e.g. "2026-11-07 04:30 UTC / 10:00 IST" */
    public static String both(Instant t) {
        return UTC_FMT.format(t) + " UTC / " + IST_FMT.format(t) + " IST";
    }
}
