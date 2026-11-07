package com.itsm.domain.catalog;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

/** Incident categories are DATA, not an enum, so admins can add new ones at runtime. */
public class Category {
    private final String name;
    private final String description;
    private final Set<String> keywords = new HashSet<>();

    public Category(String name, String description, Set<String> keywords) {
        this.name = name.toUpperCase();
        this.description = description == null ? "" : description;
        keywords.forEach(k -> this.keywords.add(k.toLowerCase()));
    }

    public String getName() { return name; }
    public String getDescription() { return description; }
    public Set<String> getKeywords() { return Collections.unmodifiableSet(keywords); }
}
