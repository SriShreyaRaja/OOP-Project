package com.itsm.domain.assignment;

import com.itsm.domain.user.Technician;

import java.util.List;

/** A ranked technician with the reasons behind the score (shown in the UI and audit trail). */
public record Candidate(Technician technician, double score, List<String> reasons) {
    public Candidate {
        reasons = List.copyOf(reasons);
    }

    public String summary() {
        return String.format("%s (score %.2f): %s", technician.getUserId(), score, String.join("; ", reasons));
    }
}
