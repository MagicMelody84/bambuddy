"""Concurrent-edit paths for custom-field values.

Editing a spool while another request deletes the field used to raise
StaleDataError mid-flush, which poisons the whole session and turns a routine
race into a 5xx. These pin the behaviour that replaced it.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.custom_field import CustomField
from backend.app.models.spool import Spool
from backend.app.models.spool_custom_field_value import SpoolCustomFieldValue
from backend.app.services.custom_field_service import apply_values


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
async def env():
    from backend.app.core.database import Base

    _register_all_models()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        field = CustomField(key="kunde", name="Kunde", field_type="text")
        spool = Spool(material="PLA")
        db.add_all([field, spool])
        await db.commit()
        yield db, spool, field
    await engine.dispose()


async def test_write_after_the_row_was_removed_recreates_it(env):
    db, spool, field = env
    await apply_values(db, spool, {"kunde": "Acme"}, [field])
    await db.commit()

    # The value rows are gone but the definition still stands, so a save is a
    # legitimate write — and the session must survive it.
    await db.execute(delete(SpoolCustomFieldValue).where(SpoolCustomFieldValue.field_id == field.id))
    await db.commit()

    await apply_values(db, spool, {"kunde": "Globex"}, [field])
    await db.commit()

    await db.refresh(spool)
    assert spool.custom_fields == {"kunde": "Globex"}
    assert (await db.execute(select(Spool))).scalars().first() is not None


async def test_interleaved_writers_and_field_deletes_never_poison_a_session(tmp_path):
    """The real race, run across independent sessions.

    An ORM UPDATE against a row another session deleted raises StaleDataError
    during flush, and the session is then unusable until it is rolled back —
    which is what made a concurrent spool save return 5xx. Needs a file-backed
    database: an in-memory one is private to its connection.
    """
    from backend.app.core.database import Base

    _register_all_models()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/race.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as setup:
        spool = Spool(material="PLA")
        setup.add(spool)
        await setup.commit()
        spool_id = spool.id

    failures: list[Exception] = []

    async def writer(field_id: int, key: str, n: int):
        try:
            async with maker() as db:
                sp = (await db.execute(select(Spool).where(Spool.id == spool_id))).scalar_one()
                defs = (await db.execute(select(CustomField).where(CustomField.id == field_id))).scalars().all()
                if defs:
                    await apply_values(db, sp, {key: f"v{n}"}, list(defs))
                    await db.commit()
        except Exception as exc:  # noqa: BLE001 — the point is that none escape
            failures.append(exc)

    async def dropper(field_id: int):
        try:
            async with maker() as db:
                await db.execute(delete(SpoolCustomFieldValue).where(SpoolCustomFieldValue.field_id == field_id))
                await db.execute(delete(CustomField).where(CustomField.id == field_id))
                await db.commit()
        except Exception as exc:  # noqa: BLE001
            failures.append(exc)

    for round_no in range(15):
        async with maker() as db:
            field = CustomField(key=f"race{round_no}", name=f"Race{round_no}", field_type="text")
            db.add(field)
            await db.commit()
            fid, fkey = field.id, field.key

        await asyncio.gather(
            *[writer(fid, fkey, i) for i in range(6)],
            dropper(fid),
        )

    assert failures == [], failures[:3]
    await engine.dispose()


async def test_delete_of_a_row_removed_underneath_us_does_not_raise(env):
    db, spool, field = env
    await apply_values(db, spool, {"kunde": "Acme"}, [field])
    await db.commit()
    await db.execute(delete(SpoolCustomFieldValue).where(SpoolCustomFieldValue.field_id == field.id))
    await db.commit()

    await apply_values(db, spool, {"kunde": ""}, [field])
    await db.commit()
    rows = await db.execute(select(SpoolCustomFieldValue))
    assert rows.scalars().all() == []


async def test_a_second_insert_of_the_same_pair_updates_instead_of_duplicating(env):
    db, spool, field = env
    from backend.app.services.custom_field_service import _insert_value

    await _insert_value(db, spool.id, field.id, "erst")
    await db.commit()
    # Same pair again — the unique index must not surface as a 500.
    await _insert_value(db, spool.id, field.id, "zweit")
    await db.commit()

    rows = (await db.execute(select(SpoolCustomFieldValue))).scalars().all()
    assert len(rows) == 1
    assert rows[0].value == "zweit"


async def test_values_survive_an_unrelated_field_being_dropped(env):
    db, spool, field = env
    other = CustomField(key="charge", name="Charge", field_type="text")
    db.add(other)
    await db.commit()

    await apply_values(db, spool, {"kunde": "Acme", "charge": "A"}, [field, other])
    await db.commit()

    await db.execute(delete(SpoolCustomFieldValue).where(SpoolCustomFieldValue.field_id == other.id))
    await db.execute(delete(CustomField).where(CustomField.id == other.id))
    await db.commit()

    await db.refresh(spool)
    assert spool.custom_fields == {"kunde": "Acme"}
