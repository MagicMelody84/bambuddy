"""Integration tests for the ``location_id`` filter on GET /inventory/spools.

Without it a client wanting only the spools kept at one location had to fetch
the entire inventory and filter locally — every spool of every other location
transferred and parsed just to be discarded. That is what a constrained client
(the SpoolBuddy Lite scale) does on every location-tag scan.

Regression guards:
 - The filter actually narrows the result to the given location.
 - It composes with include_archived rather than overriding it.
 - An unknown id yields an empty list, not everything.
 - Omitting it keeps the previous behaviour: the whole active inventory.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.location import Location
from backend.app.models.spool import Spool
from backend.app.services.location_service import assign_location_name

SPOOLS_URL = "/api/v1/inventory/spools"


async def _make_location(db_session: AsyncSession, name: str) -> Location:
    loc = Location()
    assign_location_name(loc, name)
    db_session.add(loc)
    await db_session.commit()
    await db_session.refresh(loc)
    return loc


async def _make_spool(db_session: AsyncSession, material: str, **kwargs) -> Spool:
    spool = Spool(material=material, **kwargs)
    db_session.add(spool)
    await db_session.commit()
    await db_session.refresh(spool)
    return spool


@pytest.mark.asyncio
@pytest.mark.integration
async def test_filter_narrows_to_one_location(async_client: AsyncClient, db_session: AsyncSession):
    shelf = await _make_location(db_session, "Shelf A")
    drawer = await _make_location(db_session, "Drawer B")
    await _make_spool(db_session, "PLA", location_id=shelf.id)
    await _make_spool(db_session, "PETG", location_id=drawer.id)
    await _make_spool(db_session, "ABS", location_id=None)

    resp = await async_client.get(SPOOLS_URL, params={"location_id": shelf.id})
    assert resp.status_code == 200
    body = resp.json()
    assert [s["material"] for s in body] == ["PLA"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_without_filter_returns_whole_active_inventory(
    async_client: AsyncClient, db_session: AsyncSession
):
    shelf = await _make_location(db_session, "Shelf A")
    await _make_spool(db_session, "PLA", location_id=shelf.id)
    await _make_spool(db_session, "PETG", location_id=None)

    resp = await async_client.get(SPOOLS_URL)
    assert resp.status_code == 200
    assert {s["material"] for s in resp.json()} == {"PLA", "PETG"}


@pytest.mark.asyncio
@pytest.mark.integration
async def test_unknown_location_returns_empty(async_client: AsyncClient, db_session: AsyncSession):
    shelf = await _make_location(db_session, "Shelf A")
    await _make_spool(db_session, "PLA", location_id=shelf.id)

    resp = await async_client.get(SPOOLS_URL, params={"location_id": shelf.id + 999})
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_filter_composes_with_include_archived(
    async_client: AsyncClient, db_session: AsyncSession
):
    """Narrowing by location must not quietly re-admit archived spools, nor
    hide them when they were explicitly asked for."""
    from datetime import datetime, timezone

    shelf = await _make_location(db_session, "Shelf A")
    await _make_spool(db_session, "PLA", location_id=shelf.id)
    await _make_spool(
        db_session, "PETG", location_id=shelf.id, archived_at=datetime.now(timezone.utc)
    )

    active = await async_client.get(SPOOLS_URL, params={"location_id": shelf.id})
    assert active.status_code == 200
    assert [s["material"] for s in active.json()] == ["PLA"]

    with_archived = await async_client.get(
        SPOOLS_URL, params={"location_id": shelf.id, "include_archived": "true"}
    )
    assert with_archived.status_code == 200
    assert {s["material"] for s in with_archived.json()} == {"PLA", "PETG"}
