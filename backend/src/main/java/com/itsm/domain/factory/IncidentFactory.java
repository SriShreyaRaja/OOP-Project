package com.itsm.domain.factory;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.catalog.ServiceCatalog;
import com.itsm.domain.common.Clock;
import com.itsm.domain.common.Impact;
import com.itsm.domain.common.Urgency;
import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.User;

/**
 * FACTORY PATTERN: the one place that knows how to build a valid Incident.
 * Parses text input (the API receives "HIGH" as a string), resolves or guesses the
 * service, stamps the time from the Clock, and issues gap-free IDs (INC1001, INC1002…).
 */
public class IncidentFactory {
    private final ServiceCatalog catalog;
    private final Clock clock;
    private int nextNumber;

    public IncidentFactory(ServiceCatalog catalog, Clock clock, int startNumber) {
        this.catalog = catalog;
        this.clock = clock;
        this.nextNumber = startNumber;
    }

    public synchronized String nextId() { return "INC" + nextNumber++; }

    /** Hand back the last ID if that incident was rejected, so IDs stay gap-free. */
    public synchronized void discard(String incidentId) {
        if (incidentId.equals("INC" + (nextNumber - 1))) nextNumber--;
    }

    /** After reloading saved incidents, continue numbering after the highest existing ID. */
    public synchronized void continueAfter(String existingId) {
        try {
            int n = Integer.parseInt(existingId.replaceAll("\\D", ""));
            if (n >= nextNumber) nextNumber = n + 1;
        } catch (NumberFormatException ignored) {
            // non-standard IDs don't affect numbering
        }
    }

    public synchronized String peekNextId() { return "INC" + nextNumber; }

    public static <E extends Enum<E>> E parse(Class<E> type, String value, String field) {
        try {
            return Enum.valueOf(type, value.trim().toUpperCase());
        } catch (IllegalArgumentException | NullPointerException e) {
            throw new ValidationException(field + " must be one of " + java.util.Arrays.toString(type.getEnumConstants()));
        }
    }

    public Incident create(User reporter, String title, String description, String serviceId,
                           String impact, String urgency, int affectedUsers) {
        ITService service = (serviceId != null && !serviceId.isBlank())
            ? catalog.get(serviceId)
            : catalog.guessService(title + " " + description).orElseThrow(() ->
                new ValidationException("Could not determine the affected service; please choose one."));
        Impact i = parse(Impact.class, impact, "impact");
        Urgency u = parse(Urgency.class, urgency, "urgency");
        return new Incident(nextId(), title, description, reporter, service, i, u, affectedUsers, clock.now());
    }
}
