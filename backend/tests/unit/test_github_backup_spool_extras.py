"""Round-trip for the spool extras the GitHub backup carries (#1004 + custom fields).

Storage location travels by name, not by id — an id is local to an install.
Custom-field values travel keyed by the definition's stable key, with the
definitions in their own file, so a spool and its values restore as one unit.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.app.models.custom_field import CustomField
from backend.app.models.location import Location
from backend.app.models.spool import Spool
from backend.app.models.spool_catalog import SpoolCatalogEntry
from backend.app.services.github_backup import GitHubBackupService
from backend.app.services.github_restore import GitHubRestoreService, _CategoryTally


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
async def maker(tmp_path):
    from backend.app.core.database import Base

    _register_all_models()
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/bk.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


async def _seed(db):
    loc = Location(name="Regal A", name_key="regal a", identifier="SHELF-A")
    kunde = CustomField(key="kunde", name="Kunde", field_type="choice", options=["Acme", "Globex"])
    lagen = CustomField(key="lagen", name="Lagen", field_type="integer")
    db.add_all([loc, kunde, lagen])
    await db.commit()

    spool = Spool(material="PLA", brand="Polymaker", storage_location="Regal A", location_id=loc.id)
    db.add(spool)
    await db.commit()

    from backend.app.services.custom_field_service import apply_values

    await apply_values(db, spool, {"kunde": "Acme", "lagen": "12"}, [kunde, lagen])
    await db.commit()
    return spool.id


async def _collect(db) -> dict:
    files: dict = {}
    await GitHubBackupService()._collect_spools(db, files)
    return files


async def test_backup_carries_location_name_and_custom_values(maker):
    async with maker() as db:
        await _seed(db)
        files = await _collect(db)

    entry = files["spools/inventory.json"]["spools"][0]
    assert entry["storage_location"] == "Regal A"
    # Never the id: it means nothing on the machine restoring this.
    assert "location_id" not in entry
    assert entry["custom_fields"] == {"kunde": "Acme", "lagen": "12"}

    assert files["spools/locations.json"]["locations"] == [{"name": "Regal A", "identifier": "SHELF-A"}]
    keys = [f["key"] for f in files["spools/custom_fields.json"]["fields"]]
    assert sorted(keys) == ["kunde", "lagen"]


async def test_restore_into_an_empty_install_rebuilds_everything(maker, tmp_path):
    async with maker() as db:
        await _seed(db)
        files = await _collect(db)

    # A second, empty install.
    from backend.app.core.database import Base

    engine2 = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/restore.db", echo=False)
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker2 = async_sessionmaker(engine2, expire_on_commit=False)

    async with maker2() as db:
        tally = _CategoryTally()
        await GitHubRestoreService()._restore_spools(
            db,
            files["spools/inventory.json"],
            None,
            True,
            tally,
            {},
            files["spools/locations.json"],
            files["spools/custom_fields.json"],
        )
        await db.commit()

        spool = (await db.execute(select(Spool))).scalars().one()
        assert spool.storage_location == "Regal A"
        # Resolved to the freshly created catalog row, not carried over as an id.
        assert spool.location_id is not None
        assert spool.custom_fields == {"kunde": "Acme", "lagen": "12"}

        loc = (await db.execute(select(Location))).scalars().one()
        assert loc.name == "Regal A"
        assert loc.identifier == "SHELF-A"

        defs = (await db.execute(select(CustomField))).scalars().all()
        assert {d.key: d.field_type for d in defs} == {"kunde": "choice", "lagen": "integer"}

    await engine2.dispose()


async def test_restore_keeps_a_local_definition_that_diverged(maker, tmp_path):
    """A field retyped locally must win — its stored values were parsed that way."""
    async with maker() as db:
        await _seed(db)
        files = await _collect(db)

    from backend.app.core.database import Base

    engine2 = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/diverged.db", echo=False)
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker2 = async_sessionmaker(engine2, expire_on_commit=False)

    async with maker2() as db:
        db.add(CustomField(key="kunde", name="Auftraggeber", field_type="text"))
        await db.commit()

        tally = _CategoryTally()
        await GitHubRestoreService()._restore_spools(
            db,
            files["spools/inventory.json"],
            None,
            True,
            tally,
            {},
            files["spools/locations.json"],
            files["spools/custom_fields.json"],
        )
        await db.commit()

        kunde = (await db.execute(select(CustomField).where(CustomField.key == "kunde"))).scalar_one()
        assert kunde.name == "Auftraggeber"
        assert kunde.field_type == "text"
        # "Acme" is still a valid text value, so it lands.
        spool = (await db.execute(select(Spool))).scalars().one()
        assert spool.custom_fields["kunde"] == "Acme"

    await engine2.dispose()


async def test_a_value_the_local_definition_rejects_is_dropped_not_fatal(maker, tmp_path):
    async with maker() as db:
        await _seed(db)
        files = await _collect(db)

    from backend.app.core.database import Base

    engine2 = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/reject.db", echo=False)
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker2 = async_sessionmaker(engine2, expire_on_commit=False)

    async with maker2() as db:
        # Locally "kunde" is a number now; "Acme" cannot survive that.
        db.add(CustomField(key="kunde", name="Kunde", field_type="integer"))
        await db.commit()

        tally = _CategoryTally()
        await GitHubRestoreService()._restore_spools(
            db,
            files["spools/inventory.json"],
            None,
            True,
            tally,
            {},
            files["spools/locations.json"],
            files["spools/custom_fields.json"],
        )
        await db.commit()

        spool = (await db.execute(select(Spool))).scalars().one()
        # The bad one is gone, the good one survived — one value must not cost
        # the rest of the spool.
        assert spool.custom_fields == {"lagen": "12"}
        assert tally.restored == 1

    await engine2.dispose()


async def test_catalogs_survive_a_backup_with_no_spools_yet(maker, tmp_path):
    """Locations and field definitions can exist before the first spool does."""
    async with maker() as db:
        db.add(Location(name="Trockenbox", name_key="trockenbox"))
        db.add(CustomField(key="charge", name="Charge", field_type="text"))
        await db.commit()
        files = await _collect(db)

    assert "spools/inventory.json" not in files
    assert files["spools/locations.json"]["locations"] == [{"name": "Trockenbox", "identifier": None}]

    from backend.app.core.database import Base

    engine2 = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/empty.db", echo=False)
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker2 = async_sessionmaker(engine2, expire_on_commit=False)

    async with maker2() as db:
        tally = _CategoryTally()
        await GitHubRestoreService()._restore_spools(
            db,
            None,
            None,
            True,
            tally,
            {},
            files["spools/locations.json"],
            files["spools/custom_fields.json"],
        )
        await db.commit()
        assert (await db.execute(select(Location))).scalars().one().name == "Trockenbox"
        assert (await db.execute(select(CustomField))).scalars().one().key == "charge"

    await engine2.dispose()


async def test_restoring_twice_does_not_duplicate_catalogs(maker, tmp_path):
    async with maker() as db:
        await _seed(db)
        files = await _collect(db)

    from backend.app.core.database import Base

    engine2 = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/twice.db", echo=False)
    async with engine2.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker2 = async_sessionmaker(engine2, expire_on_commit=False)

    for _ in range(2):
        async with maker2() as db:
            tally = _CategoryTally()
            await GitHubRestoreService()._restore_spools(
                db,
                files["spools/inventory.json"],
                None,
                True,
                tally,
                {},
                files["spools/locations.json"],
                files["spools/custom_fields.json"],
            )
            await db.commit()

    async with maker2() as db:
        assert len((await db.execute(select(Location))).scalars().all()) == 1
        assert len((await db.execute(select(CustomField))).scalars().all()) == 2
        spools = (await db.execute(select(Spool))).scalars().all()
        assert len(spools) == 1
        assert spools[0].custom_fields == {"kunde": "Acme", "lagen": "12"}

    await engine2.dispose()


# ── The rest of the spool columns the backup used to drop ───────────────────


async def _seed_full(db):
    """A spool with every column the backup carries actually populated."""
    from datetime import datetime

    catalog = SpoolCatalogEntry(name="Eigener Kern 180g", weight=180, is_default=False)
    db.add(catalog)
    await db.commit()

    spool = Spool(
        material="PLA",
        subtype="Silk",
        brand="Polymaker",
        color_name="Jade White",
        rgba="FFFFFFFF",
        extra_colors="ec984c,6cd4bc",
        effect_type="gradient",
        label_weight=1000,
        core_weight=180,
        core_weight_catalog_id=catalog.id,
        weight_used=250.5,
        weight_used_baseline=100.0,
        weight_locked=True,
        category="Produktion",
        low_stock_threshold_pct=35,
        last_scale_weight=930,
        last_weighed_at=datetime(2026, 8, 20, 9, 15, 0),
        last_used=datetime(2026, 8, 21, 18, 0, 0),
        encode_time=datetime(2026, 8, 19, 12, 0, 0),
        added_full=True,
    )
    db.add(spool)
    await db.commit()
    return spool


async def _restore_into(tmp_path, name, files):
    from backend.app.core.database import Base

    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path}/{name}.db", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as db:
        tally = _CategoryTally()
        await GitHubRestoreService()._restore_spools(
            db,
            files.get("spools/inventory.json"),
            None,
            True,
            tally,
            {},
            files.get("spools/locations.json"),
            files.get("spools/custom_fields.json"),
            files.get("spools/spool_catalog.json"),
        )
        await db.commit()
    return engine, maker


async def test_every_carried_column_survives_a_round_trip(maker, tmp_path):
    async with maker() as db:
        await _seed_full(db)
        files = await _collect(db)

    engine2, maker2 = await _restore_into(tmp_path, "full", files)
    async with maker2() as db:
        s = (await db.execute(select(Spool))).scalars().one()
        assert s.extra_colors == "ec984c,6cd4bc"
        assert s.effect_type == "gradient"
        assert s.weight_used_baseline == 100.0
        assert s.category == "Produktion"
        assert s.low_stock_threshold_pct == 35
        assert s.last_scale_weight == 930
        assert s.last_weighed_at is not None and s.last_weighed_at.year == 2026
        assert s.last_used is not None and s.last_used.day == 21
        assert s.encode_time is not None and s.encode_time.day == 19
        assert s.added_full is True

        # The catalog reference resolved to the entry recreated on this install,
        # not to the id the source machine happened to use.
        catalog = (await db.execute(select(SpoolCatalogEntry))).scalars().one()
        assert catalog.name == "Eigener Kern 180g"
        assert s.core_weight_catalog_id == catalog.id
    await engine2.dispose()


async def test_the_catalog_reference_never_travels_as_an_id(maker):
    async with maker() as db:
        await _seed_full(db)
        files = await _collect(db)

    entry = files["spools/inventory.json"]["spools"][0]
    assert "core_weight_catalog_id" not in entry
    assert entry["core_weight_catalog"] == {"name": "Eigener Kern 180g", "weight": 180}


async def test_a_reference_with_no_local_match_restores_as_unset(maker, tmp_path):
    async with maker() as db:
        await _seed_full(db)
        files = await _collect(db)

    # Drop the catalog file: the entry cannot be recreated, so the reference
    # dangles — core_weight itself still carries the number that matters.
    files.pop("spools/spool_catalog.json")
    engine2, maker2 = await _restore_into(tmp_path, "nocat", files)
    async with maker2() as db:
        s = (await db.execute(select(Spool))).scalars().one()
        assert s.core_weight_catalog_id is None
        assert s.core_weight == 180
    await engine2.dispose()


async def test_values_a_newer_schema_rejects_are_dropped_not_written(maker, tmp_path):
    """A backup can predate today's validation; a bad value must not poison the row."""
    async with maker() as db:
        await _seed_full(db)
        files = await _collect(db)

    entry = files["spools/inventory.json"]["spools"][0]
    entry["extra_colors"] = "not-a-hex-value"
    entry["effect_type"] = "holographic"
    entry["low_stock_threshold_pct"] = 500
    entry["last_scale_weight"] = "930g"
    entry["category"] = "x" * 200
    entry["weight_used_baseline"] = "nonsense"
    entry["added_full"] = "yes"

    engine2, maker2 = await _restore_into(tmp_path, "bad", files)
    async with maker2() as db:
        s = (await db.execute(select(Spool))).scalars().one()
        assert s.extra_colors is None
        assert s.effect_type is None
        assert s.low_stock_threshold_pct is None
        assert s.last_scale_weight is None
        assert len(s.category) == 50
        assert s.weight_used_baseline == 0.0
        assert s.added_full is None
        # The spool itself still restored.
        assert s.material == "PLA"
    await engine2.dispose()


async def test_overwriting_an_existing_spool_updates_the_new_columns_too(maker, tmp_path):
    async with maker() as db:
        await _seed_full(db)
        files = await _collect(db)

    engine2, maker2 = await _restore_into(tmp_path, "twice2", files)
    async with maker2() as db:
        s = (await db.execute(select(Spool))).scalars().one()
        s.category = "Von Hand geaendert"
        s.extra_colors = None
        await db.commit()

        tally = _CategoryTally()
        await GitHubRestoreService()._restore_spools(
            db,
            files["spools/inventory.json"],
            None,
            True,
            tally,
            {},
            files.get("spools/locations.json"),
            files.get("spools/custom_fields.json"),
            files.get("spools/spool_catalog.json"),
        )
        await db.commit()

        rows = (await db.execute(select(Spool))).scalars().all()
        assert len(rows) == 1
        assert rows[0].category == "Produktion"
        assert rows[0].extra_colors == "ec984c,6cd4bc"
    await engine2.dispose()
