package com.itsm.domain.desk;

import com.itsm.domain.catalog.ITService;
import com.itsm.domain.common.Clock;
import com.itsm.domain.user.*;

import java.util.LinkedHashMap;
import java.util.Map;

/** A ready-made organisation for the demo, the tests and the video. */
public final class SampleData {
    public static final String PASSWORD = "Passw0rd!";

    private SampleData() {}

    public record Org(ServiceDesk desk, Map<String, User> people) {
        public User get(String key) { return people.get(key); }
        public Technician tech(String key) { return (Technician) people.get(key); }
    }

    public static Org build(Clock clock) {
        return seed(new ServiceDesk(clock));
    }

    /**
     * Load the sample organisation into an existing (empty) desk.
     * Member 3, at startup:  desk.attachStorage(db);  if (desk.isEmpty()) SampleData.seed(desk);
     */
    public static Org seed(ServiceDesk desk) {
        Administrator admin = new Administrator("A001", "Asha Admin", "asha@corp.in", PASSWORD);
        desk.registerUserBootstrap(admin);

        desk.addService(admin, new ITService("SVC-DB", "Core Database", 5, "DATABASE", "postgres", "database", "db"));
        desk.addService(admin, new ITService("SVC-AUTH", "Authentication SSO", 5, "AUTHENTICATION", "login", "sso", "password"));
        desk.addService(admin, new ITService("SVC-PAY", "Payment Application", 5, "APPLICATION", "payment", "transaction", "checkout"));
        desk.addService(admin, new ITService("SVC-NET", "Office Network", 4, "NETWORK", "wifi", "network", "vpn", "internet"));
        desk.addService(admin, new ITService("SVC-MAIL", "Email & Calendar", 3, "APPLICATION", "email", "outlook", "calendar"));
        desk.addService(admin, new ITService("SVC-PRINT", "Printing", 1, "HARDWARE", "printer", "print"));
        desk.addService(admin, new ITService("SVC-RPT", "Finance Reporting", 3, "APPLICATION", "report", "dashboard"));
        desk.addDependency(admin, "SVC-AUTH", "SVC-DB");
        desk.addDependency(admin, "SVC-PAY", "SVC-DB");
        desk.addDependency(admin, "SVC-PAY", "SVC-AUTH");
        desk.addDependency(admin, "SVC-MAIL", "SVC-AUTH");
        desk.addDependency(admin, "SVC-PRINT", "SVC-NET");
        desk.addDependency(admin, "SVC-RPT", "SVC-PAY");

        Map<String, User> p = new LinkedHashMap<>();
        p.put("admin", admin);
        p.put("manager", new ITManager("M001", "Meera Manager", "meera@corp.in", PASSWORD));
        p.put("lead", new TeamLead("L001", "Leo Lead", "leo@corp.in", PASSWORD,
                Map.of("APPLICATION", 4, "DATABASE", 4, "NETWORK", 3), 16, 9));
        p.put("tApp", new Technician("T201", "Tara AppSupport", "tara@corp.in", PASSWORD,
                Map.of("APPLICATION", 5, "DATABASE", 3), 20, 4));
        p.put("tNet", new Technician("T202", "Nikhil Network", "nikhil@corp.in", PASSWORD,
                Map.of("NETWORK", 5, "HARDWARE", 3), 20, 6));
        p.put("tDb", new Technician("T203", "Dev DBA", "dev@corp.in", PASSWORD,
                Map.of("DATABASE", 5, "CLOUD", 3, "APPLICATION", 2), 20, 7));
        p.put("tJr", new Technician("T204", "Jaya Junior", "jaya@corp.in", PASSWORD,
                Map.of("SOFTWARE", 3, "HARDWARE", 4, "AUTHENTICATION", 3), 24, 1));
        p.put("emp1", new Employee("E101", "Ravi Finance", "ravi@corp.in", PASSWORD, "Finance"));
        p.put("emp2", new Employee("E102", "Sana Sales", "sana@corp.in", PASSWORD, "Sales"));
        p.put("emp3", new Employee("E103", "Kiran Ops", "kiran@corp.in", PASSWORD, "Operations"));
        p.forEach((k, u) -> { if (!k.equals("admin")) desk.registerUser(admin, u); });
        return new Org(desk, p);
    }
}
