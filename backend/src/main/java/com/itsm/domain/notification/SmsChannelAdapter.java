package com.itsm.domain.notification;

import com.itsm.domain.user.User;

import java.util.Map;

/** ADAPTER PATTERN: makes the vendor SMS SDK look like one of our NotificationChannels. */
public class SmsChannelAdapter implements NotificationChannel {
    private static final int SMS_LIMIT = 160;
    private final ThirdPartySmsGateway gateway;
    private final Map<String, String> phoneBook;

    public SmsChannelAdapter(ThirdPartySmsGateway gateway, Map<String, String> phoneBook) {
        this.gateway = gateway;
        this.phoneBook = Map.copyOf(phoneBook);
    }

    @Override public String name() { return "sms"; }

    @Override public String addressFor(User user) { return phoneBook.getOrDefault(user.getUserId(), "+910000000000"); }

    @Override
    public void send(Notification n) {
        String text = "[I-ITSM] " + n.subject();
        if (text.length() > SMS_LIMIT) text = text.substring(0, SMS_LIMIT);
        gateway.dispatchText(n.address(), text, n.urgent() ? 1 : 3);
    }
}
