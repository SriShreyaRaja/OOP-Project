package com.itsm.domain.factory;

import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.notification.*;

import java.util.Map;

/** FACTORY PATTERN: builds a notification channel from its configured name. */
public final class NotificationChannelFactory {
    private NotificationChannelFactory() {}

    public static NotificationChannel create(String name, Map<String, String> phoneBook) {
        return switch (name.toLowerCase()) {
            case "in_app" -> new InAppChannel();
            case "email" -> new EmailChannel();
            case "sms" -> new SmsChannelAdapter(new ThirdPartySmsGateway(), phoneBook == null ? Map.of() : phoneBook);
            default -> throw new ValidationException("Unknown notification channel '" + name + "'.");
        };
    }
}
