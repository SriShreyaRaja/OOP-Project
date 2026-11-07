package com.itsm.domain.notification;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * Pretend vendor SDK with its own, incompatible API (different method name,
 * parameter order and a numeric priority flag). We cannot change vendor code.
 */
public class ThirdPartySmsGateway {
    public record SentMessage(String msisdn, String text, int flag) {}

    private final List<SentMessage> sent = new ArrayList<>();

    public String dispatchText(String msisdn, String text, int priorityFlag) {
        sent.add(new SentMessage(msisdn, text, priorityFlag));
        return "MSG-" + sent.size();
    }

    public List<SentMessage> sent() { return Collections.unmodifiableList(sent); }
}
