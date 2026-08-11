import asyncio
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.models.location import Location
from backend.app.models.location_ha_sensor import LocationHASensor
from backend.app.services.ha_sensor_manager import SensorReading, describe_state, evaluate
from backend.app.services.homeassistant import homeassistant_service
from backend.app.utils.local_time import utcnow_naive

logger = logging.getLogger(__name__)

POLL_INTERVAL = 120


class LocationHASensorManager:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._readings: dict[int, SensorReading] = {}
        self._last_alerting: dict[int, bool] = {}

    def start(self):
        if self._task is None:
            self._task = asyncio.create_task(self._poll_loop())
            logger.info("Home Assistant location-sensor poller started")

    def stop(self):
        if self._task:
            self._task.cancel()
            self._task = None
            logger.info("Home Assistant location-sensor poller stopped")

    def get_reading(self, sensor_id: int) -> SensorReading | None:
        return self._readings.get(sensor_id)

    def forget(self, sensor_id: int):
        self._readings.pop(sensor_id, None)
        self._last_alerting.pop(sensor_id, None)

    async def _poll_loop(self):
        while True:
            try:
                await asyncio.sleep(POLL_INTERVAL)
                await self.poll_once()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Home Assistant location-sensor poll failed: %s", e)

    async def poll_once(self):
        from backend.app.core.database import async_session

        async with async_session() as db:
            result = await db.execute(select(LocationHASensor))
            sensors = list(result.scalars().all())

            live = {s.id for s in sensors}
            for stale in set(self._readings) - live:
                self.forget(stale)

            if not sensors:
                return

            if not await self._configure(db):
                for sensor in sensors:
                    self._readings[sensor.id] = SensorReading(None, None, False, False)
                return

            states = await homeassistant_service.fetch_states(sorted({s.entity_id for s in sensors}))
            await self._apply(db, sensors, states)

    async def refresh_one(self, db: AsyncSession, sensor: LocationHASensor):
        self.forget(sensor.id)
        if not await self._configure(db):
            self._readings[sensor.id] = SensorReading(None, None, False, False)
            return

        states = await homeassistant_service.fetch_states([sensor.entity_id])
        reading = evaluate(sensor, states.get(sensor.entity_id))
        self._readings[sensor.id] = reading
        if reading.reachable:
            self._last_alerting[sensor.id] = reading.alerting

        sensor.last_checked = utcnow_naive()
        if reading.reachable and sensor.last_state != reading.state:
            sensor.last_state = reading.state
            sensor.last_changed = sensor.last_checked
        await db.commit()
        await db.refresh(sensor)

    async def _configure(self, db: AsyncSession) -> bool:
        from backend.app.api.routes.settings import get_homeassistant_settings

        try:
            ha_settings = await get_homeassistant_settings(db)
        except Exception as e:
            logger.warning("Failed to read Home Assistant settings: %s", e)
            return False
        if not ha_settings["ha_url"] or not ha_settings["ha_token"]:
            return False
        homeassistant_service.configure(ha_settings["ha_url"], ha_settings["ha_token"])
        return True

    async def _apply(self, db: AsyncSession, sensors: list[LocationHASensor], states: dict[str, dict | None]):
        from backend.app.services.notification_service import notification_service

        now = utcnow_naive()
        alerts: list[tuple[LocationHASensor, SensorReading]] = []

        for sensor in sensors:
            payload = states.get(sensor.entity_id)
            reading = evaluate(sensor, payload)
            was_alerting = self._last_alerting.get(sensor.id)
            self._readings[sensor.id] = reading

            sensor.last_checked = now
            if reading.reachable:
                if sensor.last_state != reading.state:
                    sensor.last_state = reading.state
                    sensor.last_changed = now

            if sensor.notify_on_alert and reading.reachable and reading.alerting and was_alerting is False:
                alerts.append((sensor, reading))

            if reading.reachable:
                self._last_alerting[sensor.id] = reading.alerting

        await db.commit()

        for sensor, reading in alerts:
            location = await db.get(Location, sensor.location_id)
            try:
                await notification_service.on_location_ha_sensor_alert(
                    location_id=sensor.location_id,
                    location_name=location.name if location else "Unknown",
                    sensor_name=sensor.name,
                    state=describe_state(sensor, reading),
                    db=db,
                )
            except Exception as e:
                logger.warning("Failed to send HA sensor alert for '%s': %s", sensor.name, e)


location_ha_sensor_manager = LocationHASensorManager()
