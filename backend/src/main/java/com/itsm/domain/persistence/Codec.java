package com.itsm.domain.persistence;

import java.util.*;

/**
 * Tiny text encoders so small collections fit in one database column without a JSON library.
 *   map  {NETWORK=5, HARDWARE=3}  ⇄  "NETWORK=5,HARDWARE=3"
 *   list [INC1002, INC1003]       ⇄  "INC1002,INC1003"
 * (If Member 3 prefers Jackson/JSON columns, these can be ignored.)
 */
public final class Codec {
    private Codec() {}

    public static String encodeIntMap(Map<String, Integer> m) {
        StringJoiner j = new StringJoiner(",");
        new TreeMap<>(m).forEach((k, v) -> j.add(k + "=" + v));
        return j.toString();
    }

    public static Map<String, Integer> decodeIntMap(String s) {
        Map<String, Integer> out = new LinkedHashMap<>();
        if (s == null || s.isBlank()) return out;
        for (String pair : s.split(",")) {
            String[] kv = pair.split("=", 2);
            out.put(kv[0].trim(), Integer.parseInt(kv[1].trim()));
        }
        return out;
    }

    public static String encodeList(Collection<String> items) { return String.join(",", items); }

    public static List<String> decodeList(String s) {
        if (s == null || s.isBlank()) return List.of();
        return Arrays.stream(s.split(",")).map(String::trim).filter(x -> !x.isEmpty()).toList();
    }
}
