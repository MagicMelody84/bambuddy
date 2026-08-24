"""Schemas for Home Assistant entities bound to a storage location (#2824)."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from backend.app.schemas.printer_ha_sensor import HADisplayEntity  # noqa: F401


class LocationHASensorBase(BaseModel):
    location_id: int
    name: str = Field(..., min_length=1, max_length=100)
    entity_id: str = Field(..., pattern=r"^(binary_sensor|sensor)\.[a-z0-9_]+$")
    kind: Literal["binary", "numeric"] = "binary"
    device_class: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)

    alert_state: Literal["on", "off"] | None = None
    # allow_inf_nan=False: pydantic's lax mode coerces the strings "nan"/"inf"
    # into real NaN/Infinity floats. A NaN threshold satisfies the "notify
    # needs an alert condition" rule below yet every comparison against it is
    # False — a notification that can never fire — and it skips the
    # below-vs-above ordering check the same way. Responses serialize NaN as
    # null, so the UI would show an empty field over a poisoned row.
    alert_above: float | None = Field(default=None, allow_inf_nan=False)
    alert_below: float | None = Field(default=None, allow_inf_nan=False)

    notify_on_alert: bool = False
    show_on_card: bool = True
    sort_order: int = Field(default=0, ge=0, le=999)

    @model_validator(mode="after")
    def validate_kind_matches_entity(self) -> "LocationHASensorBase":
        domain = self.entity_id.split(".")[0]
        expected = "binary" if domain == "binary_sensor" else "numeric"
        if self.kind != expected:
            raise ValueError(f"kind must be '{expected}' for a {domain} entity")

        # Alert fields are per-kind: a threshold on a battery sensor and an
        # on/off alert on a temperature reading are both configuration the
        # poller would silently ignore, so reject them at the edge instead.
        if self.kind == "binary" and (self.alert_above is not None or self.alert_below is not None):
            raise ValueError("alert_above/alert_below only apply to numeric sensors")
        if self.kind == "numeric" and self.alert_state is not None:
            raise ValueError("alert_state only applies to binary sensors")
        if self.alert_above is not None and self.alert_below is not None and self.alert_below >= self.alert_above:
            raise ValueError("alert_below must be lower than alert_above")

        # A notification with nothing to trigger on would never fire — that
        # reads as a broken feature, not as a no-op.
        if self.notify_on_alert and not self._has_alert_condition():
            raise ValueError("notify_on_alert requires an alert condition")
        return self

    def _has_alert_condition(self) -> bool:
        return self.alert_state is not None or self.alert_above is not None or self.alert_below is not None


class LocationHASensorCreate(LocationHASensorBase):
    pass


class LocationHASensorUpdate(BaseModel):
    """Partial update. Validated against the merged row in the route, because
    the per-kind rules above need fields this payload may not carry."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    entity_id: str | None = Field(default=None, pattern=r"^(binary_sensor|sensor)\.[a-z0-9_]+$")
    kind: Literal["binary", "numeric"] | None = None
    device_class: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)
    alert_state: Literal["on", "off"] | None = None
    # Same allow_inf_nan story as the base schema. The route's merged-row
    # re-validation would catch these too, but rejecting them here keeps the
    # error attached to the offending field.
    alert_above: float | None = Field(default=None, allow_inf_nan=False)
    alert_below: float | None = Field(default=None, allow_inf_nan=False)
    notify_on_alert: bool | None = None
    show_on_card: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=999)


class LocationHASensorResponse(LocationHASensorBase):
    # Reads must tolerate what writes now reject: a row that got a NaN/inf
    # threshold in before allow_inf_nan landed would otherwise fail response
    # validation and 500 the whole list for one legacy row. Serialization
    # turns them into null, which is also what the edit form should show.
    alert_above: float | None = None
    alert_below: float | None = None

    id: int
    last_state: str | None = None
    last_changed: datetime | None = None
    last_checked: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LocationHASensorReading(BaseModel):
    """One sensor's live state, as the filament card and inventory table render it."""

    id: int
    name: str
    entity_id: str
    kind: str
    device_class: str | None = None
    unit: str | None = None
    # Raw HA state: "on"/"off" for binary, the numeric string for sensors.
    # None when the entity is unavailable or has not been polled yet.
    state: str | None = None
    value: float | None = None  # numeric sensors only, parsed from state
    alerting: bool = False
    reachable: bool = True
    alert_state: str | None = None
    alert_above: float | None = None
    alert_below: float | None = None
    last_changed: datetime | None = None
    # Lets a consumer that fetched the unfiltered (show_on_card=False) list
    # still pick out the card-visible subset itself, instead of issuing a
    # second request for the same location.
    show_on_card: bool = True
