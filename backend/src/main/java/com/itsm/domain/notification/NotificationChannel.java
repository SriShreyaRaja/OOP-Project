package com.itsm.domain.notification;

import com.itsm.domain.user.User;

/** A delivery mechanism. Adding Slack/Teams/push later = one new implementation. */
public interface NotificationChannel {
    String name();
    void send(Notification notification);

    default String addressFor(User user) { return user.getUserId(); }
}
