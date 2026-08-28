from typing import Annotated, AsyncIterator, Awaitable, Callable

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import PyJWTError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import Settings, get_settings
from core.database import database
from core.security import decode_access_token, extract_user_id
from features.auth.model import User
from shared.enums import UserRole

security = HTTPBearer(auto_error=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with database.get_session() as session:
        yield session


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(security)],
    session: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    if credentials is None:
        raise _unauthorized("missing_token", "Authentication required")

    settings: Settings = get_settings()

    try:
        payload: dict = decode_access_token(credentials.credentials, settings)
        user_id: int = extract_user_id(payload)
    except PyJWTError:
        raise _unauthorized("invalid_token", "Invalid or expired token")

    user: User | None = await _get_active_user(session, user_id)

    if user is None:
        raise _unauthorized("user_not_found", "User not found or inactive")

    return user


async def _get_active_user(session: AsyncSession, user_id: int) -> User | None:
    user = await session.get(entity=User, ident=user_id)

    return user if user is not None and user.is_active else None


def _unauthorized(code: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"code": code, "message": message},
    )


def require_role(*roles: UserRole) -> Callable[..., Awaitable[User]]:
    async def role_guard(user: Annotated[User, Depends(get_current_user)]) -> User:
        if user.role not in {role.value for role in roles}:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "insufficient_permissions",
                    "message": "You do not have permissions to access this resource",
                },
            )

        return user

    return role_guard
