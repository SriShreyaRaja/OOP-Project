package com.itsm.domain.user;

import com.itsm.domain.common.Role;

public class ITManager extends Administrator {
    public ITManager(String userId, String name, String email, String password) {
        super(userId, name, email, password);
    }

    public ITManager(String userId, String name, String email, PasswordHash hash) {
        super(userId, name, email, hash);
    }

    @Override public Role role() { return Role.IT_MANAGER; }
}
