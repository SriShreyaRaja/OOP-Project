package com.itsm.domain;

import com.itsm.domain.common.FakeClock;
import com.itsm.domain.desk.IncidentRequest;
import com.itsm.domain.desk.SampleData;
import com.itsm.domain.desk.ServiceDesk;
import com.itsm.domain.incident.Incident;
import com.itsm.domain.user.Technician;
import com.itsm.domain.user.User;
import org.junit.jupiter.api.BeforeEach;

/** Fresh organisation and fake clock for every test. */
public abstract class TestSupport {
    protected FakeClock clock;
    protected SampleData.Org org;
    protected ServiceDesk desk;

    @BeforeEach
    void setUpOrg() {
        clock = new FakeClock();
        org = SampleData.build(clock);
        desk = org.desk();
    }

    protected User u(String key) { return org.get(key); }

    protected IncidentRequest.Builder paymentOutage() {
        return IncidentRequest.builder("Payment application unavailable",
                "Users are unable to complete transactions on the payment app.")
            .impact("ORGANIZATION").urgency("CRITICAL").affectedUsers(500);
    }

    protected Incident reportPayment() { return desk.reportIncident(u("emp1"), paymentOutage().build()); }

    protected Technician assignee(Incident i) { return i.getAssignee().orElseThrow(); }

    protected void work(Incident i) {
        desk.acknowledge(assignee(i), i.getIncidentId());
        desk.startWork(assignee(i), i.getIncidentId());
    }

    protected void resolve(Incident i) {
        desk.resolve(assignee(i), i.getIncidentId(), "Restarted the failing service node.", "Node memory leak", "Add heap alert");
    }

    protected void fullLifecycle(Incident i) {
        work(i);
        resolve(i);
        desk.verify(u("emp1"), i.getIncidentId());
        desk.close(u("emp1"), i.getIncidentId());
    }
}
