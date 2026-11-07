package com.itsm.domain.notification;

import java.util.*;

/** Dashboard bell icon. Keeps an inbox per user, which the frontend reads. */
public class InAppChannel implements NotificationChannel {
    private final Map<String, List<Notification>> inboxes = new HashMap<>();

    @Override public String name() { return "in_app"; }

    @Override public void send(Notification n) {
        inboxes.computeIfAbsent(n.recipientId(), k -> new ArrayList<>()).add(n);
    }

    public List<Notification> inbox(String userId) {
        return Collections.unmodifiableList(inboxes.getOrDefault(userId, List.of()));
    }
}
