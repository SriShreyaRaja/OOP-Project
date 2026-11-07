package com.itsm.domain.repository;

import com.itsm.domain.common.Role;
import com.itsm.domain.user.Technician;
import com.itsm.domain.user.User;

import java.util.List;
import java.util.Optional;

public interface UserRepository {
    void save(User user);
    Optional<User> findById(String userId);
    List<User> findAll();

    default Optional<User> findByEmail(String email) {
        return findAll().stream().filter(u -> u.getEmail().equalsIgnoreCase(email)).findFirst();
    }

    default List<Technician> technicians() {
        return findAll().stream().filter(Technician.class::isInstance).map(Technician.class::cast).toList();
    }

    default List<User> byRole(Role role) { return findAll().stream().filter(u -> u.role() == role).toList(); }
}
