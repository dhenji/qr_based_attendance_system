from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from shared.enums import AuditAction, AuditEntity

from features.system.model import AuditLog


async def record_audit(
    session: AsyncSession,
    *,
    actor_id: int | None,
    action: AuditAction,
    entity_type: AuditEntity,
    entity_id: int | None,
    old_value: dict[str, Any] | None = None,
    new_value: dict[str, Any] | None = None,
) -> AuditLog:
    """Persist one audit trail row in the caller's transaction.

    Flushes (never commits): the row rolls back with the mutation when the
    request fails, and commits with it when the request succeeds.

    `actor_id` is `None` when nobody was authenticated — a lockout triggered by
    an anonymous attempt, or a cron run. The subject is still identified by
    `entity_type` + `entity_id`.
    """
    row = AuditLog(
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        old_value=old_value,
        new_value=new_value,
        performed_by=actor_id,
    )
    session.add(row)
    await session.flush()
    return row
