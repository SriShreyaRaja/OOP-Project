package com.itsm.domain.intelligence;

import com.itsm.domain.incident.Incident;

import java.time.Duration;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/**
 * Baseline duplicate detector: normalised-keyword Jaccard similarity, plus a bonus when
 * both incidents hit the same service, restricted to open incidents in a recent time window.
 */
public class KeywordDuplicateDetector implements DuplicateDetector {
    private final double threshold;
    private final double sameServiceBonus;
    private final Duration window;

    public KeywordDuplicateDetector() { this(0.45, 0.25, Duration.ofHours(24)); }

    public KeywordDuplicateDetector(double threshold, double sameServiceBonus, Duration window) {
        this.threshold = threshold;
        this.sameServiceBonus = sameServiceBonus;
        this.window = window;
    }

    @Override
    public List<Match> findDuplicates(Incident incident, List<Incident> candidates) {
        String text = incident.getTitle() + " " + incident.getDescription();
        List<Match> out = new ArrayList<>();
        for (Incident other : candidates) {
            if (other.getIncidentId().equals(incident.getIncidentId()) || !other.isOpen()) continue;
            if (Duration.between(other.getCreatedAt(), incident.getCreatedAt()).abs().compareTo(window) > 0) continue;
            double score = TextSimilarity.jaccard(text, other.getTitle() + " " + other.getDescription());
            boolean sameService = other.getService().getServiceId().equals(incident.getService().getServiceId());
            if (sameService) score += sameServiceBonus;
            score = Math.min(1.0, Math.round(score * 100) / 100.0);
            if (score >= threshold) {
                out.add(new Match(other.getIncidentId(), score, "text similarity" + (sameService ? " + same service" : "")));
            }
        }
        out.sort(Comparator.comparingDouble(Match::score).reversed());
        return out;
    }
}
