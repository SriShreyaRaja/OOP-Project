package com.itsm.domain.notification;

import java.time.Instant;

public record Notification(String recipientId, String address, String channel,
                           String subject, String body, Instant at, boolean urgent) {}
