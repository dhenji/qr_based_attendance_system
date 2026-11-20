from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import database
from core.security import decode_access_token, extract_user_id

from shared.enums import UserRole

from features.admin.service import AdminService
from features.analytics.service import AnalyticsService
from features.attendance.service import AttendanceService
from features.auth.model import User
from features.auth.service import AuthService
from features.course.service import CourseService
from features.dashboard.service import DashboardService
from features.excuse.service import ExcuseService
from features.face_enrollment.service import FaceEnrollmentService
from features.professor.service import ProfessorService
from features.program.service import ProgramService
from features.reports.service import ReportsService
from features.session.service import SessionService
from features.student.service import StudentService
from features.system.service import SystemService

settings: Settings = get_settings()
security = HTTPBearer(auto_error=False)


async def _get_db() -> AsyncIterator[AsyncSession]:
    async with database.get_session() as session:
        try:
            yield session
            await session.commit()
        except BaseException:
            # Any exception, not just the AppException family. Nothing catches
            # the rest, so it would otherwise escape without an explicit
            # rollback and leave the transaction to be undone implicitly by the
            # pool when the connection is returned.
            await session.rollback()
            raise


async def _get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> User:
    if credentials is None:
        raise _unauthorized("missing_token", "Authentication required")

    payload: dict[str, Any] | None = decode_access_token(
        credentials.credentials, settings
    )

    if payload is None:
        raise _unauthorized("invalid_token", "Invalid or expired token")

    if payload.get("type") is not None:
        raise _unauthorized("invalid_token", "Invalid or expired token")

    try:
        user_id: int = extract_user_id(payload)
    except PyJWTError:
        raise _unauthorized("invalid_token", "Invalid or corrupted token")

    user: User | None = await _get_active_user(session, user_id)

    if user is None:
        raise _unauthorized("user_not_found", "User not found or inactive")

    now: datetime = datetime.now(timezone.utc)
    timeout_seconds: int = _idle_timeout_seconds(user, settings)
    last_activity: datetime | None = user.last_activity_at
    if (
        last_activity is not None
        and timeout_seconds > 0
        and (now - last_activity).total_seconds() > timeout_seconds
    ):
        raise _unauthorized("session_idle", "Session expired due to inactivity")

    # Activity tracking is handled on login/refresh; this check is read-only
    # so it does not mutate rows during request handling.

    # Revoke outstanding tokens when the account's session version moved
    # (logout, password change/reset, MFA disable, admin deactivation).
    token_version: int | None = payload.get("tv")
    if token_version is None or int(token_version) != (user.token_version or 0):
        raise _unauthorized("invalid_token", "Invalid or expired token")

    return user


async def _get_optional_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> User | None:
    if credentials is None or credentials.credentials is None:
        return None

    payload: dict[str, Any] | None = decode_access_token(
        credentials.credentials, settings
    )

    if payload is None or payload.get("type") is not None:
        return None

    try:
        user_id: int = extract_user_id(payload)
    except PyJWTError:
        return None

    user: User | None = await _get_active_user(session, user_id)
    if user is None:
        return None

    now: datetime = datetime.now(timezone.utc)
    timeout_seconds: int = _idle_timeout_seconds(user, settings)
    last_activity: datetime | None = user.last_activity_at
    if (
        last_activity is not None
        and timeout_seconds > 0
        and (now - last_activity).total_seconds() > timeout_seconds
    ):
        raise _unauthorized("session_idle", "Session expired due to inactivity")

    # Activity tracking is handled on login/refresh; this check is read-only
    # so it does not mutate rows during request handling.

    token_version: int | None = payload.get("tv")
    if token_version is None or int(token_version) != (user.token_version or 0):
        return None

    return user


async def _get_active_user(session: AsyncSession, user_id: int) -> User | None:
    user = await session.get(entity=User, ident=user_id)

    return user if user is not None and user.is_active else None


def _idle_timeout_seconds(user: User, settings: Settings) -> int:
    role = user.role
    if role in ("admin", "super_admin"):
        minutes = settings.idle_timeout_minutes_admin
    elif role == "professor":
        minutes = settings.idle_timeout_minutes_professor
    else:
        minutes = settings.idle_timeout_minutes_student
    return int(minutes) * 60


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
    )


def _role_matches(user_role: str, required: UserRole) -> bool:
    """True when ``user_role`` satisfies the ``required`` role.

    ``super_admin`` is a superset of ``admin``: a super_admin passess admin-only checks.
    """

    if user_role == required.value:
        return True

    return user_role == UserRole.SUPER_ADMIN.value and required == UserRole.ADMIN


def require_role(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    async def role_guard(user: Annotated[User, Depends(_get_current_user)]) -> User:
        if not any(_role_matches(user.role, role) for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "insufficient_permissions",
                    "message": "You do not have permissions to access this resource",
                },
            )

        return user

    return role_guard


# The admin guard. Defined once here so every router annotates its actor with
# the same dependency instead of re-spelling the role inside the signature.
AdminUser = Annotated[User, Depends(require_role(UserRole.ADMIN))]


async def _get_auth_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> AuthService:
    return AuthService(session)


async def _get_admin_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> AdminService:
    return AdminService(session)


async def _get_program_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ProgramService:
    return ProgramService(session)


async def _get_course_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> CourseService:
    return CourseService(session)


async def _get_student_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> StudentService:
    return StudentService(session)


async def _get_professor_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ProfessorService:
    return ProfessorService(session)


async def _get_attendance_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> AttendanceService:
    return AttendanceService(session)


async def _get_face_enrollment_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> FaceEnrollmentService:
    return FaceEnrollmentService(session)


async def _get_session_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> SessionService:
    return SessionService(session)


async def _get_excuse_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ExcuseService:
    return ExcuseService(session)


async def _get_analytics_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> AnalyticsService:
    return AnalyticsService(session)


async def _get_reports_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> ReportsService:
    return ReportsService(session)


async def _get_system_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> SystemService:
    return SystemService(session)


async def _get_dashboard_service(
    session: Annotated[AsyncSession, Depends(_get_db)],
) -> DashboardService:
    """The dashboard aggregate, wired to the slices it composes.

    Each dependency builds its service against the *same* session, so one
    request is one transaction: a dashboard read that fails halfway rolls back
    with everything else on the request.
    """

    return DashboardService(
        session,
        student_service=StudentService(session),
        attendance_service=AttendanceService(session),
        session_service=SessionService(session),
        analytics_service=AnalyticsService(session),
        reports_service=ReportsService(session),
        system_service=SystemService(session),
        program_service=ProgramService(session),
    )


AuthServiceDep = Annotated[AuthService, Depends(_get_auth_service)]
AdminServiceDep = Annotated[AdminService, Depends(_get_admin_service)]
ProgramServiceDep = Annotated[ProgramService, Depends(_get_program_service)]
CourseServiceDep = Annotated[CourseService, Depends(_get_course_service)]
StudentServiceDep = Annotated[StudentService, Depends(_get_student_service)]
ProfessorServiceDep = Annotated[ProfessorService, Depends(_get_professor_service)]
SessionServiceDep = Annotated[SessionService, Depends(_get_session_service)]
AttendanceServiceDep = Annotated[AttendanceService, Depends(_get_attendance_service)]
ExcuseServiceDep = Annotated[ExcuseService, Depends(_get_excuse_service)]
AnalyticsServiceDep = Annotated[AnalyticsService, Depends(_get_analytics_service)]
ReportsServiceDep = Annotated[ReportsService, Depends(_get_reports_service)]
SystemServiceDep = Annotated[SystemService, Depends(_get_system_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(_get_dashboard_service)]


FaceEnrollmentServiceDep = Annotated[
    FaceEnrollmentService, Depends(_get_face_enrollment_service)
]

CurrentUserDep = Annotated[User, Depends(_get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(_get_optional_current_user)]
