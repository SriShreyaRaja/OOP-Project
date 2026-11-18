import asyncio
from contextlib import asynccontextmanager
import os
from datetime import datetime, timedelta, timezone
from fastapi import Query, Response
from itsm.domain import SearchCriteria
from datetime import timedelta
from itsm.domain.factory import UserFactory, parse_enum
from itsm.domain.catalog import ITService
from itsm.domain.sla import SLAPolicy
from itsm.domain.common import Priority

from itsm.api.init_db import open_desk
import jwt
from fastapi import FastAPI, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from itsm.domain import ServiceDesk, IncidentRequest, sample_data
from itsm.domain.common import SystemClock, to_plain
from itsm.domain.exceptions import ITSMError, AuthenticationError

@asynccontextmanager
async def lifespan(app: FastAPI):

    async def monitor_sla():
        while True:
            await asyncio.sleep(60)

            try:
                await asyncio.to_thread(desk.run_monitor)
                print("SLA monitoring completed")

            except Exception as e:
                print("SLA monitoring error:", e)

    task = asyncio.create_task(monitor_sla())

    yield

    task.cancel()

    try:
        await task
    except asyncio.CancelledError:
        pass
    finally:
        storage.close()

# --------------------------------------------------
# 1. APP SETUP
# --------------------------------------------------
app = FastAPI(
    title="I-ITSM Backend API",
    lifespan=lifespan
)
# Allow the frontend to communicate with the backend.
# For development only. Restrict this to your frontend URL later.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --------------------------------------------------
# 2. DOMAIN SETUP
# --------------------------------------------------
desk, storage, seeded = open_desk("data/itsm.db")
# --------------------------------------------------
# 3. JWT CONFIGURATION
# --------------------------------------------------
SECRET_KEY = os.getenv(
    "JWT_SECRET_KEY",
    "dev-only-change-this-secret-before-deployment"
)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def create_access_token(user_id: str):
    """Create a JWT token for a logged-in user."""

    expiration_time = datetime.now(timezone.utc) + timedelta(
        minutes=ACCESS_TOKEN_EXPIRE_MINUTES
    )

    payload = {
        "sub": user_id,
        "exp": expiration_time
    }

    token = jwt.encode(
        payload,
        SECRET_KEY,
        algorithm=ALGORITHM
    )

    return token


# --------------------------------------------------
# 4. DOMAIN ERROR HANDLING
# --------------------------------------------------

@app.exception_handler(ITSMError)
def handle_domain_error(request, error: ITSMError):
    return JSONResponse(
        status_code=error.http_status,
        content=error.to_dict()
    )


# --------------------------------------------------
# 5. REQUEST MODELS
# --------------------------------------------------
class LoginBody(BaseModel):
    email: str
    password: str
class IncidentBody(BaseModel):
    title: str
    description: str
    serviceId: str | None = None
    impact: str = "MEDIUM"
    urgency: str = "MEDIUM"
    affectedUsers: int = 1
    category: str | None = None

# --------------------------------------------------
# 6. AUTHENTICATION
# --------------------------------------------------

# Tells Swagger that our API uses Bearer tokens
security = HTTPBearer(auto_error=False)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security)
):
    # Check whether a Bearer token was provided
    if credentials is None:
        raise AuthenticationError("Please log in.")

    token = credentials.credentials

    try:
        # Decode and verify the JWT
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )

        user_id = payload.get("sub")

        if not user_id:
            raise AuthenticationError("Invalid login token.")

        # Retrieve the user from the domain
        return desk.user(user_id)

    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Session expired. Please log in again.")

    except jwt.InvalidTokenError:
        raise AuthenticationError("Invalid login token.")


# --------------------------------------------------
# 7. LOGIN ENDPOINT
# --------------------------------------------------

@app.post("/api/auth/login")
def login(body: LoginBody):

    # Domain verifies email, password and account lockout.
    user = desk.login(body.email, body.password)

    # Create a JWT after successful login.
    token = create_access_token(user.user_id)

    return {
        "token": token,
        "user": user.to_dict()
    }


# --------------------------------------------------
# 8. SERVICES ENDPOINT
# --------------------------------------------------
@app.get("/api/services")
def get_services(user=Depends(current_user)):
    return [
        service.to_dict()
        for service in desk.catalog.all()
    ]

# --------------------------------------------------
# 9. CATEGORIES ENDPOINT
# --------------------------------------------------

@app.get("/api/categories")
def get_categories(user=Depends(current_user)):

    return desk.categories.names()

# --------------------------------------------------
# 10. HOME / HEALTH CHECK
# --------------------------------------------------
@app.get("/")
def home():
    return {
        "message": "I-ITSM Backend API is running"
    }

# --------------------------------------------------
# 11. CREATE INCIDENT
# --------------------------------------------------
@app.post("/api/incidents", status_code=201)
def create_incident(
    body: IncidentBody,
    user=Depends(current_user)
):

    # Builder pattern: construct a domain request
    request = (
        IncidentRequest.builder(
            body.title,
            body.description
        )
        .service(body.serviceId)
        .impact(body.impact)
        .urgency(body.urgency)
        .affected_users(body.affectedUsers)
        .category(body.category)
        .build()
    )
    # ServiceDesk performs the actual business logic
    incident = desk.report_incident(user, request)

    # Return the incident in JSON format
    return incident.to_dict(desk.now(), user)

# --------------------------------------------------
# 12. GET MY INCIDENTS
# --------------------------------------------------
@app.get("/api/incidents/mine")
def get_my_incidents(user=Depends(current_user)):

    incidents = desk.my_incidents(user)

    return [
        incident.to_dict(desk.now(), user)
        for incident in incidents
    ]


# --------------------------------------------------
# 13. TECHNICIAN - VIEW ASSIGNED INCIDENTS
# --------------------------------------------------

@app.get("/api/technician/queue")
def technician_queue(user=Depends(current_user)):

    incidents = desk.my_queue(user)

    return [
        incident.to_dict(desk.now(), user)
        for incident in incidents
    ]


# --------------------------------------------------
# 14. TECHNICIAN - VIEW PROFILE
# --------------------------------------------------

@app.get("/api/technician/me")
def technician_profile(user=Depends(current_user)):

    return user.to_dict()


# --------------------------------------------------
# 15. TECHNICIAN - ACKNOWLEDGE INCIDENT
# --------------------------------------------------

@app.post("/api/incidents/{incident_id}/acknowledge")
def acknowledge_incident(
    incident_id: str,
    user=Depends(current_user)
):

    incident = desk.acknowledge(user, incident_id)

    return incident.to_dict(desk.now(), user)


# --------------------------------------------------
# 16. TECHNICIAN - START WORK
# --------------------------------------------------

@app.post("/api/incidents/{incident_id}/start")
def start_incident(
    incident_id: str,
    user=Depends(current_user)
):

    incident = desk.start_work(user, incident_id)

    return incident.to_dict(desk.now(), user)


# --------------------------------------------------
# 17. TECHNICIAN - RESOLVE INCIDENT
# --------------------------------------------------

class ResolveBody(BaseModel):
    fix: str
    rootCause: str
    preventiveAction: str | None = None


@app.post("/api/incidents/{incident_id}/resolve")
def resolve_incident(
    incident_id: str,
    body: ResolveBody,
    user=Depends(current_user)
):

    incident = desk.resolve(
        user,
        incident_id,
        body.fix,
        body.rootCause,
        body.preventiveAction
    )

    return incident.to_dict(desk.now(), user)


# --------------------------------------------------
# 18. EMPLOYEE - VERIFY RESOLUTION
# --------------------------------------------------

@app.post("/api/incidents/{incident_id}/verify")
def verify_incident(
    incident_id: str,
    user=Depends(current_user)
):

    incident = desk.verify(user, incident_id)

    return incident.to_dict(desk.now(), user)


# --------------------------------------------------
# 19. EMPLOYEE - CLOSE INCIDENT
# --------------------------------------------------

@app.post("/api/incidents/{incident_id}/close")
def close_incident(
    incident_id: str,
    user=Depends(current_user)
):

    incident = desk.close(user, incident_id)

    return incident.to_dict(desk.now(), user)


# --------------------------------------------------
# 20. EMPLOYEE - GIVE FEEDBACK
# --------------------------------------------------

class FeedbackBody(BaseModel):
    rating: int
    comment: str = ""


@app.post("/api/incidents/{incident_id}/feedback")
def give_incident_feedback(
    incident_id: str,
    body: FeedbackBody,
    user=Depends(current_user)
):

    incident = desk.give_feedback(
        user,
        incident_id,
        body.rating,
        body.comment
    )

    return incident.to_dict(desk.now(), user)


# --------------------------------------------------
# 21. ADMIN / STAFF - OVERVIEW DASHBOARD
# --------------------------------------------------

@app.get("/api/reports/overview")
def get_overview(user=Depends(current_user)):

    return to_plain(desk.overview(user))


# --------------------------------------------------
# 22. TECHNICIAN WORKLOAD REPORT
# --------------------------------------------------

@app.get("/api/reports/workload")
def get_workload(user=Depends(current_user)):

    return to_plain(desk.technician_workload(user))


# --------------------------------------------------
# 23. SERVICE ANALYSIS
# --------------------------------------------------

@app.get("/api/reports/services")
def get_service_analysis(user=Depends(current_user)):

    return to_plain(desk.service_analysis(user))


# --------------------------------------------------
# 24. SLA VIOLATIONS
# --------------------------------------------------

@app.get("/api/reports/sla-violations")
def get_sla_violations(user=Depends(current_user)):

    incidents = desk.sla_violations(user)

    return [
        incident.to_dict(desk.now(), user)
        for incident in incidents
    ]


# --------------------------------------------------
# 25. SLA RISKS
# --------------------------------------------------

@app.get("/api/reports/sla-risks")
def get_sla_risks(user=Depends(current_user)):

    return to_plain(desk.sla_risks(user))


# --------------------------------------------------
# 26. INCIDENT CORRELATIONS
# --------------------------------------------------

@app.get("/api/reports/correlations")
def get_correlations(user=Depends(current_user)):

    return to_plain(desk.correlations(user))


# --------------------------------------------------
# 27. SERVICE FAILURE SIMULATION
# --------------------------------------------------
@app.get("/api/reports/what-if/{service_id}")
def get_failure_simulation(
    service_id: str,
    user=Depends(current_user)
):

    return to_plain(
        desk.simulate_failure(user, service_id)
    )
# --------------------------------------------------
# 28. ALL AUDIT LOGS
# --------------------------------------------------
@app.get("/api/audit")
def get_audit_logs(user=Depends(current_user)):

    events = desk.all_audit_logs(user)

    return [event.to_dict() for event in events]


# ==================================================
# ADDITIONAL REQUEST MODELS
# ==================================================

class PasswordBody(BaseModel):
    oldPassword: str
    newPassword: str


class NoteBody(BaseModel):
    text: str
    internal: bool = False


class QuestionBody(BaseModel):
    question: str


class AnswerBody(BaseModel):
    answer: str


class ReasonBody(BaseModel):
    reason: str


class AvailabilityBody(BaseModel):
    available: bool


class AssignBody(BaseModel):
    technicianId: str


class ReassessBody(BaseModel):
    impact: str | None = None
    urgency: str | None = None
    affectedUsers: int | None = None


# ==================================================
# EMPLOYEE / COMMON ENDPOINTS
# ==================================================

@app.post("/api/auth/password", status_code=204)
def change_password(
    body: PasswordBody,
    user=Depends(current_user)
):
    desk.change_password(
        user, body.oldPassword, body.newPassword
    )
    return Response(status_code=204)


@app.get("/api/notifications")
def get_notifications(user=Depends(current_user)):
    return to_plain(desk.inbox(user))


@app.get("/api/incidents/{incident_id}")
def get_incident_details(
    incident_id: str,
    user=Depends(current_user)
):
    incident = desk.get_incident(user, incident_id)
    return incident.to_dict(desk.now(), user)


@app.get("/api/incidents/{incident_id}/notes")
def get_incident_notes(
    incident_id: str,
    user=Depends(current_user)
):
    incident = desk.get_incident(user, incident_id)
    return to_plain(incident.visible_notes(user))


@app.post("/api/incidents/{incident_id}/notes")
def add_incident_note(
    incident_id: str,
    body: NoteBody,
    user=Depends(current_user)
):
    incident = desk.add_note(
        user, incident_id, body.text, body.internal
    )
    return incident.to_dict(desk.now(), user)


@app.post("/api/incidents/{incident_id}/request-info")
def request_incident_info(
    incident_id: str,
    body: QuestionBody,
    user=Depends(current_user)
):
    incident = desk.request_info(
        user, incident_id, body.question
    )
    return incident.to_dict(desk.now(), user)


@app.post("/api/incidents/{incident_id}/info")
def provide_incident_info(
    incident_id: str,
    body: AnswerBody,
    user=Depends(current_user)
):
    incident = desk.provide_info(
        user, incident_id, body.answer
    )
    return incident.to_dict(desk.now(), user)


@app.post("/api/incidents/{incident_id}/reopen")
def reopen_incident(
    incident_id: str,
    body: ReasonBody,
    user=Depends(current_user)
):
    incident = desk.reopen(
        user, incident_id, body.reason
    )
    return incident.to_dict(desk.now(), user)


# ==================================================
# ADDITIONAL TECHNICIAN ENDPOINTS
# ==================================================

@app.post("/api/technician/availability", status_code=204)
def set_technician_availability(
    body: AvailabilityBody,
    user=Depends(current_user)
):
    desk.set_availability(
        user, user.user_id, body.available
    )
    return Response(status_code=204)


@app.get("/api/incidents/{incident_id}/suggestions")
def get_resolution_suggestions(
    incident_id: str,
    user=Depends(current_user)
):
    return to_plain(
        desk.suggest_resolutions(user, incident_id)
    )


# ==================================================
# TEAM LEAD / STAFF ENDPOINTS
# ==================================================

@app.get("/api/incidents")
def search_incidents(
    priority: str | None = None,
    status: str | None = None,
    category: str | None = None,
    service: str | None = None,
    technician: str | None = None,
    slaStatus: str | None = None,
    date_from: datetime | None = Query(
        default=None, alias="from"
    ),
    date_to: datetime | None = Query(
        default=None, alias="to"
    ),
    q: str | None = None,
    open: bool | None = None,
    user=Depends(current_user)
):
    criteria = SearchCriteria.where()

    if priority:
        criteria.priority(priority)
    if status:
        criteria.status(status)
    if category:
        criteria.category(category)
    if service:
        criteria.service(service)
    if technician:
        criteria.technician(technician)
    if slaStatus:
        criteria.sla_status(slaStatus)
    if date_from:
        criteria.created_from(date_from)
    if date_to:
        criteria.created_to(date_to)
    if q:
        criteria.text(q)
    if open is True:
        criteria.open_only()

    incidents = desk.search(user, criteria)

    return [
        i.to_dict(desk.now(), user)
        for i in incidents
    ]


@app.get("/api/incidents/{incident_id}/recommendations")
def technician_recommendations(
    incident_id: str,
    user=Depends(current_user)
):
    return to_plain(
        desk.recommend_technicians(user, incident_id, 3)
    )


@app.post("/api/incidents/{incident_id}/assign")
def manually_assign_incident(
    incident_id: str,
    body: AssignBody,
    user=Depends(current_user)
):
    incident = desk.assign_manually(
        user, incident_id, body.technicianId
    )
    return incident.to_dict(desk.now(), user)


@app.post("/api/incidents/{incident_id}/reassess")
def reassess_incident(
    incident_id: str,
    body: ReassessBody,
    user=Depends(current_user)
):
    incident = desk.reassess(
        user,
        incident_id,
        body.impact,
        body.urgency,
        body.affectedUsers
    )
    return incident.to_dict(desk.now(), user)


@app.get("/api/incidents/{incident_id}/audit")
def get_incident_audit(
    incident_id: str,
    user=Depends(current_user)
):
    events = desk.audit_trail(user, incident_id)

    return [event.to_dict() for event in events]


# ==================================================
# ADMIN REQUEST MODELS
# ==================================================

class NewUserBody(BaseModel):
    role: str
    userId: str
    name: str
    email: str
    password: str
    skills: dict[str, int] | None = None
    maxWorkloadPoints: int = 20
    yearsExperience: float = 0
    department: str | None = None


class SkillsBody(BaseModel):
    skills: dict[str, int]


class NewServiceBody(BaseModel):
    serviceId: str
    name: str
    businessCriticality: int
    defaultCategory: str
    keywords: list[str] = []


class DependencyBody(BaseModel):
    dependsOnId: str


class NewCategoryBody(BaseModel):
    name: str
    keywords: list[str]
    description: str = ""


class SLAPolicyBody(BaseModel):
    priority: str
    responseMinutes: int
    resolutionMinutes: int
    warningThreshold: float = 0.75
    serviceId: str | None = None


class StrategyBody(BaseModel):
    name: str


# ==================================================
# ADMIN - USER MANAGEMENT
# ==================================================

@app.post("/api/admin/users", status_code=201)
def create_admin_user(
    body: NewUserBody,
    user=Depends(current_user)
):
    new_user = UserFactory.create(
        body.role,
        body.userId,
        body.name,
        body.email,
        body.password,
        skills=body.skills,
        max_workload_points=body.maxWorkloadPoints,
        years_experience=body.yearsExperience,
        department=body.department
    )

    created = desk.register_user(user, new_user)
    return created.to_dict()


@app.post("/api/admin/users/{user_id}/deactivate", status_code=204)
def deactivate_admin_user(
    user_id: str,
    user=Depends(current_user)
):
    desk.deactivate_user(user, user_id)
    return Response(status_code=204)


@app.put("/api/admin/technicians/{technician_id}/skills", status_code=204)
def update_admin_skills(
    technician_id: str,
    body: SkillsBody,
    user=Depends(current_user)
):
    desk.update_technician_skills(
        user, technician_id, body.skills
    )
    return Response(status_code=204)


# ==================================================
# ADMIN - SERVICE MANAGEMENT
# ==================================================

@app.post("/api/admin/services", status_code=201)
def create_admin_service(
    body: NewServiceBody,
    user=Depends(current_user)
):
    service = ITService(
        body.serviceId,
        body.name,
        body.businessCriticality,
        body.defaultCategory,
        *body.keywords
    )

    desk.add_service(user, service)
    return service.to_dict()


@app.post("/api/admin/services/{service_id}/dependencies", status_code=204)
def create_service_dependency(
    service_id: str,
    body: DependencyBody,
    user=Depends(current_user)
):
    desk.add_dependency(
        user, service_id, body.dependsOnId
    )
    return Response(status_code=204)


@app.post("/api/admin/categories", status_code=201)
def create_admin_category(
    body: NewCategoryBody,
    user=Depends(current_user)
):
    desk.add_category(
        user,
        body.name,
        body.keywords,
        body.description
    )
    return {"name": body.name}


# ==================================================
# ADMIN - SLA CONFIGURATION
# ==================================================

@app.post("/api/admin/sla-policies", status_code=201)
def create_admin_sla_policy(
    body: SLAPolicyBody,
    user=Depends(current_user)
):
    policy = SLAPolicy(
        priority=parse_enum(
            Priority, body.priority, "priority"
        ),
        response_target=timedelta(
            minutes=body.responseMinutes
        ),
        resolution_target=timedelta(
            minutes=body.resolutionMinutes
        ),
        warning_threshold=body.warningThreshold,
        service_id=body.serviceId
    )

    desk.configure_sla(user, policy)
    return to_plain(policy)


# ==================================================
# ADMIN - STRATEGY CONFIGURATION
# ==================================================

@app.put("/api/admin/strategies/assignment", status_code=204)
def change_assignment_strategy(
    body: StrategyBody,
    user=Depends(current_user)
):
    desk.set_assignment_strategy(user, body.name)
    return Response(status_code=204)


@app.put("/api/admin/strategies/priority", status_code=204)
def change_priority_strategy(
    body: StrategyBody,
    user=Depends(current_user)
):
    desk.set_priority_strategy(user, body.name)
    return Response(status_code=204)
