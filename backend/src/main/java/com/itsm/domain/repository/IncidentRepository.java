package com.itsm.domain.repository;

import com.itsm.domain.incident.Incident;

import java.util.List;
import java.util.Optional;

/**
 * REPOSITORY PATTERN: the contract between the domain (Member 2) and the database (Member 3).
 * The domain only ever sees this interface. Member 3 writes a JDBC/JPA implementation
 * with the same methods and passes it to ServiceDesk; no domain code changes.
 */
public interface IncidentRepository {
    void save(Incident incident);
    Optional<Incident> findById(String incidentId);
    List<Incident> findAll();

    default List<Incident> findOpen() { return findAll().stream().filter(Incident::isOpen).toList(); }
}
