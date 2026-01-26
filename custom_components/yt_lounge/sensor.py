"""Platform for sensor integration for YTLounge."""

from __future__ import annotations

from typing import cast

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_API_KEY
from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator
from .entity import YTLoungeEntity


YTLOUNGE_BASE_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="video_id",
        name="video ID",
        icon="mdi:movie-cog"
    ),
)
YTLOUNGE_API_SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key="video_title",
        name="video title",
        icon="mdi:movie-open"
    ),
    SensorEntityDescription(
        key="channel",
        name="channel",
        icon="mdi:badge-account-horizontal"
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: YTLoungeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Platform setup using common elements."""

    async_add_entities(
        YTLoungeSensor(entry.runtime_data, description)
        for description in YTLOUNGE_BASE_SENSORS
    )

    if CONF_API_KEY in entry.data:
        async_add_entities(
            YTLoungeSensor(entry.runtime_data, description)
            for description in YTLOUNGE_API_SENSORS
        )

class YTLoungeSensor(YTLoungeEntity, SensorEntity):
    """YTLounge sensor."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator,
        description: SensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.screen_id}_{description.key}_sensor"
        self._attr_name = f"{self.device_name} {description.name}"

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.connected and self.coordinator.subscribed

    @property
    def native_value(self) -> StateType:
        """Sensor status direct from live coordinator data."""
        return cast(StateType, self.coordinator.live_data[self.entity_description.key])
