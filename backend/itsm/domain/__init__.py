"""
I-ITSM domain layer (Member 2). Everything outside the domain talks to ServiceDesk:

    from itsm.domain import ServiceDesk, IncidentRequest, SearchCriteria
"""
from .service_desk import IncidentRequest, SearchCriteria, ServiceDesk  # noqa: F401
