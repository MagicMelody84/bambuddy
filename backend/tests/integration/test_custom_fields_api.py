"""Custom-field values on the spool create/update routes.

Applying values needs the spool's id, so it can only happen after the row is
committed — which is exactly why the payload has to be *validated* before it.
Rejecting it afterwards answers 400 for a spool that already exists, and the
client, told its create failed, retries into a duplicate.
"""

import pytest
from httpx import AsyncClient

FIELDS = "/api/v1/inventory/custom-fields"
SPOOLS = "/api/v1/inventory/spools"


async def _make_field(client: AsyncClient, **overrides) -> dict:
    payload = {"name": "Kunde", "field_type": "text"}
    payload.update(overrides)
    resp = await client.post(FIELDS, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _spool_count(client: AsyncClient) -> int:
    resp = await client.get(SPOOLS)
    assert resp.status_code == 200
    return len(resp.json())


class TestRejectedValuesLeaveNoSpool:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_an_unknown_field_key_creates_no_spool(self, async_client: AsyncClient):
        before = await _spool_count(async_client)

        resp = await async_client.post(SPOOLS, json={"material": "PLA", "custom_fields": {"does_not_exist": "x"}})

        assert resp.status_code == 400
        assert await _spool_count(async_client) == before

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_value_the_type_rejects_creates_no_spool(self, async_client: AsyncClient):
        field = await _make_field(async_client, name="Lagen", field_type="integer")
        before = await _spool_count(async_client)

        resp = await async_client.post(
            SPOOLS, json={"material": "PLA", "custom_fields": {field["key"]: "not a number"}}
        )

        assert resp.status_code == 400
        assert await _spool_count(async_client) == before

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bulk_create_leaves_no_partial_batch(self, async_client: AsyncClient):
        before = await _spool_count(async_client)

        resp = await async_client.post(
            f"{SPOOLS}/bulk",
            json={"spool": {"material": "PLA", "custom_fields": {"does_not_exist": "x"}}, "quantity": 3},
        )

        assert resp.status_code == 400
        assert await _spool_count(async_client) == before


class TestValuesRoundTrip:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_a_valid_value_is_stored_and_returned(self, async_client: AsyncClient):
        field = await _make_field(async_client)

        created = await async_client.post(SPOOLS, json={"material": "PLA", "custom_fields": {field["key"]: "Acme"}})

        assert created.status_code == 200
        assert created.json()["custom_fields"] == {field["key"]: "Acme"}

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bulk_create_puts_the_value_on_every_spool(self, async_client: AsyncClient):
        field = await _make_field(async_client, name="Charge")

        created = await async_client.post(
            f"{SPOOLS}/bulk",
            json={"spool": {"material": "PLA", "custom_fields": {field["key"]: "B-42"}}, "quantity": 3},
        )

        assert created.status_code == 200
        body = created.json()
        assert len(body) == 3
        assert all(s["custom_fields"] == {field["key"]: "B-42"} for s in body)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_with_a_bad_value_changes_nothing(self, async_client: AsyncClient):
        field = await _make_field(async_client, name="Lagen", field_type="integer")
        spool = (
            await async_client.post(SPOOLS, json={"material": "PLA", "custom_fields": {field["key"]: "12"}})
        ).json()

        resp = await async_client.patch(
            f"{SPOOLS}/{spool['id']}",
            json={"material": "PETG", "custom_fields": {field["key"]: "not a number"}},
        )

        assert resp.status_code == 400
        # The rejected value must not have taken the rest of the edit with it.
        current = (await async_client.get(SPOOLS)).json()[0]
        assert current["material"] == "PLA"
        assert current["custom_fields"] == {field["key"]: "12"}
