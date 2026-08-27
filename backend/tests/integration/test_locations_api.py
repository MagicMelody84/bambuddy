"""Integration tests for /inventory/locations (#1004)."""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.location import Location
from backend.app.services.location_service import assign_location_name


@pytest.mark.asyncio
@pytest.mark.integration
async def test_locations_crud_and_spool_link(async_client: AsyncClient, db_session: AsyncSession):
    create_resp = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf A"})
    assert create_resp.status_code == 201
    loc = create_resp.json()
    assert loc["name"] == "Shelf A"
    assert loc["spool_count"] == 0

    dup_resp = await async_client.post("/api/v1/inventory/locations", json={"name": "shelf a"})
    assert dup_resp.status_code == 409

    spool_resp = await async_client.post(
        "/api/v1/inventory/spools",
        json={"material": "PLA", "location_id": loc["id"]},
    )
    assert spool_resp.status_code == 200
    spool = spool_resp.json()
    assert spool["location_id"] == loc["id"]
    assert spool["storage_location"] == "Shelf A"

    list_resp = await async_client.get("/api/v1/inventory/locations")
    assert list_resp.status_code == 200
    listed = {item["id"]: item for item in list_resp.json()}
    assert listed[loc["id"]]["spool_count"] == 1

    delete_resp = await async_client.delete(f"/api/v1/inventory/locations/{loc['id']}")
    assert delete_resp.status_code == 409

    clear_resp = await async_client.patch(
        f"/api/v1/inventory/spools/{spool['id']}",
        json={"location_id": None},
    )
    assert clear_resp.status_code == 200

    delete_resp2 = await async_client.delete(f"/api/v1/inventory/locations/{loc['id']}")
    assert delete_resp2.status_code == 200


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_location_by_tag(async_client: AsyncClient):
    create_resp = await async_client.post(
        "/api/v1/inventory/locations", json={"name": "Shelf C", "tag_uid": "04a1b2c3d4"}
    )
    assert create_resp.status_code == 201
    loc = create_resp.json()

    # Lookup normalizes to uppercase hex, so a differently-cased/spaced query
    # still matches what was stored.
    found_resp = await async_client.get("/api/v1/inventory/locations/by-tag", params={"tag_uid": "04:A1:B2:C3:D4"})
    assert found_resp.status_code == 200
    assert found_resp.json()["id"] == loc["id"]

    missing_resp = await async_client.get("/api/v1/inventory/locations/by-tag", params={"tag_uid": "FFFFFFFFFF"})
    assert missing_resp.status_code == 404

    empty_resp = await async_client.get("/api/v1/inventory/locations/by-tag", params={"tag_uid": "xyz"})
    assert empty_resp.status_code == 400


@pytest.mark.asyncio
@pytest.mark.integration
async def test_a_tag_cannot_be_assigned_to_two_locations(async_client: AsyncClient):
    """One physical tag, one shelf.

    /locations/by-tag answers a scan with a single row, so a UID on two
    locations makes it resolve to whichever has the lower id — the scan lands
    on the wrong shelf with nothing to indicate it.
    """
    first = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf D", "tag_uid": "AABBCCDD"})
    assert first.status_code == 201

    # Same tag, differently formatted — normalization must not let it through.
    clash = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf E", "tag_uid": "aa:bb:cc:dd"})
    assert clash.status_code == 409
    assert "NFC tag" in clash.json()["detail"]

    # The scan still resolves to the one location that owns the tag.
    resolved = await async_client.get("/api/v1/inventory/locations/by-tag", params={"tag_uid": "AABBCCDD"})
    assert resolved.status_code == 200
    assert resolved.json()["id"] == first.json()["id"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_patch_cannot_steal_another_locations_tag(async_client: AsyncClient):
    owner = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf F", "tag_uid": "11223344"})
    assert owner.status_code == 201
    other = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf G"})
    other_id = other.json()["id"]

    clash = await async_client.patch(f"/api/v1/inventory/locations/{other_id}", json={"tag_uid": "11223344"})
    assert clash.status_code == 409

    # Re-writing a location's own tag stays allowed — that is the ordinary
    # scan-and-save flow, not a conflict.
    same = await async_client.patch(
        f"/api/v1/inventory/locations/{owner.json()['id']}", json={"tag_uid": "11:22:33:44"}
    )
    assert same.status_code == 200
    assert same.json()["tag_uid"] == "11223344"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_untagged_locations_do_not_collide(async_client: AsyncClient):
    """NULL tag_uid must stay distinct — otherwise the unique index would let
    exactly one location exist without a tag."""
    for name in ("Untagged 1", "Untagged 2", "Untagged 3"):
        resp = await async_client.post("/api/v1/inventory/locations", json={"name": name})
        assert resp.status_code == 201, resp.text


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_location_can_clear_tag_uid(async_client: AsyncClient):
    # Regression: PATCH with tag_uid=null must clear the field. An earlier
    # `if data.tag_uid is not None` guard couldn't distinguish "omitted" from
    # "explicitly cleared" — both parse to None — so a clear request silently
    # left the old tag_uid in place.
    create_resp = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf B"})
    assert create_resp.status_code == 201
    loc_id = create_resp.json()["id"]

    set_resp = await async_client.patch(f"/api/v1/inventory/locations/{loc_id}", json={"tag_uid": "04A1B2C3D4"})
    assert set_resp.status_code == 200
    assert set_resp.json()["tag_uid"] == "04A1B2C3D4"

    clear_resp = await async_client.patch(f"/api/v1/inventory/locations/{loc_id}", json={"tag_uid": None})
    assert clear_resp.status_code == 200
    assert clear_resp.json()["tag_uid"] is None

    # Omitting tag_uid entirely must leave a previously-set value untouched.
    await async_client.patch(f"/api/v1/inventory/locations/{loc_id}", json={"tag_uid": "04A1B2C3D4"})
    untouched_resp = await async_client.patch(f"/api/v1/inventory/locations/{loc_id}", json={"name": "Shelf B Renamed"})
    assert untouched_resp.status_code == 200
    assert untouched_resp.json()["tag_uid"] == "04A1B2C3D4"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_locations_sorts_naturally_not_lexicographically(async_client: AsyncClient):
    # Created out of order and with a name-shape ("Drybox N") that a plain
    # ORDER BY name would sort as "Drybox 1", "Drybox 10", "Drybox 2".
    for name in ["Drybox 10", "Drybox 2", "Drybox 1", "Shelf A"]:
        resp = await async_client.post("/api/v1/inventory/locations", json={"name": name})
        assert resp.status_code == 201, resp.text

    list_resp = await async_client.get("/api/v1/inventory/locations")
    assert list_resp.status_code == 200
    names = [loc["name"] for loc in list_resp.json()]
    assert names == ["Drybox 1", "Drybox 2", "Drybox 10", "Shelf A"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rename_location_updates_spool_count(async_client: AsyncClient):
    create_resp = await async_client.post("/api/v1/inventory/locations", json={"name": "Old Name"})
    loc = create_resp.json()

    await async_client.post(
        "/api/v1/inventory/spools",
        json={"material": "PLA", "location_id": loc["id"]},
    )

    list_before = await async_client.get("/api/v1/inventory/locations")
    by_id = {item["id"]: item for item in list_before.json()}
    assert by_id[loc["id"]]["spool_count"] == 1

    rename_resp = await async_client.patch(
        f"/api/v1/inventory/locations/{loc['id']}",
        json={"name": "New Name"},
    )
    assert rename_resp.status_code == 200
    assert rename_resp.json()["name"] == "New Name"
    assert rename_resp.json()["spool_count"] == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_rename_location_collision_returns_409(async_client: AsyncClient):
    first = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf A"})
    second = await async_client.post("/api/v1/inventory/locations", json={"name": "Shelf B"})
    assert first.status_code == 201
    assert second.status_code == 201

    collision = await async_client.patch(
        f"/api/v1/inventory/locations/{second.json()['id']}",
        json={"name": "Shelf A"},
    )
    assert collision.status_code == 409
    assert collision.json()["detail"] == "A location with this name already exists"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_create_location_duplicate_after_commit_returns_409(async_client: AsyncClient):
    """Second create with the same name_key must return 409, not 500."""
    first = await async_client.post("/api/v1/inventory/locations", json={"name": "Race Shelf"})
    second = await async_client.post("/api/v1/inventory/locations", json={"name": "race shelf"})
    assert first.status_code == 201
    assert second.status_code == 409
    assert second.json()["detail"] == "A location with this name already exists"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_locations_is_read_only(async_client: AsyncClient, db_session: AsyncSession):
    """GET /locations is a pure read — no catalog rows appear without explicit writes."""
    from sqlalchemy import func, select

    loc = Location()
    assign_location_name(loc, "Local Only")
    db_session.add(loc)
    await db_session.commit()

    before = await db_session.scalar(select(func.count()).select_from(Location))
    resp = await async_client.get("/api/v1/inventory/locations")
    after = await db_session.scalar(select(func.count()).select_from(Location))

    assert resp.status_code == 200
    assert len(resp.json()) == 1
    assert before == after == 1


@pytest.mark.asyncio
@pytest.mark.integration
async def test_update_location_404_on_unknown_id(async_client: AsyncClient):
    resp = await async_client.patch(
        "/api/v1/inventory/locations/99999",
        json={"name": "Ghost"},
    )
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Location not found"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_delete_location_404_on_unknown_id(async_client: AsyncClient):
    resp = await async_client.delete("/api/v1/inventory/locations/99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Location not found"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_locations_routes_require_auth_when_enabled(async_client: AsyncClient):
    """All five /locations endpoints must return 401 when auth is enabled and
    no credentials are presented. Mirror of the pattern from
    test_queue_start_user_attribution._enable_auth_with_admin — required by
    project policy: every permission-gated route gets a fail-closed test on
    first ship, no follow-ups (the two CVSS 9.8/9.9 advisories shipped from
    this exact gap)."""
    await async_client.post(
        "/api/v1/auth/setup",
        json={
            "auth_enabled": True,
            "admin_username": "locations1505admin",
            "admin_password": "AdminPass1!",
        },
    )

    # GET /locations — read-gated
    list_resp = await async_client.get("/api/v1/inventory/locations")
    assert list_resp.status_code == 401, list_resp.text

    # POST /locations — write-gated
    create_resp = await async_client.post("/api/v1/inventory/locations", json={"name": "Locked"})
    assert create_resp.status_code == 401, create_resp.text

    # PATCH /locations/{id} — write-gated. Use a synthetic id; the auth gate
    # runs before the not-found check, so 401 is the correct expectation even
    # when the id doesn't exist.
    patch_resp = await async_client.patch("/api/v1/inventory/locations/99999", json={"name": "Locked2"})
    assert patch_resp.status_code == 401, patch_resp.text

    # DELETE /locations/{id} — write-gated
    delete_resp = await async_client.delete("/api/v1/inventory/locations/99999")
    assert delete_resp.status_code == 401, delete_resp.text
