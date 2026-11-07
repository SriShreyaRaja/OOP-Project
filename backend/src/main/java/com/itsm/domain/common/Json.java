package com.itsm.domain.common;

import java.lang.reflect.RecordComponent;
import java.time.Instant;
import java.util.Collection;
import java.util.Map;
import java.util.Optional;

/**
 * Minimal JSON writer with no dependencies. Handles maps, lists, records, enums, strings,
 * numbers, booleans, Instants and Optionals. Lets the demo, Colab and tests print exactly
 * what the API will send. (In Spring Boot, Jackson does this automatically.)
 *
 *   Json.write(incident.toMap(desk.now()))   →  {"incidentId":"INC1001", ...}
 */
public final class Json {
    private Json() {}

    public static String write(Object value) {
        StringBuilder sb = new StringBuilder();
        append(sb, value);
        return sb.toString();
    }

    private static void append(StringBuilder sb, Object v) {
        if (v == null) { sb.append("null"); return; }
        if (v instanceof Optional<?> o) { append(sb, o.orElse(null)); return; }
        if (v instanceof String s) { quote(sb, s); return; }
        if (v instanceof Number || v instanceof Boolean) { sb.append(v); return; }
        if (v instanceof Enum<?> e) { quote(sb, e.name()); return; }
        if (v instanceof Instant t) { quote(sb, t.toString()); return; }
        if (v instanceof Map<?, ?> m) {
            sb.append('{');
            boolean first = true;
            for (Map.Entry<?, ?> e : m.entrySet()) {
                if (!first) sb.append(',');
                first = false;
                quote(sb, String.valueOf(e.getKey()));
                sb.append(':');
                append(sb, e.getValue());
            }
            sb.append('}');
            return;
        }
        if (v instanceof Collection<?> c) {
            sb.append('[');
            boolean first = true;
            for (Object o : c) {
                if (!first) sb.append(',');
                first = false;
                append(sb, o);
            }
            sb.append(']');
            return;
        }
        if (v.getClass().isRecord()) {
            sb.append('{');
            boolean first = true;
            for (RecordComponent rc : v.getClass().getRecordComponents()) {
                if (!first) sb.append(',');
                first = false;
                quote(sb, rc.getName());
                sb.append(':');
                try {
                    append(sb, rc.getAccessor().invoke(v));
                } catch (ReflectiveOperationException ex) {
                    sb.append("null");
                }
            }
            sb.append('}');
            return;
        }
        quote(sb, v.toString());
    }

    private static void quote(StringBuilder sb, String s) {
        sb.append('"');
        for (char ch : s.toCharArray()) {
            switch (ch) {
                case '"' -> sb.append("\\\"");
                case '\\' -> sb.append("\\\\");
                case '\n' -> sb.append("\\n");
                case '\r' -> sb.append("\\r");
                case '\t' -> sb.append("\\t");
                default -> {
                    if (ch < 0x20) sb.append(String.format("\\u%04x", (int) ch));
                    else sb.append(ch);
                }
            }
        }
        sb.append('"');
    }
}
