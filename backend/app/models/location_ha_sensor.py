from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class LocationHASensor(Base):
    __tablename__ = "location_ha_sensors"

    id: Mapped[int] = mapped_column(primary_key=True)
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id", ondelete="CASCADE"), index=True)

    name: Mapped[str] = mapped_column(String(100))
    entity_id: Mapped[str] = mapped_column(String(255))

    kind: Mapped[str] = mapped_column(String(16), default="binary")

    device_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    unit: Mapped[str | None] = mapped_column(String(16), nullable=True)

    alert_state: Mapped[str | None] = mapped_column(String(8), nullable=True)
    alert_above: Mapped[float | None] = mapped_column(Float, nullable=True)
    alert_below: Mapped[float | None] = mapped_column(Float, nullable=True)

    notify_on_alert: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")

    show_on_card: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")

    last_state: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_changed: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_checked: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())

    location: Mapped["Location"] = relationship(back_populates="ha_sensors")


from backend.app.models.location import Location  # noqa: E402
