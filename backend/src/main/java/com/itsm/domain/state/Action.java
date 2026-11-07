package com.itsm.domain.state;

/** Everything that can be done to an incident's lifecycle. */
public enum Action {
    CLASSIFY, ASSIGN, ACKNOWLEDGE, START_WORK, REQUEST_INFO, PROVIDE_INFO,
    RESOLVE, VERIFY, REOPEN, CLOSE
}
