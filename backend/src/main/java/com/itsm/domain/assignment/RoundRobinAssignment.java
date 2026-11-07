package com.itsm.domain.assignment;

import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;

import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;

/** Fair rotation among skilled, available technicians. Remembers who went last. */
public class RoundRobinAssignment extends AssignmentStrategy {
    private String lastAssignedId;

    @Override public String name() { return "round_robin"; }

    @Override
    public List<Candidate> rank(Incident incident, List<Technician> all) {
        List<Technician> pool = new ArrayList<>(eligible(incident, all));
        pool.sort(Comparator.comparing(Technician::getUserId));
        int start = 0;
        for (int i = 0; i < pool.size(); i++) {
            if (pool.get(i).getUserId().equals(lastAssignedId)) { start = i + 1; break; }
        }
        List<Candidate> out = new ArrayList<>();
        for (int k = 0; k < pool.size(); k++) {
            Technician t = pool.get((start + k) % pool.size());
            out.add(new Candidate(t, pool.size() - k, List.of("next in rotation (#" + (k + 1) + ")")));
        }
        return out;
    }

    @Override
    public Candidate select(Incident incident, List<Technician> all) {
        Candidate c = super.select(incident, all);
        lastAssignedId = c.technician().getUserId();
        return c;
    }

    @Override protected Candidate score(Incident incident, Technician t) {
        throw new UnsupportedOperationException("round robin ranks by rotation");
    }
}
