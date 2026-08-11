import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.auth import RequirePermissionIfAuthEnabled
from backend.app.core.database import get_db
from backend.app.core.permissions import Permission
from backend.app.models.location import Location
from backend.app.models.location_ha_sensor import LocationHASensor
from backend.app.models.user import User
from backend.app.schemas.location_ha_sensor import (
    HADisplayEntity,
    LocationHASensorCreate,
    LocationHASensorReading,
    LocationHASensorResponse,
    LocationHASensorUpdate,
)
from backend.app.services.homeassistant import homeassistant_service
from backend.app.services.location_ha_sensor_manager import location_ha_sensor_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/location-ha-sensors", tags=["location-ha-sensors"])

_READ = RequirePermissionIfAuthEnabled(Permission.INVENTORY_READ)
_CREATE = RequirePermissionIfAuthEnabled(Permission.INVENTORY_CREATE)
_UPDATE = RequirePermissionIfAuthEnabled(Permission.INVENTORY_UPDATE)
_DELETE = RequirePermissionIfAuthEnabled(Permission.INVENTORY_DELETE)


async def _refresh_quietly(sensor: LocationHASensor, db: AsyncSession) -> None:
    try:
        await location_ha_sensor_manager.refresh_one(db, sensor)
    except Exception as e:
        logger.warning("Could not read %s right after saving it: %s", sensor.entity_id, e)


@router.get("/", response_model=list[LocationHASensorResponse])
async def list_location_ha_sensors(
    location_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    query = select(LocationHASensor)
    if location_id is not None:
        query = query.where(LocationHASensor.location_id == location_id)
    result = await db.execute(query.order_by(LocationHASensor.location_id, LocationHASensor.sort_order))
    return list(result.scalars().all())


@router.get("/entities", response_model=list[HADisplayEntity])
async def list_bindable_entities(
    search: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    from backend.app.api.routes.settings import get_homeassistant_settings

    ha_settings = await get_homeassistant_settings(db)
    if not ha_settings["ha_url"] or not ha_settings["ha_token"]:
        raise HTTPException(
            400,
            "Home Assistant not configured. Please set HA URL and token in Settings → Network → Home Assistant.",
        )

    entities = await homeassistant_service.list_display_entities(ha_settings["ha_url"], ha_settings["ha_token"], search)
    return [HADisplayEntity(**e) for e in entities]


@router.get("/by-location/{location_id}/readings", response_model=list[LocationHASensorReading])
async def get_location_sensor_readings(
    location_id: int,
    show_on_card: bool = True,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    conditions = [LocationHASensor.location_id == location_id]
    if show_on_card:
        conditions.append(LocationHASensor.show_on_card.is_(True))

    result = await db.execute(
        select(LocationHASensor).where(*conditions).order_by(LocationHASensor.sort_order, LocationHASensor.id)
    )

    readings = []
    for sensor in result.scalars().all():
        cached = location_ha_sensor_manager.get_reading(sensor.id)
        readings.append(
            LocationHASensorReading(
                id=sensor.id,
                name=sensor.name,
                entity_id=sensor.entity_id,
                kind=sensor.kind,
                device_class=sensor.device_class,
                unit=sensor.unit,
                state=cached.state if cached else sensor.last_state,
                value=cached.value if cached else None,
                alerting=cached.alerting if cached else False,
                reachable=cached.reachable if cached else False,
                alert_state=sensor.alert_state,
                alert_above=sensor.alert_above,
                alert_below=sensor.alert_below,
                last_changed=sensor.last_changed,
            )
        )
    return readings


@router.post("/", response_model=LocationHASensorResponse)
async def create_location_ha_sensor(
    data: LocationHASensorCreate,
    db: AsyncSession = Depends(get_db),
    _: User | None = _CREATE,
):
    location = await db.get(Location, data.location_id)
    if not location:
        raise HTTPException(404, "Location not found")

    existing = await db.execute(
        select(LocationHASensor).where(
            LocationHASensor.location_id == data.location_id,
            LocationHASensor.entity_id == data.entity_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(400, f"{data.entity_id} is already bound to this location")

    sensor = LocationHASensor(**data.model_dump())
    db.add(sensor)
    await db.commit()
    await db.refresh(sensor)
    logger.info("Bound HA entity %s to location %s as '%s'", sensor.entity_id, sensor.location_id, sensor.name)

    await _refresh_quietly(sensor, db)
    return sensor


@router.get("/{sensor_id}", response_model=LocationHASensorResponse)
async def get_location_ha_sensor(
    sensor_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = _READ,
):
    sensor = await db.get(LocationHASensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")
    return sensor


@router.patch("/{sensor_id}", response_model=LocationHASensorResponse)
async def update_location_ha_sensor(
    sensor_id: int,
    data: LocationHASensorUpdate,
    db: AsyncSession = Depends(get_db),
    _: User | None = _UPDATE,
):
    sensor = await db.get(LocationHASensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")

    updates = data.model_dump(exclude_unset=True)

    merged = {field: getattr(sensor, field) for field in LocationHASensorCreate.model_fields}
    merged.update(updates)
    try:
        LocationHASensorCreate(**merged)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e

    new_entity = updates.get("entity_id")
    if new_entity and new_entity != sensor.entity_id:
        clash = await db.execute(
            select(LocationHASensor).where(
                LocationHASensor.location_id == sensor.location_id,
                LocationHASensor.entity_id == new_entity,
                LocationHASensor.id != sensor.id,
            )
        )
        if clash.scalar_one_or_none():
            raise HTTPException(400, f"{new_entity} is already bound to this location")

    for field, value in updates.items():
        setattr(sensor, field, value)
    await db.commit()
    await db.refresh(sensor)

    await _refresh_quietly(sensor, db)
    return sensor


@router.delete("/{sensor_id}")
async def delete_location_ha_sensor(
    sensor_id: int,
    db: AsyncSession = Depends(get_db),
    _: User | None = _DELETE,
):
    sensor = await db.get(LocationHASensor, sensor_id)
    if not sensor:
        raise HTTPException(404, "Sensor not found")

    name = sensor.name
    await db.delete(sensor)
    await db.commit()
    location_ha_sensor_manager.forget(sensor_id)
    logger.info("Removed location HA sensor '%s'", name)
    return {"message": f"Sensor '{name}' removed"}
