from typing import Any

from sqlalchemy import JSON, BigInteger, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from core.database import Base
from shared.enums import SyncStatus
from shared.mixins import CreatedAtMixin


class SyncQueue(CreatedAtMixin, Base):
    __tablename__ = "sync_queue"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    record_data: Mapped[dict[str, Any]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), server_default=SyncStatus.PENDING.value, index=True
    )
    retry_count: Mapped[int] = mapped_column(Integer, server_default="0")
