"""Unit tests for the custom-field service (key derivation, validation, value writes)."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.services.custom_field_service import (
    MAX_OPTIONS,
    MAX_SORT_ORDER,
    SPOOLMAN_EXTRA_PREFIX,
    SUPPORTED_FIELD_TYPES,
    apply_values,
    coerce_value,
    normalize_field_key,
    normalize_field_name,
    normalize_field_type,
    normalize_options,
    parse_range,
    serialize_values,
    spoolman_extra_key,
    spoolman_field_type,
    spoolman_value,
    strip_control_chars,
    validate_values,
)


def _register_all_models():
    import backend.app.models  # noqa: F401
    from backend.app.models import (  # noqa: F401
        custom_field,
        external_link,
        location,
        print_log,
        print_queue,
        project_bom,
        slot_preset,
        spool_custom_field_value,
        spoolman_k_profile,
        spoolman_slot_assignment,
        virtual_printer,
    )


@pytest.fixture
async def session():
    from backend.app.core.database import Base

    _register_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        yield db
    await engine.dispose()


def _definition(**kwargs):
    from backend.app.models.custom_field import CustomField

    return CustomField(**kwargs)


class TestKeyNormalization:
    def test_slugifies_display_name(self):
        assert normalize_field_key("Kunde / Projekt") == "kunde_projekt"

    def test_collapses_and_trims_separators(self):
        assert normalize_field_key("  Trockenschrank – Charge!  ") == "trockenschrank_charge"

    def test_name_without_ascii_alphanumerics_falls_back_to_a_digest(self):
        # The app ships in thirteen languages and the key has to stay ASCII for
        # Spoolman, so a purely non-Latin name must not be refused.
        for name in ("客户", "حقل مخصص", "Клиент", "顧客", "고객"):
            key = normalize_field_key(name)
            assert key.startswith("field_")
            assert key.isascii()

    def test_the_digest_fallback_is_stable_and_distinct(self):
        assert normalize_field_key("客户") == normalize_field_key("客户")
        assert normalize_field_key("客户") != normalize_field_key("顧客")

    def test_punctuation_only_name_also_gets_a_key(self):
        assert normalize_field_key("---").startswith("field_")

    def test_rejects_blank_name(self):
        with pytest.raises(ValueError):
            normalize_field_key("   ")

    def test_control_characters_are_stripped_from_the_name(self):
        # PostgreSQL refuses to store a NUL at all, so one pasted into the name
        # would be a 500 rather than a validation error.
        assert normalize_field_name("Kun\x00de\r\n") == "Kunde"
        assert strip_control_chars("a\x00b\x1fc\x7f") == "abc"
        with pytest.raises(ValueError):
            normalize_field_name("\x00\x01")

    def test_truncated_key_does_not_end_in_separator(self):
        key = normalize_field_key("a" * 49 + " b")
        assert len(key) <= 50
        assert not key.endswith("_")


class TestOptions:
    def test_trims_and_deduplicates_preserving_order(self):
        assert normalize_options([" B ", "A", "B"], "choice") == ["B", "A"]

    def test_rejects_empty_list_for_choice(self):
        with pytest.raises(ValueError):
            normalize_options([], "choice")

    def test_rejects_list_of_blanks(self):
        with pytest.raises(ValueError):
            normalize_options(["  ", ""], "choice")

    def test_rejects_too_many_options(self):
        with pytest.raises(ValueError):
            normalize_options([str(i) for i in range(MAX_OPTIONS + 1)], "choice")

    def test_non_choice_types_take_no_options(self):
        assert normalize_options([], "text") == []
        assert normalize_options(None, "datetime") == []
        with pytest.raises(ValueError, match="does not take options"):
            normalize_options(["A"], "text")


class TestFieldTypes:
    def test_defaults_to_text(self):
        assert normalize_field_type(None) == "text"
        assert normalize_field_type("") == "text"

    def test_every_supported_type_round_trips(self):
        for field_type in SUPPORTED_FIELD_TYPES:
            assert normalize_field_type(field_type.upper()) == field_type

    def test_rejects_unknown_type(self):
        with pytest.raises(ValueError):
            normalize_field_type("colour")


class TestNumericStrictness:
    """Python's own parsers are laxer than a user would expect."""

    def test_integer_rejects_underscores_and_non_ascii_digits(self):
        field = _definition(id=1, key="n", name="N", field_type="integer")
        for bad in ("1_0", "١٢", "1 0", "0x10", "1e3", "12.0", "+ 5"):
            with pytest.raises(ValueError):
                coerce_value(bad, field)
        assert coerce_value("+5", field) == "5"
        assert coerce_value("-5", field) == "-5"

    def test_float_rejects_underscores_and_non_ascii_digits(self):
        field = _definition(id=1, key="f", name="F", field_type="float")
        for bad in ("1_000.5", "١٢.٣", "1,0,0", "0x1p3", "infinity"):
            with pytest.raises(ValueError):
                coerce_value(bad, field)
        assert coerce_value("1e3", field) == "1000.0"
        assert coerce_value(".5", field) == "0.5"


class TestCoerceValue:
    def test_integer_requires_a_whole_number(self):
        field = _definition(id=1, key="lagen", name="Lagen", field_type="integer")
        assert coerce_value("12", field) == "12"
        assert coerce_value("-3", field) == "-3"
        for bad in ("12.5", "abc", ""):
            with pytest.raises(ValueError):
                coerce_value(bad, field)

    def test_float_accepts_a_comma_decimal(self):
        field = _definition(id=1, key="laenge", name="Länge", field_type="float")
        assert coerce_value("1,5", field) == "1.5"
        assert coerce_value("12", field) == "12.0"

    def test_float_rejects_text_and_infinities(self):
        field = _definition(id=1, key="laenge", name="Länge", field_type="float")
        for bad in ("abc", "inf", "nan"):
            with pytest.raises(ValueError):
                coerce_value(bad, field)

    def test_integer_range_normalises_to_min_max(self):
        field = _definition(id=1, key="temp", name="Temperatur", field_type="integer_range")
        assert coerce_value("200, 230", field) == "200,230"
        assert coerce_value("200 230", field) == "200,230"

    def test_range_rejects_inverted_bounds_and_wrong_arity(self):
        field = _definition(id=1, key="temp", name="Temperatur", field_type="integer_range")
        with pytest.raises(ValueError, match="lower bound"):
            coerce_value("230,200", field)
        with pytest.raises(ValueError, match="min,max"):
            coerce_value("230", field)

    def test_float_range_keeps_decimals(self):
        # The comma is the separator, so decimals inside a range must use a dot.
        field = _definition(id=1, key="tol", name="Toleranz", field_type="float_range")
        assert coerce_value("-0.5, 1.25", field) == "-0.5,1.25"
        with pytest.raises(ValueError, match="min,max"):
            coerce_value("-0,5 , 1,25", field)

    def test_boolean_accepts_common_spellings(self):
        field = _definition(id=1, key="trocken", name="Trocken", field_type="boolean")
        for truthy in ("true", "1", "yes", "Ja", "ON"):
            assert coerce_value(truthy, field) == "true"
        for falsy in ("false", "0", "no", "Nein", "off"):
            assert coerce_value(falsy, field) == "false"
        with pytest.raises(ValueError):
            coerce_value("maybe", field)

    def test_datetime_accepts_the_trailing_z(self):
        field = _definition(id=1, key="geoeffnet", name="Geöffnet", field_type="datetime")
        assert coerce_value("2026-08-23T14:30", field) == "2026-08-23T14:30:00"
        assert coerce_value("2026-08-23T14:30:00Z", field).startswith("2026-08-23T14:30:00")
        with pytest.raises(ValueError):
            coerce_value("yesterday", field)

    def test_text_passes_through(self):
        field = _definition(id=1, key="notiz", name="Notiz", field_type="text")
        assert coerce_value("Charge 42 / Regal B", field) == "Charge 42 / Regal B"

    def test_parse_range_round_trips(self):
        assert parse_range("1,5") == ("1", "5")
        assert parse_range("nonsense") == ("", "")


class TestValueLength:
    def test_a_bare_date_that_grows_past_the_column_is_rejected(self):
        # Coercion can lengthen a value (a date becomes a full timestamp), and
        # the column is VARCHAR(255) — enforced by PostgreSQL, ignored by SQLite.
        field = _definition(id=1, key="t", name="T", field_type="text")
        assert len(validate_values({"t": "x" * 255}, [field])["t"]) == 255
        with pytest.raises(ValueError, match="exceeds"):
            validate_values({"t": "x" * 256}, [field])

    def test_sort_order_is_capped_below_the_postgres_integer_limit(self):
        assert MAX_SORT_ORDER < 2**31 - 1


class TestSpoolmanEncoding:
    def test_types_map_one_to_one_except_choice(self):
        for field_type in SUPPORTED_FIELD_TYPES:
            expected = "text" if field_type == "choice" else field_type
            assert spoolman_field_type(field_type) == expected

    def test_values_are_typed_not_stringified(self):
        assert spoolman_value("5", "integer") == 5
        assert spoolman_value("1.5", "float") == 1.5
        assert spoolman_value("true", "boolean") is True
        assert spoolman_value("false", "boolean") is False
        assert spoolman_value("200,230", "integer_range") == [200, 230]
        assert spoolman_value("-0.5,1.25", "float_range") == [-0.5, 1.25]
        assert spoolman_value("Acme", "choice") == "Acme"
        assert spoolman_value("2026-08-23T14:30:00", "datetime") == "2026-08-23T14:30:00"

    def test_cleared_value_is_null_for_every_type(self):
        # Spoolman merges extra dicts, so a cleared field has to send something
        # explicit; "" is not valid for the numeric types, null is.
        for field_type in SUPPORTED_FIELD_TYPES:
            assert spoolman_value(None, field_type) is None
            assert spoolman_value("", field_type) is None


class TestValidateValues:
    def test_accepts_a_declared_option(self):
        field = _definition(id=1, key="kunde", name="Kunde", field_type="choice", options=["Acme", "Globex"])
        assert validate_values({"kunde": "Acme"}, [field]) == {"kunde": "Acme"}

    def test_blank_value_means_clear(self):
        field = _definition(id=1, key="kunde", name="Kunde", field_type="choice", options=["Acme"])
        assert validate_values({"kunde": "  "}, [field]) == {"kunde": None}
        assert validate_values({"kunde": None}, [field]) == {"kunde": None}

    def test_rejects_value_outside_the_option_list(self):
        field = _definition(id=1, key="kunde", name="Kunde", field_type="choice", options=["Acme"])
        with pytest.raises(ValueError, match="not an option"):
            validate_values({"kunde": "Initech"}, [field])

    def test_rejects_unknown_field_instead_of_dropping_it(self):
        with pytest.raises(ValueError, match="unknown custom field"):
            validate_values({"ghost": "x"}, [])


class TestApplyValues:
    async def test_insert_update_and_clear_round_trip(self, session):
        from backend.app.models.custom_field import CustomField
        from backend.app.models.spool import Spool

        field = CustomField(key="kunde", name="Kunde", field_type="choice", options=["Acme", "Globex"])
        spool = Spool(material="PLA")
        session.add_all([field, spool])
        await session.commit()
        definitions = [field]

        await apply_values(session, spool, {"kunde": "Acme"}, definitions)
        await session.commit()
        await session.refresh(spool)
        assert serialize_values(spool) == {"kunde": "Acme"}
        assert spool.custom_fields == {"kunde": "Acme"}

        await apply_values(session, spool, {"kunde": "Globex"}, definitions)
        await session.commit()
        await session.refresh(spool)
        assert spool.custom_fields == {"kunde": "Globex"}

        await apply_values(session, spool, {"kunde": ""}, definitions)
        await session.commit()
        await session.refresh(spool)
        assert spool.custom_fields == {}

    async def test_omitted_key_is_left_alone(self, session):
        from backend.app.models.custom_field import CustomField
        from backend.app.models.spool import Spool

        kunde = CustomField(key="kunde", name="Kunde", field_type="choice", options=["Acme"])
        charge = CustomField(key="charge", name="Charge", field_type="choice", options=["A", "B"])
        spool = Spool(material="PLA")
        session.add_all([kunde, charge, spool])
        await session.commit()
        definitions = [kunde, charge]

        await apply_values(session, spool, {"kunde": "Acme", "charge": "A"}, definitions)
        await session.commit()

        await apply_values(session, spool, {"charge": "B"}, definitions)
        await session.commit()
        await session.refresh(spool)
        assert spool.custom_fields == {"kunde": "Acme", "charge": "B"}

    async def test_deleting_a_spool_removes_its_values(self, session):
        from sqlalchemy import func, select

        from backend.app.models.custom_field import CustomField
        from backend.app.models.spool import Spool
        from backend.app.models.spool_custom_field_value import SpoolCustomFieldValue

        field = CustomField(key="kunde", name="Kunde", field_type="choice", options=["Acme"])
        spool = Spool(material="PLA")
        session.add_all([field, spool])
        await session.commit()

        await apply_values(session, spool, {"kunde": "Acme"}, [field])
        await session.commit()

        await session.delete(spool)
        await session.commit()

        remaining = await session.execute(select(func.count(SpoolCustomFieldValue.id)))
        assert remaining.scalar_one() == 0
