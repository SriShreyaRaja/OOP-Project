package com.itsm.domain.notification;

import com.itsm.domain.event.DomainEvent;
import com.itsm.domain.event.EventObserver;
import com.itsm.domain.user.User;

import java.util.*;
import java.util.function.Function;

/**
 * Observer that turns events into notifications, with a simple channel-selection policy:
 *   urgent events (P1, SLA breach, escalation) → every registered channel (in-app + email + SMS)
 *   normal events                              → in-app + email only
 */
public class NotificationService implements EventObserver {
    private static final Set<String> NORMAL = Set.of("in_app", "email");

    private final Function<String, Optional<User>> userLookup;
    private final Map<String, NotificationChannel> channels = new LinkedHashMap<>();
    private final List<String> deliveryFailures = new ArrayList<>();

    public NotificationService(Function<String, Optional<User>> userLookup) {
        this.userLookup = userLookup;
    }

    public void registerChannel(NotificationChannel channel) { channels.put(channel.name(), channel); }

    public <T extends NotificationChannel> T channel(String name, Class<T> type) {
        return type.cast(channels.get(name));
    }

    /** Failed deliveries, for the admin dashboard / retry job. */
    public List<String> deliveryFailures() { return Collections.unmodifiableList(deliveryFailures); }

    private List<NotificationChannel> select(DomainEvent e) {
        if (e.urgent()) return List.copyOf(channels.values());
        return channels.values().stream().filter(c -> NORMAL.contains(c.name())).toList();
    }

    @Override
    public void onEvent(DomainEvent e) {
        String subject = e.incidentId() + ": " + pretty(e.type().name());
        for (String rid : new LinkedHashSet<>(e.recipients())) {           // de-duplicate
            userLookup.apply(rid).ifPresent(user -> {
                for (NotificationChannel ch : select(e)) {
                    try {
                        ch.send(new Notification(rid, ch.addressFor(user), ch.name(), subject,
                                                 e.description(), e.at(), e.urgent()));
                    } catch (RuntimeException ex) {
                        // One broken channel (e.g. SMS provider down) must never break the incident workflow.
                        deliveryFailures.add(ch.name() + " → " + rid + ": " + ex.getMessage());
                    }
                }
            });
        }
    }

    private static String pretty(String enumName) {
        String s = enumName.replace('_', ' ').toLowerCase();
        return Character.toUpperCase(s.charAt(0)) + s.substring(1);
    }
}
