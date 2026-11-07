"""
Custom exception hierarchy.

Every business-rule violation raises a specific subclass of ITSMError. The API layer
(Member 3) catches ITSMError once and uses `code` + `http_status` to build the response;
tests (Member 4) assert the exact subclass.
"""
from __future__ import annotations


class ITSMError(Exception):
    code = "ITSM_ERROR"
    http_status = 400

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def to_dict(self) -> dict:
        return {"error": self.code, "message": self.message}


class ValidationError(ITSMError):
    code, http_status = "INVALID_INPUT", 400


class AuthenticationError(ITSMError):
    code, http_status = "INVALID_LOGIN", 401


class UnauthorizedOperationError(ITSMError):
    code, http_status = "UNAUTHORIZED_OPERATION", 403


class IncidentNotFoundError(ITSMError):
    code, http_status = "INCIDENT_NOT_FOUND", 404


class UserNotFoundError(ITSMError):
    code, http_status = "USER_NOT_FOUND", 404


class ServiceNotFoundError(ITSMError):
    code, http_status = "SERVICE_NOT_FOUND", 404


class CategoryNotFoundError(ITSMError):
    code, http_status = "CATEGORY_NOT_FOUND", 404


class InvalidStateTransitionError(ITSMError):
    code, http_status = "INVALID_STATE_TRANSITION", 409


class TechnicianUnavailableError(ITSMError):
    code, http_status = "TECHNICIAN_UNAVAILABLE", 409


class WorkloadExceededError(ITSMError):
    code, http_status = "WORKLOAD_EXCEEDED", 409


class DependencyCycleError(ITSMError):
    code, http_status = "DEPENDENCY_CYCLE", 409


class DuplicateIncidentError(ITSMError):
    """A report that looks like an already-open incident. Carries the original's ID."""
    code, http_status = "DUPLICATE_INCIDENT", 409

    def __init__(self, original_incident_id: str, similarity: float):
        super().__init__(f"Looks like a duplicate of {original_incident_id} "
                         f"(similarity {similarity:.2f}). Add details there instead.")
        self.original_incident_id = original_incident_id
        self.similarity = similarity


class SLAConfigurationError(ITSMError):
    code, http_status = "MISSING_SLA_CONFIGURATION", 500


class ExternalServiceError(ITSMError):
    """Network / third-party failure (e.g. the SMS or email provider is unreachable)."""
    code, http_status = "EXTERNAL_SERVICE_FAILURE", 502


class PersistenceError(ITSMError):
    """Database failure. Member 3 wraps sqlite3 errors in this so the API answers 503 cleanly."""
    code, http_status = "DATABASE_FAILURE", 503
