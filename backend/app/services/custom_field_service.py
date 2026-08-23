"""User-defined custom fields for spools — single write path for definitions and values.

Definitions live in ``custom_fields``, values in ``spool_custom_field_values``.
Both inventory backends speak the same flat ``{key: value}`` payload: the local
one persists it as value rows, the Spoolman one mirrors it into the spool's
``extra`` dict under the ``bambu_cf_`` prefix.
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime

from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.custom_field import CustomField
from backend.app.models.spool_custom_field_value import SpoolCustomFieldValue

logger = logging.getLogger(__name__)

DUPLICATE_FIELD_KEY = "A custom field with this name already exists"

# What a field can hold. Deliberately the same set, in the same order, as
# Spoolman's own extra-field types, so a value means the same thing on both
# sides and nothing has to be approximated when it is mirrored across.
#
# Values are always persisted as their canonical string form in a single
# VARCHAR column — the type governs how that string is parsed on the way in and
# which widget the form renders, not how it is stored. Ranges are stored as
# "min,max".
SUPPORTED_FIELD_TYPES = (
    "text",
    "integer",
    "integer_range",
    "float",
    "float_range",
    "datetime",
    "boolean",
    "choice",
)
DEFAULT_FIELD_TYPE = "text"

# Only these carry an option list; for every other type an option list is a
# mistake, so it is rejected rather than silently dropped.
TYPES_WITH_OPTIONS = frozenset({"choice"})

RANGE_TYPES = frozenset({"integer_range", "float_range"})

MAX_OPTIONS = 50
MAX_OPTION_LENGTH = 100
MAX_VALUE_LENGTH = 255
# PostgreSQL's INTEGER tops out at 2^31-1; anything near that is nonsense for a
# display order anyway, and an unbounded value would be a 500 on Postgres while
# SQLite silently accepted it.
MAX_SORT_ORDER = 100_000

# Prefix under which values are stored in a Spoolman spool's `extra` dict,
# matching the existing bambu_slicer_filament / bambu_color_name convention.
SPOOLMAN_EXTRA_PREFIX = "bambu_cf_"

_KEY_SANITIZE_RE = re.compile(r"[^a-z0-9]+")
# Control characters carry no meaning in any of these strings and PostgreSQL
# refuses to store a NUL at all ("A string literal cannot contain NUL (0x00)
# characters"), which would turn a stray paste into a 500. Stripped everywhere
# rather than rejected: a trailing \r from a copy-paste should not be an error.
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")
# ASCII-only numeric forms. Python's int()/float() also accept underscores
# ("1_0" -> 10) and non-ASCII digits ("١٢" -> 12); both would silently store
# something other than what the user typed.
_INTEGER_RE = re.compile(r"^[+-]?[0-9]+$")
_FLOAT_RE = re.compile(r"^[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?$")


def strip_control_chars(value: str) -> str:
    return _CONTROL_CHARS_RE.sub("", value)


def normalize_field_name(name: str) -> str:
    trimmed = strip_control_chars(name).strip()
    if not trimmed:
        raise ValueError("name must not be empty")
    return trimmed


def normalize_field_key(name: str) -> str:
    """Derive the stable slug from a display name.

    Lowercase ASCII, non-alphanumerics collapsed to underscores. The key ends up
    in a Spoolman `extra` key, so it has to stay ASCII — which means a name
    written entirely in Arabic, Cyrillic, Chinese, Japanese or Korean slugs to
    nothing. Those fall back to a digest of the name rather than being refused:
    the app ships in thirteen languages, and rejecting "客户" would make the
    feature unusable for most of them. The digest is deterministic, so the same
    name always yields the same key.
    """
    normalized = normalize_field_name(name)
    slug = _KEY_SANITIZE_RE.sub("_", normalized.lower()).strip("_")
    if not slug:
        return "field_" + hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]
    return slug[:50].rstrip("_")


def normalize_field_type(field_type: str | None) -> str:
    resolved = (field_type or DEFAULT_FIELD_TYPE).strip().lower()
    if resolved not in SUPPORTED_FIELD_TYPES:
        raise ValueError(f"unsupported field type '{resolved}'")
    return resolved


def normalize_options(options: list[str] | None, field_type: str) -> list[str]:
    """Validate and de-duplicate the option list for *field_type*.

    Types that take no options must be given none — an option list on a text
    field would look configured but never be shown to anyone.
    """
    if field_type not in TYPES_WITH_OPTIONS:
        if options:
            raise ValueError(f"a '{field_type}' field does not take options")
        return []
    if not options:
        raise ValueError("a choice field needs at least one option")
    cleaned: list[str] = []
    for raw in options:
        option = strip_control_chars(raw or "").strip()
        if not option:
            continue
        if len(option) > MAX_OPTION_LENGTH:
            raise ValueError(f"option '{option[:20]}…' exceeds {MAX_OPTION_LENGTH} characters")
        if option not in cleaned:
            cleaned.append(option)
    if not cleaned:
        raise ValueError("a choice field needs at least one option")
    if len(cleaned) > MAX_OPTIONS:
        raise ValueError(f"a custom field accepts at most {MAX_OPTIONS} options")
    return cleaned


_TRUE_TOKENS = frozenset({"true", "1", "yes", "y", "on", "ja"})
_FALSE_TOKENS = frozenset({"false", "0", "no", "n", "off", "nein"})


def _parse_number(raw: str, *, integer: bool, label: str) -> int | float:
    """Parse one numeric token, accepting a comma decimal separator.

    Matched against an explicit ASCII pattern first: ``int("1_0")`` is 10 and
    ``int("١٢")`` is 12, so handing the raw string to Python would store a
    number the user never typed.
    """
    candidate = raw.strip() if integer else raw.strip().replace(",", ".")
    if integer:
        if not _INTEGER_RE.match(candidate):
            raise ValueError(f"'{raw}' is not a whole number ({label})")
        return int(candidate, 10)
    if not _FLOAT_RE.match(candidate):
        raise ValueError(f"'{raw}' is not a number ({label})")
    parsed = float(candidate)
    if parsed != parsed or parsed in (float("inf"), float("-inf")):
        raise ValueError(f"'{raw}' is not a finite number ({label})")
    return parsed


def _coerce_range(value: str, *, integer: bool, label: str) -> str:
    """Parse "min,max" (or whitespace-separated) into the canonical "min,max" form.

    The comma is the separator here, so decimals in a float range must use a
    dot — "0,5" would otherwise be indistinguishable from a two-part range.
    """
    parts = value.split(",") if "," in value else value.split()
    if len(parts) != 2:
        raise ValueError(f"'{value}' is not a range in 'min,max' form ({label})")
    low = _parse_number(parts[0], integer=integer, label=label)
    high = _parse_number(parts[1], integer=integer, label=label)
    if low > high:
        raise ValueError(f"the lower bound must not exceed the upper bound ({label})")
    return f"{low},{high}"


def parse_range(value: str) -> tuple[str, str]:
    """Split a stored range back into its two bounds; ("", "") when unparseable."""
    parts = value.split(",")
    if len(parts) != 2:
        return ("", "")
    return (parts[0].strip(), parts[1].strip())


def coerce_value(value: str, definition: CustomField) -> str:
    """Parse a raw input string into the canonical stored form for its type.

    Raises ValueError with a user-facing message when the input does not fit
    the type. The canonical form is what gets compared, sorted and round-tripped
    through Spoolman, so normalising here (rather than at the edges) keeps every
    caller consistent.
    """
    label = definition.name
    field_type = definition.field_type

    if field_type == "integer":
        return str(_parse_number(value, integer=True, label=label))

    if field_type == "float":
        return str(_parse_number(value, integer=False, label=label))

    if field_type in RANGE_TYPES:
        return _coerce_range(value, integer=field_type == "integer_range", label=label)

    if field_type == "boolean":
        lowered = value.lower()
        if lowered in _TRUE_TOKENS:
            return "true"
        if lowered in _FALSE_TOKENS:
            return "false"
        raise ValueError(f"'{value}' is not a yes/no value ({label})")

    if field_type == "datetime":
        # Accept the trailing Z that browsers and APIs emit; fromisoformat only
        # learned it in 3.11 and the input may come from anywhere.
        candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
        try:
            return datetime.fromisoformat(candidate).isoformat()
        except ValueError:
            raise ValueError(f"'{value}' is not a timestamp in ISO 8601 form ({label})") from None

    if field_type == "choice":
        if value not in (definition.options or []):
            raise ValueError(f"'{value}' is not an option of custom field '{label}'")
        return value

    # text
    return value


def spoolman_extra_key(key: str) -> str:
    """Spoolman `extra` key for a custom field."""
    return f"{SPOOLMAN_EXTRA_PREFIX}{key}"


def spoolman_field_type(field_type: str) -> str:
    """Which Spoolman extra-field type to register a custom field as.

    The two vocabularies are deliberately identical, so this is the identity
    map — except for `choice`. Spoolman freezes a choice field's allowed values
    at registration and Bambuddy's `ensure_extra_field` never rewrites an
    existing field, so a `choice` registration would start rejecting writes the
    moment the user adds an option here. Bambuddy already validates the value
    against its own definition before anything is sent, so registering it as
    free text costs nothing but a less specific widget in Spoolman's own UI.
    """
    return "text" if field_type == "choice" else field_type


def spoolman_value(value: str | None, field_type: str):
    """Convert a canonical stored value into what Spoolman's extra dict expects.

    Spoolman stores extra values as JSON text typed to the field, so an integer
    goes over as ``5`` and a range as ``[1,5]`` — not as quoted strings. A
    cleared value is written as ``null`` rather than ``""``: Spoolman merges
    extra dicts, so omitting the key would leave the old value in place, and an
    empty string is not valid for the numeric types.
    """
    if value is None or value == "":
        return None
    if field_type == "integer":
        return int(value)
    if field_type == "float":
        return float(value)
    if field_type == "boolean":
        return value == "true"
    if field_type in RANGE_TYPES:
        low, high = parse_range(value)
        if field_type == "integer_range":
            return [int(low), int(high)]
        return [float(low), float(high)]
    return value


async def get_definitions(db: AsyncSession) -> list[CustomField]:
    """All custom field definitions in display order."""
    result = await db.execute(select(CustomField).order_by(CustomField.sort_order, CustomField.name))
    return list(result.scalars().all())


async def get_definition_by_key(db: AsyncSession, key: str) -> CustomField | None:
    result = await db.execute(select(CustomField).where(CustomField.key == key))
    return result.scalar_one_or_none()


def validate_values(payload: dict[str, str | None], definitions: list[CustomField]) -> dict[str, str | None]:
    """Check an incoming ``{key: value}`` payload against the definitions.

    Unknown keys are rejected rather than ignored — silently dropping them is
    how a renamed field turns into data loss the user only notices later.
    Blank values are normalised to None, meaning "clear this field".
    """
    by_key = {definition.key: definition for definition in definitions}
    resolved: dict[str, str | None] = {}
    for key, raw in payload.items():
        definition = by_key.get(key)
        if definition is None:
            raise ValueError(f"unknown custom field '{key}'")
        value = strip_control_chars(raw or "").strip() or None
        if value is None:
            resolved[key] = None
            continue
        if len(value) > MAX_VALUE_LENGTH:
            raise ValueError(f"value for '{definition.name}' exceeds {MAX_VALUE_LENGTH} characters")
        coerced = coerce_value(value, definition)
        # Checked again on the way out: coercion can grow a value (a bare date
        # becomes a full timestamp), and the column is VARCHAR(255) — which
        # SQLite ignores but PostgreSQL enforces with a hard error.
        if len(coerced) > MAX_VALUE_LENGTH:
            raise ValueError(f"value for '{definition.name}' exceeds {MAX_VALUE_LENGTH} characters")
        resolved[key] = coerced
    return resolved


def serialize_values(spool) -> dict[str, str | None]:
    """Flatten a spool's loaded value rows into ``{key: value}``.

    Rows whose definition was deleted concurrently are skipped rather than
    raising — one stale row must not 500 the whole inventory list.
    """
    values: dict[str, str | None] = {}
    for row in getattr(spool, "custom_values", None) or []:
        definition = getattr(row, "field", None)
        if definition is None:
            continue
        values[definition.key] = row.value
    return values


async def apply_values(
    db: AsyncSession,
    spool,
    payload: dict[str, str | None],
    definitions: list[CustomField],
) -> None:
    """Upsert / delete the value rows for *spool* from a validated payload.

    Only keys present in the payload are touched, so a PATCH that omits a field
    leaves it alone.

    Updates and deletes go out as Core statements rather than through loaded ORM
    objects. Deleting a definition removes its value rows, and an ORM UPDATE
    against a row that vanished in the meantime raises StaleDataError mid-flush,
    which leaves the whole session needing a rollback — a 500 for what is just
    someone editing a spool while someone else deletes the field. A Core UPDATE
    matching nothing reports rowcount 0 and we move on.

    Rows are read with an explicit query rather than off ``spool.custom_values``:
    the caller may hand us a spool it just constructed, whose collection is not
    loaded, and touching it there would raise MissingGreenlet on the implicit
    async lazy load. Callers returning the spool afterwards must re-select it
    with ``populate_existing`` — the session runs with ``expire_on_commit=False``,
    so an already-loaded collection would otherwise stay stale and the response
    would omit the value just saved.
    """
    resolved = validate_values(payload, definitions)
    if not resolved:
        return

    by_key = {definition.key: definition for definition in definitions}
    existing = await db.execute(
        select(SpoolCustomFieldValue.field_id).where(SpoolCustomFieldValue.spool_id == spool.id)
    )
    existing_ids = set(existing.scalars().all())

    for key, value in resolved.items():
        field_id = by_key[key].id
        if value is None:
            if field_id in existing_ids:
                await db.execute(
                    delete(SpoolCustomFieldValue)
                    .where(SpoolCustomFieldValue.spool_id == spool.id)
                    .where(SpoolCustomFieldValue.field_id == field_id)
                    .execution_options(synchronize_session=False)
                )
            continue
        if field_id in existing_ids:
            result = await db.execute(
                update(SpoolCustomFieldValue)
                .where(SpoolCustomFieldValue.spool_id == spool.id)
                .where(SpoolCustomFieldValue.field_id == field_id)
                .values(value=value)
                .execution_options(synchronize_session=False)
            )
            if result.rowcount == 0:
                # The row went away between our read and our write. Re-creating
                # it could resurrect a value whose definition is already gone,
                # so the write is dropped instead.
                logger.info(
                    "Skipped custom-field value for spool %s field %s: the row was removed concurrently",
                    spool.id,
                    field_id,
                )
            continue
        await _insert_value(db, spool.id, field_id, value)

    await db.flush()


async def _insert_value(db: AsyncSession, spool_id: int, field_id: int, value: str) -> None:
    """Insert one value row, tolerating a concurrent insert or a deleted field.

    The insert gets its own SAVEPOINT so a conflict rolls back just this row
    instead of the caller's whole transaction. Two things can go wrong, both as
    an IntegrityError on PostgreSQL (SQLite enforces neither, since PRAGMA
    foreign_keys is off app-wide): another request inserted the same
    (spool, field) first, or the definition was deleted meanwhile.
    """
    try:
        async with db.begin_nested():
            db.add(SpoolCustomFieldValue(spool_id=spool_id, field_id=field_id, value=value))
            await db.flush()
        return
    except IntegrityError:
        pass

    result = await db.execute(
        update(SpoolCustomFieldValue)
        .where(SpoolCustomFieldValue.spool_id == spool_id)
        .where(SpoolCustomFieldValue.field_id == field_id)
        .values(value=value)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 0:
        logger.info(
            "Dropped custom-field value for spool %s field %s: the field was deleted while the write was in flight",
            spool_id,
            field_id,
        )
