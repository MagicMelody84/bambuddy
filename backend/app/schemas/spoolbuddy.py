import ipaddress
import json
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# --- Device schemas ---


def validate_device_ip(value: str | None) -> str | None:
    """Accept only a literal IP address for a device's ``ip_address``.

    The value is not just displayed: the Settings page builds
    ``http://<ip_address>`` and embeds it in an iframe, and the SSH updater
    connects to it. A hostname or URL fragment here would let a registered
    device point that frame at an arbitrary origin, so the field is held to
    what its name promises. ``ipaddress`` also rejects the numeric-encoded
    forms (``2130706433``, ``0x7f000001``) that browsers still resolve — see
    the same reasoning in ``_url_safety.py``.

    Devices legitimately live on the LAN, so private and loopback addresses
    are fine; only the "this is not an IP at all" case is refused.
    """
    if value is None:
        return None
    candidate = value.strip()
    if not candidate:
        return None
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        raise ValueError("ip_address must be an IPv4 or IPv6 address") from None
    return candidate


class DeviceRegisterRequest(BaseModel):
    device_id: str = Field(..., min_length=1, max_length=50)
    hostname: str = Field(..., min_length=1, max_length=100)
    ip_address: str = Field(..., min_length=1, max_length=45)
    firmware_version: str | None = Field(None, max_length=20)
    has_nfc: bool = True
    has_scale: bool = True
    tare_offset: int = 0
    calibration_factor: float = 1.0
    nfc_reader_type: str | None = Field(None, max_length=20)
    nfc_connection: str | None = Field(None, max_length=20)
    backend_url: str | None = Field(None, max_length=255)
    has_backlight: bool = False
    hardware_variant: Literal["standard", "lite"] = "standard"

    @field_validator("ip_address")
    @classmethod
    def _validate_ip_address(cls, v: str) -> str:
        validated = validate_device_ip(v)
        if validated is None:
            raise ValueError("ip_address must be an IPv4 or IPv6 address")
        return validated


class DeviceResponse(BaseModel):
    id: int
    device_id: str
    hostname: str
    ip_address: str
    firmware_version: str | None = None
    has_nfc: bool
    has_scale: bool
    tare_offset: int
    calibration_factor: float
    nfc_reader_type: str | None = None
    nfc_connection: str | None = None
    backend_url: str | None = None
    display_brightness: int = 100
    display_blank_timeout: int = 0
    has_backlight: bool = False
    hardware_variant: Literal["standard", "lite"] = "standard"
    last_calibrated_at: datetime | None = None
    last_seen: datetime | None = None
    pending_command: str | None = None
    nfc_ok: bool
    scale_ok: bool
    uptime_s: int
    update_status: str | None = None
    update_message: str | None = None
    system_stats: dict | None = None
    online: bool = False
    ssh_public_key: str | None = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class HeartbeatRequest(BaseModel):
    nfc_ok: bool = False
    scale_ok: bool = False
    uptime_s: int = 0
    firmware_version: str | None = Field(None, max_length=20)
    ip_address: str | None = Field(None, max_length=45)
    nfc_reader_type: str | None = Field(None, max_length=20)
    nfc_connection: str | None = Field(None, max_length=20)
    backend_url: str | None = Field(None, max_length=255)
    system_stats: dict | None = None

    @field_validator("ip_address")
    @classmethod
    def _validate_ip_address(cls, v: str | None) -> str | None:
        # Same rule as registration: the heartbeat can move a device's address,
        # so it is the second way an unvalidated value reaches the iframe.
        return validate_device_ip(v)

    @field_validator("system_stats")
    @classmethod
    def _limit_system_stats_size(cls, v: dict | None) -> dict | None:
        if v is not None and len(json.dumps(v)) > 4096:
            raise ValueError("system_stats must not exceed 4096 bytes when JSON-encoded")
        return v


class HeartbeatResponse(BaseModel):
    pending_command: str | None = None
    pending_write_payload: dict | None = None
    pending_system_payload: dict | None = None
    tare_offset: int
    calibration_factor: float
    display_brightness: int = 100
    display_blank_timeout: int = 0
    ssh_public_key: str | None = None


# --- NFC schemas ---


class TagScannedRequest(BaseModel):
    device_id: str = Field(..., max_length=50)
    tag_uid: str = Field(..., max_length=32)
    tray_uuid: str | None = Field(None, max_length=32, pattern=r"^[0-9A-Fa-f]*$")
    sak: int | None = None
    tag_type: str | None = Field(None, max_length=50)
    raw_blocks: dict | None = None


class TagRemovedRequest(BaseModel):
    device_id: str = Field(..., max_length=50)
    tag_uid: str = Field(..., max_length=32)


# --- Scale schemas ---


class ScaleReadingRequest(BaseModel):
    device_id: str = Field(..., max_length=50)
    weight_grams: float = Field(..., allow_inf_nan=False)
    stable: bool = False
    raw_adc: int | None = None


class UpdateSpoolWeightRequest(BaseModel):
    spool_id: int = Field(..., gt=0)
    weight_grams: float = Field(..., allow_inf_nan=False, ge=0.0, le=100_000.0)


# --- Calibration schemas ---


class SetTareRequest(BaseModel):
    tare_offset: int


class SetCalibrationFactorRequest(BaseModel):
    known_weight_grams: float = Field(..., gt=0)
    raw_adc: int
    tare_raw_adc: int | None = None


class CalibrationResponse(BaseModel):
    tare_offset: int
    calibration_factor: float


# --- Display schemas ---


class WriteTagRequest(BaseModel):
    device_id: str = Field(..., max_length=50)
    spool_id: int = Field(..., gt=0)


class WriteTagResultRequest(BaseModel):
    device_id: str = Field(..., max_length=50)
    spool_id: int = Field(..., gt=0)
    tag_uid: str = Field(..., min_length=8, max_length=30, pattern=r"^[0-9A-Fa-f]+$")
    success: bool
    message: str | None = Field(None, max_length=500)


class DisplaySettingsRequest(BaseModel):
    brightness: int = Field(ge=0, le=100)
    blank_timeout: int = Field(ge=0)


class SystemConfigRequest(BaseModel):
    backend_url: str = Field(..., min_length=1, max_length=255)
    api_key: str | None = Field(default=None, max_length=255)


class SystemCommandRequest(BaseModel):
    command: str = Field(
        ..., max_length=50, description="System command: reboot, shutdown, restart_daemon, restart_browser"
    )


class SystemCommandResultRequest(BaseModel):
    command: str = Field(..., max_length=50)
    success: bool
    message: str | None = Field(None, max_length=500)


class UpdateStatusRequest(BaseModel):
    status: Literal["updating", "complete", "error"]
    message: str | None = Field(None, max_length=255)


# --- Diagnostics schemas ---


class DiagnosticResultRequest(BaseModel):
    diagnostic: str = Field(..., max_length=50, description="Diagnostic type: 'nfc', 'scale', or 'read_tag'")
    success: bool
    output: str = Field(..., max_length=10_000)
    exit_code: int = Field(..., ge=-255, le=255)
