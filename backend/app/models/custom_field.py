from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class CustomField(Base):
    """User-defined extra field for filament spools.

    Definition only — the per-spool values live in ``SpoolCustomFieldValue``.
    Splitting the two mirrors ``locations`` / ``spool.location_id``: renaming a
    field touches one row, and a spool can carry as many fields as the user
    defines.
    """

    __tablename__ = "custom_fields"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Stable slug, never changes after creation. Used as the value-lookup key in
    # the API payload and — prefixed — as the Spoolman `extra` key, so renaming
    # the display name must not touch it or Spoolman-side values orphan.
    key: Mapped[str] = mapped_column(String(50), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # text | number | boolean | date | datetime | select — see
    # custom_field_service.SUPPORTED_FIELD_TYPES. Governs parsing and the form
    # widget; every value is stored as its canonical string either way.
    field_type: Mapped[str] = mapped_column(String(20), default="text", server_default="text")
    # Allowed values, as a JSON list of strings. Only select fields have any.
    options: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    values: Mapped[list["SpoolCustomFieldValue"]] = relationship(back_populates="field", cascade="all, delete-orphan")


from backend.app.models.spool_custom_field_value import SpoolCustomFieldValue  # noqa: E402
