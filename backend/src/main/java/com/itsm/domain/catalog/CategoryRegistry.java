package com.itsm.domain.catalog;

import com.itsm.domain.exception.CategoryNotFoundException;
import com.itsm.domain.intelligence.TextSimilarity;

import java.util.*;

/**
 * Open/Closed Principle in action: a new category is a registry entry, not a code change.
 * Also provides keyword-based category suggestion (Intelligent Feature F).
 */
public class CategoryRegistry {
    private final Map<String, Category> categories = new TreeMap<>();

    public void register(Category category) { categories.put(category.getName(), category); }

    public Category get(String name) {
        Category c = categories.get(name.toUpperCase());
        if (c == null) throw new CategoryNotFoundException("Category '" + name + "' does not exist.");
        return c;
    }

    public boolean exists(String name) { return categories.containsKey(name.toUpperCase()); }
    public List<String> names() { return List.copyOf(categories.keySet()); }

    /** Best keyword match and a confidence (share of all keyword hits), if any. */
    public Optional<Suggestion> suggest(String text) {
        Set<String> words = TextSimilarity.rawWords(text);
        Map<String, Integer> hits = new HashMap<>();
        for (Category c : categories.values()) {
            int n = (int) c.getKeywords().stream().filter(words::contains).count();
            if (n > 0) hits.put(c.getName(), n);
        }
        if (hits.isEmpty()) return Optional.empty();
        int total = hits.values().stream().mapToInt(Integer::intValue).sum();
        Map.Entry<String, Integer> best = Collections.max(hits.entrySet(), Map.Entry.comparingByValue());
        return Optional.of(new Suggestion(best.getKey(), (double) best.getValue() / total));
    }

    public record Suggestion(String category, double confidence) {}

    public static CategoryRegistry withDefaults() {
        CategoryRegistry r = new CategoryRegistry();
        r.register(new Category("HARDWARE", "Physical devices",
            Set.of("laptop", "printer", "monitor", "keyboard", "mouse", "device", "screen", "jammed")));
        r.register(new Category("SOFTWARE", "Installed software",
            Set.of("install", "crash", "crashes", "update", "license", "excel", "software")));
        r.register(new Category("NETWORK", "Connectivity",
            Set.of("wifi", "network", "internet", "vpn", "latency", "connection", "disconnects")));
        r.register(new Category("DATABASE", "Databases",
            Set.of("database", "db", "query", "sql", "table", "deadlock")));
        r.register(new Category("CLOUD", "Cloud platforms",
            Set.of("cloud", "aws", "azure", "bucket", "instance", "kubernetes")));
        r.register(new Category("SECURITY", "Security events",
            Set.of("phishing", "virus", "malware", "breach", "suspicious", "hacked")));
        r.register(new Category("AUTHENTICATION", "Login and identity",
            Set.of("login", "password", "sso", "otp", "locked", "authenticate", "signin")));
        r.register(new Category("APPLICATION", "Business applications",
            Set.of("payment", "transaction", "transactions", "portal", "app", "application", "checkout")));
        r.register(new Category("STORAGE", "Disks and files",
            Set.of("disk", "drive", "quota", "backup", "file", "files")));
        return r;
    }
}
