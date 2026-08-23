from datetime import datetime

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.services.custom_field_service import (
    DEFAULT_FIELD_TYPE,
    MAX_SORT_ORDER,
    normalize_field_name,
    normalize_field_type,
    normalize_options,
)


class CustomFieldCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    field_type: str = Field(default=DEFAULT_FIELD_TYPE)
    # Only meaningful for select fields; rejected on every other type.
    options: list[str] = Field(default_factory=list)
    sort_order: int = Field(default=0, ge=0, le=MAX_SORT_ORDER)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return normalize_field_name(v)

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str) -> str:
        return normalize_field_type(v)

    @model_validator(mode="after")
    def validate_options_against_type(self) -> "CustomFieldCreate":
        # Options can only be checked once the type is known, so this runs as a
        # model validator rather than a field one.
        self.options = normalize_options(self.options, self.field_type)
        return self


class CustomFieldUpdate(BaseModel):
    """Partial update.

    `key` is deliberately absent — it is the stable link to the stored values
    (and to the Spoolman `extra` entry), so only the presentation changes here.
    `field_type` may change only while no spool carries a value; the route
    enforces that, since it needs the usage count.
    """

    name: str | None = Field(default=None, min_length=1, max_length=100)
    field_type: str | None = None
    options: list[str] | None = None
    sort_order: int | None = Field(default=None, ge=0, le=MAX_SORT_ORDER)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_field_name(v)

    @field_validator("field_type")
    @classmethod
    def validate_field_type(cls, v: str | None) -> str | None:
        if v is None:
            return None
        return normalize_field_type(v)


class CustomFieldResponse(BaseModel):
    id: int
    key: str
    name: str
    field_type: str
    options: list[str] = []
    sort_order: int = 0
    # How many spools currently carry a value for this field. Drives the delete
    # confirmation and gates whether the type can still be changed.
    value_count: int = 0
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
