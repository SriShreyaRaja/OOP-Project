package com.itsm.domain.persistence;

import com.itsm.domain.common.Role;
import com.itsm.domain.exception.ValidationException;
import com.itsm.domain.user.*;

import java.util.Map;

/**
 * Plain data version of a User — exactly one database row.
 * Member 3: save {@link #from(User)}, and turn a loaded row back into a User with {@link #toUser()}.
 *
 * Suggested table:  users(user_id PK, name, email UNIQUE, role, password_hash, active,
 *                         department, skills, max_workload_points, years_experience, available)
 * skills is stored as text like "NETWORK=5,HARDWARE=3" (see {@link Codec}).
 */
public record UserRecord(String userId, String name, String email, Role role, String passwordHash,
                         boolean active, String department, Map<String, Integer> skills,
                         int maxWorkloadPoints, double yearsExperience, boolean available) {

    public UserRecord {
        skills = skills == null ? Map.of() : Map.copyOf(skills);
    }

    public static UserRecord from(User u) {
        if (u instanceof Technician t) {
            return new UserRecord(t.getUserId(), t.getName(), t.getEmail(), t.role(), t.encodedPasswordHash(),
                    t.isActive(), null, t.getSkills(), t.getMaxWorkloadPoints(), t.getYearsExperience(), t.isAvailable());
        }
        String dept = u instanceof Employee e ? e.getDepartment() : null;
        return new UserRecord(u.getUserId(), u.getName(), u.getEmail(), u.role(), u.encodedPasswordHash(),
                u.isActive(), dept, Map.of(), 0, 0, false);
    }

    public User toUser() {
        PasswordHash hash = PasswordHash.decode(passwordHash);
        User u = switch (role) {
            case EMPLOYEE -> new Employee(userId, name, email, hash, department);
            case TECHNICIAN -> new Technician(userId, name, email, hash, skills, maxWorkloadPoints, yearsExperience);
            case TEAM_LEAD -> new TeamLead(userId, name, email, hash, skills, maxWorkloadPoints, yearsExperience);
            case SYSTEM_ADMIN -> new Administrator(userId, name, email, hash);
            case IT_MANAGER -> new ITManager(userId, name, email, hash);
            case SYSTEM -> throw new ValidationException("The SYSTEM account is never stored.");
        };
        if (!active) u.deactivate();
        if (u instanceof Technician t) t.setAvailable(available);
        return u;
    }
}
