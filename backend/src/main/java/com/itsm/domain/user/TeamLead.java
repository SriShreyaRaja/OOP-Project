package com.itsm.domain.user;

import com.itsm.domain.common.Permission;
import com.itsm.domain.common.Role;

import java.util.EnumSet;
import java.util.Map;
import java.util.Set;

public class TeamLead extends Technician {
    public TeamLead(String userId, String name, String email, String password,
                    Map<String, Integer> skills, int maxWorkloadPoints, double yearsExperience) {
        super(userId, name, email, password, skills, maxWorkloadPoints, yearsExperience);
    }

    public TeamLead(String userId, String name, String email, PasswordHash hash,
                    Map<String, Integer> skills, int maxWorkloadPoints, double yearsExperience) {
        super(userId, name, email, hash, skills, maxWorkloadPoints, yearsExperience);
    }

    @Override public Role role() { return Role.TEAM_LEAD; }

    @Override
    public Set<Permission> permissions() {
        Set<Permission> p = EnumSet.copyOf(super.permissions());
        p.addAll(EnumSet.of(Permission.REASSIGN_INCIDENT, Permission.VIEW_ALL_INCIDENTS,
                            Permission.VIEW_REPORTS));
        return p;
    }
}
