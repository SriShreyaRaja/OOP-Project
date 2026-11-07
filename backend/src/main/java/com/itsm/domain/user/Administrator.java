package com.itsm.domain.user;

import com.itsm.domain.common.Permission;
import com.itsm.domain.common.Role;

import java.util.EnumSet;
import java.util.Set;

public class Administrator extends User {
    private static final Set<Permission> PERMS = EnumSet.of(
        Permission.MANAGE_USERS, Permission.MANAGE_SERVICES, Permission.CONFIGURE_SLA,
        Permission.CONFIGURE_CATEGORIES, Permission.CONFIGURE_STRATEGY, Permission.VIEW_ALL_INCIDENTS,
        Permission.VIEW_REPORTS, Permission.VIEW_AUDIT, Permission.REASSIGN_INCIDENT,
        Permission.CLOSE_INCIDENT, Permission.REPORT_INCIDENT);

    public Administrator(String userId, String name, String email, String password) {
        super(userId, name, email, password);
    }

    public Administrator(String userId, String name, String email, PasswordHash hash) {
        super(userId, name, email, hash);
    }

    @Override public Role role() { return Role.SYSTEM_ADMIN; }
    @Override public Set<Permission> permissions() { return PERMS; }
}
