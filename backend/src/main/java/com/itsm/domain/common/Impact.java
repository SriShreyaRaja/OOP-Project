package com.itsm.domain.common;

/** How widely the problem is felt. Higher = worse. */
public enum Impact {
    LOW(1), MEDIUM(2), HIGH(3), ORGANIZATION(4);

    private final int weight;
    Impact(int weight) { this.weight = weight; }
    public int weight() { return weight; }
}
