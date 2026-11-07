package com.itsm.domain.intelligence;

import java.util.*;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Small, explainable text tools: tokenising, stop-word removal, ITSM synonym
 * normalisation ("down", "failing", "unable" all mean an outage) and Jaccard similarity.
 * Member 4 can replace this with TF-IDF or embeddings behind the same interfaces.
 */
public final class TextSimilarity {
    private static final Pattern WORD = Pattern.compile("[a-z0-9]+");
    private static final Set<String> STOP = Set.of(
        "the", "a", "an", "is", "are", "to", "of", "and", "or", "in", "on", "for", "not", "my", "our",
        "we", "i", "it", "be", "can", "cannot", "with", "users", "user", "make", "complete", "this",
        "that", "from", "at", "has", "have", "all", "every", "again", "too", "us");
    private static final Map<String, String> SYNONYMS = Map.ofEntries(
        Map.entry("unavailable", "outage"), Map.entry("down", "outage"), Map.entry("failing", "outage"),
        Map.entry("fails", "outage"), Map.entry("failed", "outage"), Map.entry("unable", "outage"),
        Map.entry("error", "outage"), Map.entry("broken", "outage"), Map.entry("crash", "outage"),
        Map.entry("crashes", "outage"), Map.entry("unreachable", "outage"), Map.entry("working", "outage"),
        Map.entry("transaction", "payment"), Map.entry("transactions", "payment"),
        Map.entry("payments", "payment"), Map.entry("pay", "payment"),
        Map.entry("signin", "login"), Map.entry("logon", "login"), Map.entry("password", "login"),
        Map.entry("wifi", "network"), Map.entry("internet", "network"), Map.entry("vpn", "network"));

    private TextSimilarity() {}

    /** Lower-case words, no filtering. */
    public static Set<String> rawWords(String text) {
        Set<String> out = new HashSet<>();
        if (text == null) return out;
        Matcher m = WORD.matcher(text.toLowerCase());
        while (m.find()) out.add(m.group());
        return out;
    }

    /** Meaningful, normalised tokens. */
    public static Set<String> tokens(String text) {
        Set<String> out = new HashSet<>();
        for (String w : rawWords(text)) {
            if (w.length() > 1 && !STOP.contains(w)) out.add(SYNONYMS.getOrDefault(w, w));
        }
        return out;
    }

    /** |A ∩ B| / |A ∪ B|, from 0 (nothing shared) to 1 (identical). */
    public static double jaccard(String a, String b) {
        Set<String> ta = tokens(a), tb = tokens(b);
        if (ta.isEmpty() || tb.isEmpty()) return 0;
        Set<String> inter = new HashSet<>(ta);
        inter.retainAll(tb);
        Set<String> union = new HashSet<>(ta);
        union.addAll(tb);
        return (double) inter.size() / union.size();
    }
}
