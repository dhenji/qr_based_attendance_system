from __future__ import annotations

from shared.enums import UserRole


def _role(value: UserRole | str | None) -> UserRole | None:
    if value is None:
        return None
    if isinstance(value, UserRole):
        return value
    return UserRole(value)


def _is_super_admin(role: UserRole | str | None) -> bool:
    return _role(role) == UserRole.SUPER_ADMIN


def can_manage_users(actor_role: UserRole | str | None) -> bool:
    """Whether the actor may access the user-management surface at all."""
    role = _role(actor_role)
    return role in {UserRole.SUPER_ADMIN, UserRole.ADMIN}


def can_view_target(actor_role: UserRole | str | None, target_role: UserRole | str | None) -> bool:
    """Whether the actor may see a target account in lists/details."""
    actor = _role(actor_role)
    target = _role(target_role)
    if actor == UserRole.SUPER_ADMIN:
        return True
    if actor == UserRole.ADMIN:
        return target != UserRole.SUPER_ADMIN
    return False


def can_manage_target(actor_role: UserRole | str | None, target_role: UserRole | str | None) -> bool:
    """Whether the actor may mutate (deactivate/reactivate/reset/lockout-mutate) a target."""
    actor = _role(actor_role)
    target = _role(target_role)
    if actor == UserRole.SUPER_ADMIN:
        return True
    if actor == UserRole.ADMIN:
        return target in {UserRole.PROFESSOR, UserRole.STUDENT}
    return False


def can_assign_role(actor_role: UserRole | str | None, role_to_assign: UserRole | str | None) -> bool:
    """Whether the actor may create an account with the given role."""
    actor = _role(actor_role)
    role = _role(role_to_assign)
    if actor == UserRole.SUPER_ADMIN:
        return role in {UserRole.ADMIN, UserRole.PROFESSOR, UserRole.STUDENT}
    if actor == UserRole.ADMIN:
        return role in {UserRole.PROFESSOR, UserRole.STUDENT}
    return False


def hide_sensitive_fields(
    actor_role: UserRole | str | None,
    target_role: UserRole | str | None,
    *,
    is_self: bool = False,
    actor_id: int | None = None,
    target_id: int | None = None,
) -> bool:
    """Whether email/name fields must be omitted for this actor->target view."""
    if is_self:
        return False
    if actor_id is not None and target_id is not None and actor_id == target_id:
        return False
    actor = _role(actor_role)
    target = _role(target_role)
    return actor == UserRole.ADMIN and target == UserRole.ADMIN


def can_read_lockout(actor_role: UserRole | str | None, target_role: UserRole | str | None) -> bool:
    return can_view_target(actor_role, target_role)


def can_mutate_lockout(actor_role: UserRole | str | None, target_role: UserRole | str | None) -> bool:
    return can_manage_target(actor_role, target_role)
