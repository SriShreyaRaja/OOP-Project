package com.itsm.domain.user;

import com.itsm.domain.common.Permission;
import com.itsm.domain.common.Role;

import java.util.EnumSet;
import java.util.Set;

public class Employee extends User {
    private static final Set<Permission> PERMS = EnumSet.of(
        Permission.REPORT_INCIDENT, Permission.VIEW_OWN_INCIDENTS, Permission.ADD_INFO,
        Permission.GIVE_FEEDBACK, Permission.VERIFY_RESOLUTION);

    private final String department;

    public Employee(String userId, String name, String email, String password, String department) {
        super(userId, name, email, password);
        this.department = department == null ? "General" : department;
    }

    public Employee(String userId, String name, String email, PasswordHash hash, String department) {
        super(userId, name, email, hash);
        this.department = department == null ? "General" : department;
    }

    public String getDepartment() { return department; }
    @Override public Role role() { return Role.EMPLOYEE; }
    @Override public Set<Permission> permissions() { return PERMS; }
}
