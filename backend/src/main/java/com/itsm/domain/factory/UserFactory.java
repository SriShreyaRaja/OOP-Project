package com.itsm.domain.factory;

import com.itsm.domain.common.Role;
import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.user.*;

import java.util.Map;

/** FACTORY PATTERN: builds the right User subclass from a role string (e.g. from a signup form). */
public final class UserFactory {
    private UserFactory() {}

    public static User create(String role, String id, String name, String email, String password,
                              Map<String, Integer> skills, int maxWorkloadPoints, double years, String department) {
        Role r = IncidentFactory.parse(Role.class, role, "role");
        return switch (r) {
            case EMPLOYEE -> new Employee(id, name, email, password, department);
            case TECHNICIAN -> new Technician(id, name, email, password, skills, maxWorkloadPoints, years);
            case TEAM_LEAD -> new TeamLead(id, name, email, password, skills, maxWorkloadPoints, years);
            case SYSTEM_ADMIN -> new Administrator(id, name, email, password);
            case IT_MANAGER -> new ITManager(id, name, email, password);
            case SYSTEM -> throw new ValidationException("The SYSTEM account cannot be created.");
        };
    }

    public static User employee(String id, String name, String email, String password, String dept) {
        return create("EMPLOYEE", id, name, email, password, null, 0, 0, dept);
    }
}
