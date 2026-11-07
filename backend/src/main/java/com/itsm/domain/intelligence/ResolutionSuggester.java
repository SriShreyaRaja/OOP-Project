package com.itsm.domain.intelligence;

import com.itsm.domain.incident.Incident;
import com.itsm.domain.incident.Resolution;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** Intelligent Feature G: suggest fixes that worked for similar past incidents. */
public class ResolutionSuggester {
    public record Suggestion(String fromIncidentId, String fix, String rootCause, double similarity) {}

    public List<Suggestion> suggest(Incident incident, List<Incident> history, int top) {
        String text = incident.getTitle() + " " + incident.getDescription();
        List<Suggestion> out = new ArrayList<>();
        for (Incident h : history) {
            if (h.getIncidentId().equals(incident.getIncidentId()) || h.getResolutions().isEmpty()) continue;
            double s = TextSimilarity.jaccard(text, h.getTitle() + " " + h.getDescription());
            if (h.getService().getServiceId().equals(incident.getService().getServiceId())) s += 0.2;
            if (s > 0.2) {
                Resolution r = h.getResolutions().get(h.getResolutions().size() - 1);
                out.add(new Suggestion(h.getIncidentId(), r.description(), r.rootCause(),
                        Math.round(Math.min(s, 1.0) * 100) / 100.0));
            }
        }
        out.sort(Comparator.comparingDouble(Suggestion::similarity).reversed());
        return out.subList(0, Math.min(top, out.size()));
    }
}
