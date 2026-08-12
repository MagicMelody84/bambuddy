from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from backend.app.services.ha_sensor_manager import SensorReading
from backend.app.services.location_ha_sensor_manager import location_ha_sensor_manager

HUMIDITY = {
    "name": "Drybox Humidity",
    "entity_id": "sensor.drybox_humidity",
    "kind": "numeric",
    "device_class": "humidity",
    "unit": "%",
}
DOOR = {
    "name": "Cabinet Door",
    "entity_id": "binary_sensor.cabinet_door",
    "kind": "binary",
    "device_class": "door",
    "alert_state": "on",
}


@pytest.fixture(autouse=True)
def _no_live_ha():
    with patch.object(location_ha_sensor_manager, "refresh_one", AsyncMock()):
        yield


@pytest.fixture(autouse=True)
def _clean_cache():
    yield
    location_ha_sensor_manager._readings.clear()
    location_ha_sensor_manager._last_alerting.clear()


class TestCrud:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_bind_a_humidity_sensor(self, async_client: AsyncClient, location_factory):
        location = await location_factory()

        response = await async_client.post(
            "/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": location.id}
        )

        assert response.status_code == 200
        body = response.json()
        assert body["entity_id"] == "sensor.drybox_humidity"
        assert body["kind"] == "numeric"
        assert body["show_on_card"] is True
        assert body["notify_on_alert"] is False
        assert "block_print" not in body

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_switch(self, async_client: AsyncClient, location_factory):
        location = await location_factory()

        response = await async_client.post(
            "/api/v1/location-ha-sensors/",
            json={**DOOR, "location_id": location.id, "entity_id": "switch.something"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_kind_that_contradicts_the_entity(self, async_client: AsyncClient, location_factory):
        location = await location_factory()

        response = await async_client.post(
            "/api/v1/location-ha-sensors/",
            json={**HUMIDITY, "location_id": location.id, "kind": "binary"},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_notify_with_nothing_to_trigger_on(self, async_client: AsyncClient, location_factory):
        location = await location_factory()

        response = await async_client.post(
            "/api/v1/location-ha-sensors/",
            json={**DOOR, "location_id": location.id, "alert_state": None, "notify_on_alert": True},
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_duplicate_binding(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        payload = {**HUMIDITY, "location_id": location.id}
        await async_client.post("/api/v1/location-ha-sensors/", json=payload)

        response = await async_client.post("/api/v1/location-ha-sensors/", json=payload)

        assert response.status_code == 400
        assert "already bound" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_an_unknown_location(self, async_client: AsyncClient):
        response = await async_client.post("/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": 9999})

        assert response.status_code == 404

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_accepts_a_coherent_change(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        created = await async_client.post("/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": location.id})
        sensor_id = created.json()["id"]

        response = await async_client.patch(
            f"/api/v1/location-ha-sensors/{sensor_id}",
            json={"alert_above": 60, "notify_on_alert": True, "name": "Box Humidity"},
        )

        assert response.status_code == 200
        assert response.json()["notify_on_alert"] is True
        assert response.json()["name"] == "Box Humidity"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_delete_drops_the_cached_reading(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        created = await async_client.post("/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": location.id})
        sensor_id = created.json()["id"]
        location_ha_sensor_manager._readings[sensor_id] = SensorReading("41.2", 41.2, True, True)

        response = await async_client.delete(f"/api/v1/location-ha-sensors/{sensor_id}")

        assert response.status_code == 200
        assert location_ha_sensor_manager.get_reading(sensor_id) is None


class TestReadings:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_serves_the_cached_reading(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        created = await async_client.post(
            "/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": location.id, "alert_above": 60}
        )
        sensor_id = created.json()["id"]
        location_ha_sensor_manager._readings[sensor_id] = SensorReading("65.0", 65.0, True, True)

        response = await async_client.get(f"/api/v1/location-ha-sensors/by-location/{location.id}/readings")

        assert response.status_code == 200
        reading = response.json()[0]
        assert reading["value"] == 65.0
        assert reading["alerting"] is True
        assert reading["unit"] == "%"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hidden_sensors_stay_off_the_card(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        await async_client.post(
            "/api/v1/location-ha-sensors/",
            json={**HUMIDITY, "location_id": location.id, "show_on_card": False},
        )

        response = await async_client.get(f"/api/v1/location-ha-sensors/by-location/{location.id}/readings")

        assert response.json() == []

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_hidden_sensors_are_included_when_not_restricted_to_the_card(
        self, async_client: AsyncClient, location_factory
    ):
        location = await location_factory()
        await async_client.post(
            "/api/v1/location-ha-sensors/",
            json={**HUMIDITY, "location_id": location.id, "show_on_card": False},
        )

        response = await async_client.get(
            f"/api/v1/location-ha-sensors/by-location/{location.id}/readings?show_on_card=false"
        )

        assert len(response.json()) == 1

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_other_locations_sensors_are_not_listed(self, async_client: AsyncClient, location_factory):
        one = await location_factory()
        two = await location_factory()
        await async_client.post("/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": one.id})

        response = await async_client.get(f"/api/v1/location-ha-sensors/by-location/{two.id}/readings")

        assert response.json() == []


class TestEntityPicker:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_explains_itself_when_ha_is_not_configured(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/location-ha-sensors/entities")

        assert response.status_code == 400
        assert "Home Assistant not configured" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_entities_is_not_parsed_as_a_sensor_id(self, async_client: AsyncClient):
        response = await async_client.get("/api/v1/location-ha-sensors/entities")

        assert response.status_code != 404


class TestCascadeAndUniqueness:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_patch_cannot_create_a_duplicate_binding(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        await async_client.post("/api/v1/location-ha-sensors/", json={**DOOR, "location_id": location.id})
        second = await async_client.post("/api/v1/location-ha-sensors/", json={**HUMIDITY, "location_id": location.id})

        response = await async_client.patch(
            f"/api/v1/location-ha-sensors/{second.json()['id']}",
            json={"entity_id": DOOR["entity_id"], "kind": "binary"},
        )

        assert response.status_code == 400
        assert "already bound" in response.json()["detail"]

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_deleting_a_location_takes_its_sensors(self, async_client: AsyncClient, location_factory):
        location = await location_factory()
        await async_client.post("/api/v1/location-ha-sensors/", json={**DOOR, "location_id": location.id})

        deleted = await async_client.delete(f"/api/v1/inventory/locations/{location.id}")

        assert deleted.status_code == 200
        listed = await async_client.get("/api/v1/location-ha-sensors/")
        assert listed.json() == []


class TestPollInterval:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_defaults_to_120_seconds(self, async_client: AsyncClient):
        interval = await location_ha_sensor_manager._get_poll_interval()

        assert interval == 120

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_reads_the_configured_value(self, async_client: AsyncClient):
        response = await async_client.put("/api/v1/settings/", json={"location_sensor_poll_interval": 300})
        assert response.status_code == 200

        interval = await location_ha_sensor_manager._get_poll_interval()

        assert interval == 300

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_rejects_a_value_below_the_60s_minimum(self, async_client: AsyncClient):
        response = await async_client.put("/api/v1/settings/", json={"location_sensor_poll_interval": 30})

        assert response.status_code == 422

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_clamps_a_stored_value_below_the_minimum(self, async_client: AsyncClient, db_session):
        from backend.app.models.settings import Settings

        db_session.add(Settings(key="location_sensor_poll_interval", value="10"))
        await db_session.commit()

        interval = await location_ha_sensor_manager._get_poll_interval()

        assert interval == 60


class TestSaveSurvivesHomeAssistant:
    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_create_succeeds_even_if_the_first_read_blows_up(self, async_client: AsyncClient, location_factory):
        location = await location_factory()

        with patch.object(location_ha_sensor_manager, "refresh_one", AsyncMock(side_effect=RuntimeError("HA said no"))):
            response = await async_client.post(
                "/api/v1/location-ha-sensors/", json={**DOOR, "location_id": location.id}
            )

        assert response.status_code == 200
        listed = await async_client.get(f"/api/v1/location-ha-sensors/?location_id={location.id}")
        assert len(listed.json()) == 1
