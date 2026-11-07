package com.itsm.domain.intelligence;

import com.itsm.domain.incident.Incident;

import java.util.List;

/** Intelligent Feature A: Duplicate Incident Detection. Member 4 can plug in a smarter version. */
public interface DuplicateDetector {
    record Match(String incidentId, double score, String reason) {}

    List<Match> findDuplicates(Incident incident, List<Incident> candidates);
}
