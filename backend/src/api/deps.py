from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Annotated, Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import database
from core.security import decode_access_token, extract_user_id
from features.admin.service import AdminService
from features.analytics.service import AnalyticsService
from features.attendance.service import AttendanceService
from features.auth.model import User
from features.auth.service import AuthService
from features.course.service import CourseService
from features.excuse.service import ExcuseService
from features.face_enrollment.service import FaceEnrollmentService
from features.professor.service import ProfessorService
from features.program.service import ProgramService
from features.session.service import SessionService
from features.student.service import StudentService
from shared.enums import UserRole

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

    return await _get_active_user(session, user_id)


async def _get_active_user(session: AsyncSession, user_id: int) -> User | None:
    user = await session.get(entity=User, ident=user_id)

    return user if user is not None and user.is_active else None


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


FaceEnrollmentServiceDep = Annotated[
    FaceEnrollmentService, Depends(_get_face_enrollment_service)
]

CurrentUserDep = Annotated[User, Depends(_get_current_user)]
OptionalUserDep = Annotated[User | None, Depends(_get_optional_current_user)]
