"""Regression tests for the locations.tag_uid unique migration.

An earlier build created the index as non-unique, so two locations could hold
the same NFC tag. ``/locations/by-tag`` answers a scan with a single row, so
that made the scan resolve to whichever had the lower id. The API refuses the
second assignment now; this migration is the backstop, and it has to cope with
databases that already contain a duplicate.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from backend.app.core.database import _migrate_location_tag_uid_unique


@pytest.fixture
async def engine():
    """In-memory SQLite with the locations table as it was BEFORE the index."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE locations ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "name VARCHAR(255) NOT NULL UNIQUE, "
                "name_key VARCHAR(255), "
                "tag_uid VARCHAR(32))"
            )
        )
        # The non-unique index the earlier build left behind.
        await conn.execute(text("CREATE INDEX ix_locations_tag_uid ON locations (tag_uid)"))
    try:
        yield engine
    finally:
        await engine.dispose()


async def _insert(conn, name: str, tag_uid: str | None) -> None:
    await conn.execute(
        text("INSERT INTO locations (name, name_key, tag_uid) VALUES (:n, :k, :t)"),
        {"n": name, "k": name.lower(), "t": tag_uid},
    )


async def _rows(conn) -> list[tuple]:
    result = await conn.execute(text("SELECT name, tag_uid FROM locations ORDER BY id"))
    return list(result.all())


async def test_clears_the_duplicate_tag_from_all_but_the_oldest(engine):
    async with engine.begin() as conn:
        await _insert(conn, "Shelf A", "AABBCCDD")
        await _insert(conn, "Shelf B", "AABBCCDD")
        await _insert(conn, "Shelf C", "11223344")

    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)

    async with engine.begin() as conn:
        # The oldest row keeps the tag; the later claimant loses it but survives.
        assert await _rows(conn) == [
            ("Shelf A", "AABBCCDD"),
            ("Shelf B", None),
            ("Shelf C", "11223344"),
        ]


async def test_untagged_locations_are_left_alone(engine):
    async with engine.begin() as conn:
        await _insert(conn, "Untagged 1", None)
        await _insert(conn, "Untagged 2", None)
        await _insert(conn, "Untagged 3", None)

    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)

    async with engine.begin() as conn:
        assert await _rows(conn) == [("Untagged 1", None), ("Untagged 2", None), ("Untagged 3", None)]


async def test_the_index_then_rejects_a_duplicate_tag(engine):
    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)

    async with engine.begin() as conn:
        await _insert(conn, "Shelf A", "AABBCCDD")

    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await _insert(conn, "Shelf B", "AABBCCDD")


async def test_the_index_still_allows_many_untagged_locations(engine):
    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)

    # NULLs stay distinct under a unique index in both SQLite and PostgreSQL —
    # otherwise exactly one location could exist without a tag.
    async with engine.begin() as conn:
        await _insert(conn, "Untagged 1", None)
        await _insert(conn, "Untagged 2", None)

    async with engine.begin() as conn:
        assert len(await _rows(conn)) == 2


async def test_is_idempotent(engine):
    async with engine.begin() as conn:
        await _insert(conn, "Shelf A", "AABBCCDD")
        await _insert(conn, "Shelf B", "AABBCCDD")

    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)
    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)

    async with engine.begin() as conn:
        assert await _rows(conn) == [("Shelf A", "AABBCCDD"), ("Shelf B", None)]


async def test_handles_empty_table(engine):
    async with engine.begin() as conn:
        await _migrate_location_tag_uid_unique(conn)

    async with engine.begin() as conn:
        assert await _rows(conn) == []
