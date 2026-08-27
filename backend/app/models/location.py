from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base

if TYPE_CHECKING:
    from backend.app.models.location_ha_sensor import LocationHASensor
    from backend.app.models.spool import Spool


class Location(Base):
    """Physical storage location for filament spools (shelf, drawer, drybox, etc.)."""

    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    # Case-insensitive uniqueness — LOWER(TRIM(name)); enforced via migration index.
    name_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    # RFID/NFC tag UID for the physical shelf/drawer, mirrors Spool.tag_uid.
    # Unique: a scan resolves through /locations/by-tag, which answers with one
    # row, so a UID on two shelves would make that pick silently. NULLs stay
    # distinct in both SQLite and PostgreSQL, so untagged locations are fine.
    # Upgraded databases get the same index from
    # _migrate_location_tag_uid_unique, under this same (default) name.
    tag_uid: Mapped[str | None] = mapped_column(String(32), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    spools: Mapped[list["Spool"]] = relationship(back_populates="location")
    ha_sensors: Mapped[list["LocationHASensor"]] = relationship(back_populates="location", cascade="all, delete-orphan")
