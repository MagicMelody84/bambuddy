from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.app.core.database import Base


class SpoolCustomFieldValue(Base):
    """One custom-field value on one spool.

    The FK lives here rather than as a ``custom_id`` on ``spool`` because a
    spool carries many values — same shape as ``spool_k_profile``.
    """

    __tablename__ = "spool_custom_field_values"
    __table_args__ = (UniqueConstraint("spool_id", "field_id", name="uq_spool_custom_field"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    spool_id: Mapped[int] = mapped_column(ForeignKey("spool.id", ondelete="CASCADE"), index=True)
    field_id: Mapped[int] = mapped_column(ForeignKey("custom_fields.id", ondelete="CASCADE"), index=True)
    value: Mapped[str | None] = mapped_column(String(255), nullable=True)

    spool: Mapped["Spool"] = relationship(back_populates="custom_values")
    # selectin so Spool.custom_fields can read the key without an async lazy load.
    field: Mapped["CustomField"] = relationship(back_populates="values", lazy="selectin")


from backend.app.models.custom_field import CustomField  # noqa: E402
from backend.app.models.spool import Spool  # noqa: E402
