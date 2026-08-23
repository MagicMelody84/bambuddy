"""Spoolman write path for custom-field values.

Values are mirrored into a Spoolman spool's `extra` dict. Spoolman rejects a
PATCH carrying an unregistered extra key with HTTP 400, so each field has to be
registered before the merge, under the matching Spoolman type. Values go over
as JSON typed to that field, and a cleared value as null — Spoolman merges extra
dicts rather than replacing them, so an omitted key would keep the old value.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.api.routes.spoolman_inventory import _validate_custom_fields, _write_custom_fields


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


class FakeSpoolmanClient:
    def __init__(self):
        self.registered: list[tuple[str, str, list[str] | None]] = []
        self.merged: dict | None = None

    async def ensure_extra_field(self, name, field_type="text", choices=None):
        self.registered.append((name, field_type, choices))
        return True

    async def merge_spool_extra(self, spool_id, new_fields):
        self.merged = new_fields
        return {"id": spool_id, "extra": new_fields, "filament": {"material": "PLA", "weight": 1000}}


@pytest.fixture
async def session():
    from backend.app.core.database import Base
    from backend.app.models.custom_field import CustomField

    _register_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        db.add(CustomField(key="kunde", name="Kunde", field_type="choice", options=["Acme", "Globex"]))
        db.add(CustomField(key="notiz", name="Notiz", field_type="text"))
        db.add(CustomField(key="lagen", name="Lagen", field_type="integer"))
        db.add(CustomField(key="temp", name="Temperatur", field_type="integer_range"))
        await db.commit()
        yield db
    await engine.dispose()


async def test_choice_is_registered_as_text(session):
    client = FakeSpoolmanClient()
    await _write_custom_fields(session, client, 7, {"kunde": "Acme"})
    # text, not choice: Bambuddy owns the option list, and a choice registered
    # here would freeze it at the values that existed on first write.
    assert client.registered == [("bambu_cf_kunde", "text", None)]
    assert client.merged == {"bambu_cf_kunde": json.dumps("Acme")}


async def test_numeric_and_range_fields_keep_their_spoolman_type(session):
    client = FakeSpoolmanClient()
    values = await _validate_custom_fields(session, {"lagen": "12", "temp": "200,230"})
    await _write_custom_fields(session, client, 7, values)
    assert sorted(client.registered) == [
        ("bambu_cf_lagen", "integer", None),
        ("bambu_cf_temp", "integer_range", None),
    ]
    # Typed JSON, not quoted strings — 5 and [1,5], never "5".
    assert client.merged == {
        "bambu_cf_lagen": "12",
        "bambu_cf_temp": "[200, 230]",
    }


async def test_cleared_value_is_written_as_an_explicit_null(session):
    client = FakeSpoolmanClient()
    await _write_custom_fields(session, client, 7, {"kunde": None})
    assert client.merged == {"bambu_cf_kunde": "null"}


async def test_nothing_is_written_for_an_empty_payload(session):
    client = FakeSpoolmanClient()
    assert await _write_custom_fields(session, client, 7, {}) is None
    assert client.registered == []
    assert client.merged is None


async def test_value_outside_the_option_list_is_a_400(session):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _validate_custom_fields(session, {"kunde": "Initech"})
    assert exc.value.status_code == 400


async def test_free_text_value_is_written_as_typed(session):
    client = FakeSpoolmanClient()
    values = await _validate_custom_fields(session, {"notiz": "  Regal B / Charge 42 "})
    await _write_custom_fields(session, client, 7, values)
    assert client.merged == {"bambu_cf_notiz": json.dumps("Regal B / Charge 42")}


async def test_unknown_field_is_a_400(session):
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc:
        await _validate_custom_fields(session, {"ghost": "x"})
    assert exc.value.status_code == 400
