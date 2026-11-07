package com.itsm.domain.user;

import com.itsm.domain.common.Permission;
import com.itsm.domain.common.Role;
import com.itsm.domain.exception.UnauthorizedOperationException;
import com.itsm.domain.exception.ValidationException;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Abstract base for every person in the system.
 *
 * Inheritance is used only for true "is-a" relationships:
 * <pre>
 *   User (abstract)
 *    ├── Employee
 *    ├── Technician
 *    │     └── TeamLead        (a team lead IS a technician with extra rights)
 *    └── Administrator
 *          ├── ITManager       (an IT manager IS an administrator)
 *          └── SystemAccount   (automation)
 * </pre>
 * Polymorphism: each subclass answers {@link #permissions()} differently, so the
 * rest of the system just asks {@code user.can(Permission.X)} without instanceof checks.
 */
public abstract class User {
    private static final Pattern EMAIL = Pattern.compile("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$");

    private final String userId;
    private final String name;
    private final String email;
    private PasswordHash passwordHash;
    private boolean active = true;

    protected User(String userId, String name, String email, String password) {
        this(userId, name, email, PasswordHash.of(password));
    }

    /** Used when reloading a saved user: the stored hash is reused, no password needed. */
    protected User(String userId, String name, String email, PasswordHash passwordHash) {
        if (userId == null || userId.isBlank() || name == null || name.isBlank()) {
            throw new ValidationException("User id and name are required.");
        }
        if (email == null || !EMAIL.matcher(email).matches()) {
            throw new ValidationException("Invalid email: " + email);
        }
        this.userId = userId.trim();
        this.name = name.trim();
        this.email = email.trim().toLowerCase();
        this.passwordHash = java.util.Objects.requireNonNull(passwordHash);
    }

    public String getUserId() { return userId; }
    public String getName() { return name; }
    public String getEmail() { return email; }
    public boolean isActive() { return active; }

    public boolean checkPassword(String password) {
        return active && passwordHash.matches(password);
    }

    public void changePassword(String oldPassword, String newPassword) {
        if (!checkPassword(oldPassword)) {
            throw new UnauthorizedOperationException("Old password is incorrect.");
        }
        this.passwordHash = PasswordHash.of(newPassword);
    }

    /** For persistence only (Member 3 stores this string). */
    public String encodedPasswordHash() { return passwordHash.encode(); }

    public void deactivate() { this.active = false; }
    public void activate() { this.active = true; }

    // ---- polymorphic authorization --------------------------------------------
    public abstract Role role();
    public abstract Set<Permission> permissions();

    public boolean can(Permission permission) {
        return active && permissions().contains(permission);
    }

    public void require(Permission permission) {
        if (!can(permission)) {
            throw new UnauthorizedOperationException(
                role() + " " + userId + " is not allowed to " + permission + ".");
        }
    }

    public Map<String, Object> toMap() {
        Map<String, Object> m = new LinkedHashMap<>();
        m.put("userId", userId);
        m.put("name", name);
        m.put("email", email);
        m.put("role", role().name());
        m.put("active", active);
        return m;
    }

    @Override public String toString() { return getClass().getSimpleName() + "[" + userId + " " + name + "]"; }
    @Override public boolean equals(Object o) { return o instanceof User u && u.userId.equals(userId); }
    @Override public int hashCode() { return userId.hashCode(); }
}
