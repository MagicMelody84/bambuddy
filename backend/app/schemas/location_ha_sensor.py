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
    alert_above: float | None = None
    alert_below: float | None = None

    notify_on_alert: bool = False
    show_on_card: bool = True
    sort_order: int = Field(default=0, ge=0, le=999)

    @model_validator(mode="after")
    def validate_kind_matches_entity(self) -> "LocationHASensorBase":
        domain = self.entity_id.split(".")[0]
        expected = "binary" if domain == "binary_sensor" else "numeric"
        if self.kind != expected:
            raise ValueError(f"kind must be '{expected}' for a {domain} entity")

        if self.kind == "binary" and (self.alert_above is not None or self.alert_below is not None):
            raise ValueError("alert_above/alert_below only apply to numeric sensors")
        if self.kind == "numeric" and self.alert_state is not None:
            raise ValueError("alert_state only applies to binary sensors")
        if self.alert_above is not None and self.alert_below is not None and self.alert_below >= self.alert_above:
            raise ValueError("alert_below must be lower than alert_above")

        if self.notify_on_alert and not self._has_alert_condition():
            raise ValueError("notify_on_alert requires an alert condition")
        return self

    def _has_alert_condition(self) -> bool:
        return self.alert_state is not None or self.alert_above is not None or self.alert_below is not None


class LocationHASensorCreate(LocationHASensorBase):
    pass


class LocationHASensorUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    entity_id: str | None = Field(default=None, pattern=r"^(binary_sensor|sensor)\.[a-z0-9_]+$")
    kind: Literal["binary", "numeric"] | None = None
    device_class: str | None = Field(default=None, max_length=32)
    unit: str | None = Field(default=None, max_length=16)
    alert_state: Literal["on", "off"] | None = None
    alert_above: float | None = None
    alert_below: float | None = None
    notify_on_alert: bool | None = None
    show_on_card: bool | None = None
    sort_order: int | None = Field(default=None, ge=0, le=999)


class LocationHASensorResponse(LocationHASensorBase):
    id: int
    last_state: str | None = None
    last_changed: datetime | None = None
    last_checked: datetime | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class LocationHASensorReading(BaseModel):
    id: int
    name: str
    entity_id: str
    kind: str
    device_class: str | None = None
    unit: str | None = None
    state: str | None = None
    value: float | None = None
    alerting: bool = False
    reachable: bool = True
    last_changed: datetime | None = None
