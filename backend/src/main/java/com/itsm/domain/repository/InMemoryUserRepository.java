package com.itsm.domain.repository;

import com.itsm.domain.user.User;

import java.util.*;

public class InMemoryUserRepository implements UserRepository {
    private final Map<String, User> items = new LinkedHashMap<>();

    @Override public void save(User user) { items.put(user.getUserId(), user); }
    @Override public Optional<User> findById(String id) { return Optional.ofNullable(items.get(id)); }
    @Override public List<User> findAll() { return List.copyOf(items.values()); }
}
