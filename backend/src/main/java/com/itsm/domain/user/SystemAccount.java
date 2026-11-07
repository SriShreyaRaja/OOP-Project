package com.itsm.domain.user;

import com.itsm.domain.common.Permission;
import com.itsm.domain.common.Role;

import java.util.UUID;

/**
 * The actor for automatic actions (auto-classify, auto-assign, SLA scans, escalation).
 * It can never log in: its password is random and thrown away.
 */
public final class SystemAccount extends Administrator {
    public static final String ID = "SYSTEM";

    public SystemAccount() {
        super(ID, "I-ITSM Automation", "system@itsm.local", UUID.randomUUID() + "x1");
    }

    @Override public Role role() { return Role.SYSTEM; }
    @Override public boolean checkPassword(String password) { return false; }
    @Override public boolean can(Permission permission) { return permissions().contains(permission); }
}
