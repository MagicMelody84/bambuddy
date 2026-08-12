from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.app.services.location_ha_sensor_manager import LocationHASensorManager


def _sensor(**overrides):
    base = {
        "id": 1,
        "location_id": 7,
        "name": "Drybox Humidity",
        "entity_id": "sensor.drybox_humidity",
        "kind": "numeric",
        "device_class": "humidity",
        "unit": "%",
        "alert_state": None,
        "alert_above": 60,
        "alert_below": None,
        "notify_on_alert": False,
        "last_state": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


class TestNotificationEdge:
    async def _apply(self, manager, sensor, states, notify):
        db = AsyncMock()
        db.get.return_value = SimpleNamespace(name="Drybox 1")
        with patch("backend.app.services.notification_service.notification_service", notify):
            await manager._apply(db, [sensor], states)

    @pytest.mark.asyncio
    async def test_fires_once_on_the_way_in(self):
        manager = LocationHASensorManager()
        sensor = _sensor(notify_on_alert=True)
        notify = AsyncMock()

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "40"}}, notify)
        assert notify.on_location_ha_sensor_alert.await_count == 0

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "65"}}, notify)
        assert notify.on_location_ha_sensor_alert.await_count == 1

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "66"}}, notify)
        assert notify.on_location_ha_sensor_alert.await_count == 1

    @pytest.mark.asyncio
    async def test_silent_on_the_first_poll_after_a_restart(self):
        manager = LocationHASensorManager()
        sensor = _sensor(notify_on_alert=True)
        notify = AsyncMock()

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "65"}}, notify)

        assert notify.on_location_ha_sensor_alert.await_count == 0
        assert manager.get_reading(sensor.id).alerting is True

    @pytest.mark.asyncio
    async def test_silent_when_the_sensor_opts_out(self):
        manager = LocationHASensorManager()
        sensor = _sensor(notify_on_alert=False)
        notify = AsyncMock()

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "40"}}, notify)
        await self._apply(manager, sensor, {sensor.entity_id: {"state": "65"}}, notify)

        assert notify.on_location_ha_sensor_alert.await_count == 0

    @pytest.mark.asyncio
    async def test_passes_the_location_name_not_a_printer_name(self):
        manager = LocationHASensorManager()
        sensor = _sensor(notify_on_alert=True)
        notify = AsyncMock()

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "40"}}, notify)
        await self._apply(manager, sensor, {sensor.entity_id: {"state": "65"}}, notify)

        notify.on_location_ha_sensor_alert.assert_awaited_once()
        _, kwargs = notify.on_location_ha_sensor_alert.await_args
        assert kwargs["location_id"] == 7
        assert kwargs["location_name"] == "Drybox 1"
        assert kwargs["sensor_name"] == "Drybox Humidity"

    @pytest.mark.asyncio
    async def test_a_dropout_does_not_count_as_the_alert_clearing(self):
        manager = LocationHASensorManager()
        sensor = _sensor(notify_on_alert=True)
        notify = AsyncMock()

        await self._apply(manager, sensor, {sensor.entity_id: {"state": "40"}}, notify)
        await self._apply(manager, sensor, {sensor.entity_id: {"state": "65"}}, notify)
        await self._apply(manager, sensor, {sensor.entity_id: None}, notify)
        await self._apply(manager, sensor, {sensor.entity_id: {"state": "66"}}, notify)

        assert notify.on_location_ha_sensor_alert.await_count == 1


class TestNoInterlock:
    def test_manager_has_no_blocked_locations_concept(self):
        manager = LocationHASensorManager()

        assert not hasattr(manager, "blocked_printers")
        assert not hasattr(manager, "blocked_locations")
