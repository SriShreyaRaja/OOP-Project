package com.itsm.domain.notification;

import com.itsm.domain.user.User;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/** Simulated email (keeps an outbox). Member 3 can replace with a real SMTP channel. */
public class EmailChannel implements NotificationChannel {
    private final List<Notification> outbox = new ArrayList<>();

    @Override public String name() { return "email"; }
    @Override public String addressFor(User user) { return user.getEmail(); }
    @Override public void send(Notification n) { outbox.add(n); }

    public List<Notification> outbox() { return Collections.unmodifiableList(outbox); }
}
