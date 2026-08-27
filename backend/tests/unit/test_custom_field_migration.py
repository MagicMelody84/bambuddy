"""Migration + schema regression tests for spool custom fields.

The tables are created by run_migrations on installs that predate the feature,
so the statements must be idempotent across restarts and must produce the same
shape the ORM models declare.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import run_migrations


@pytest.fixture(autouse=True)
def force_sqlite_dialect(monkeypatch):
    from backend.app.core import db_dialect

    monkeypatch.setattr(db_dialect, "is_sqlite", lambda: True)
    monkeypatch.setattr(db_dialect, "is_postgres", lambda: False)
    from backend.app.core import database as database_module

    monkeypatch.setattr(database_module, "is_sqlite", lambda: True)


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
async def engine():
    from backend.app.core.database import Base

    _register_all_models()
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    await eng.dispose()


async def test_migration_creates_tables_and_is_idempotent(engine):
    async with engine.begin() as conn:
        await run_migrations(conn)
    # A second startup must not fail on the already-created tables/indexes.
    async with engine.begin() as conn:
        await run_migrations(conn)

    async with engine.connect() as conn:
        tables = (
            await conn.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('custom_fields', 'spool_custom_field_values')"
                )
            )
        ).all()
    assert sorted(row[0] for row in tables) == ["custom_fields", "spool_custom_field_values"]


async def test_one_value_per_spool_and_field(engine):
    async with engine.begin() as conn:
        await run_migrations(conn)

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO spool (material, label_weight, core_weight, weight_used, "
                "weight_used_baseline, weight_locked) VALUES ('PLA', 1000, 250, 0, 0, 0)"
            )
        )
        await conn.execute(
            text("INSERT INTO custom_fields (key, name, field_type, sort_order) VALUES ('kunde', 'Kunde', 'select', 0)")
        )
        await conn.execute(
            text("INSERT INTO spool_custom_field_values (spool_id, field_id, value) VALUES (1, 1, 'Acme')")
        )

    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text("INSERT INTO spool_custom_field_values (spool_id, field_id, value) VALUES (1, 1, 'Other')")
            )
