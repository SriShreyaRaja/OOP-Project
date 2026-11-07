package com.itsm.domain.common;

public enum Priority {
    P1("Critical", 8), P2("High", 5), P3("Medium", 3), P4("Low", 1);

    private final String label;
    private final int workloadPoints;   // how much of a technician's capacity it consumes

    Priority(String label, int workloadPoints) {
        this.label = label;
        this.workloadPoints = workloadPoints;
    }

    public String label() { return label; }
    public int workloadPoints() { return workloadPoints; }
    /** 1 = most important; handy for sorting queues. */
    public int rank() { return ordinal() + 1; }
    @Override public String toString() { return name() + " - " + label; }
}
