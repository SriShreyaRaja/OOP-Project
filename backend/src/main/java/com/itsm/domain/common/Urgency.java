package com.itsm.domain.common;

/** How quickly the business needs it fixed. Higher = more urgent. */
public enum Urgency {
    LOW(1), MEDIUM(2), HIGH(3), CRITICAL(4);

    private final int weight;
    Urgency(int weight) { this.weight = weight; }
    public int weight() { return weight; }
}
