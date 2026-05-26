from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, declared_attr, mapped_column


class IdMixin:
    id: Mapped[UUID] = mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )


class TimestampsMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class TableNameMixin:
    @declared_attr.directive
    def __tablename__(cls) -> str:  # type: ignore[override]
        # CamelCase → snake_case + plural ('s' suffix; override per-model if needed)
        import re

        name = re.sub(r"(?<!^)(?=[A-Z])", "_", cls.__name__).lower()
        return name if name.endswith("s") else f"{name}s"
