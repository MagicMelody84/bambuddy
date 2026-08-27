"""Shared helpers for normalizing RFID tag and tray identifiers."""


def normalize_hex(value: str | None) -> str:
    if not value:
        return ""
    hex_chars = "".join(ch for ch in str(value).strip() if ch in "0123456789abcdefABCDEF")
    return hex_chars.upper()


def normalize_tag_uid(value: str | None) -> str:
    uid = normalize_hex(value)
    # DB column is VARCHAR(16), so keep the least-significant bytes if longer.
    if len(uid) > 16:
        uid = uid[-16:]
    return uid


def normalize_location_tag_uid(value: str | None) -> str:
    uid = normalize_hex(value)
    # Location.tag_uid is VARCHAR(32) — wider than Spool.tag_uid's VARCHAR(16),
    # so this can't reuse normalize_tag_uid's 16-char truncation without
    # losing distinguishing characters from a legitimately longer UID.
    if len(uid) > 32:
        uid = uid[-32:]
    return uid


def normalize_tray_uuid(value: str | None) -> str:
    uuid = normalize_hex(value)
    # DB column is VARCHAR(32). Keep canonical 32-char UUID when possible.
    if len(uuid) >= 32:
        uuid = uuid[:32]
    return uuid
