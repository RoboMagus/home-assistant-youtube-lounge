"""Platform for sensor integration for YouTube Lounge."""

from __future__ import annotations

from collections.abc import Callable, Coroutine, Mapping
from dataclasses import dataclass
from typing import cast, override, Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .const import CONF_API_KEY
from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator, YtLoungeData
from .entity import YTLoungeEntity

@dataclass(frozen=True, kw_only=True)
class YtLoungeExtendedSensorEntityDescription(SensorEntityDescription):
    """Describes YT Lounge entity."""

    state_fn: Callable[[YtLoungeData], Callable[[], Coroutine[Any, Any, StateType]]]
    attrs_fn: Callable[[YtLoungeData], Callable[[], Coroutine[Any, Any, Mapping[str, Any]]]]

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
YTLOUNGE_EXTENDED_SENSORS: tuple[YtLoungeExtendedSensorEntityDescription, ...] = (
    YtLoungeExtendedSensorEntityDescription(
        key="playlist_items",
        name="playlist items",
        icon="mdi:playlist-play",
        native_unit_of_measurement="",
        state_fn=lambda data: len(getattr(data, 'playlist_items')),
        attrs_fn=lambda data: {
            "playlist_items": getattr(data, 'playlist_items'),
            "remaining": 0 if not getattr(data, "video_id") else len(l := getattr(data, "playlist_items")) - get_video_index(l, getattr(data, "video_id")) - 1
        },
    ),
    YtLoungeExtendedSensorEntityDescription(
        key="connected_clients",
        name="connected clients",
        icon="mdi:devices",
        native_unit_of_measurement="",
        state_fn=lambda data: len(getattr(data, 'connected_clients')),
        attrs_fn=lambda data: {
            "connected_clients": getattr(data, 'connected_clients')
        },
    ),
)

def get_video_index(playlist, vid):
    for i, v in enumerate(playlist):
        if v.get("id") == vid:
            return i
    return 0

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
    async_add_entities(
        YTLoungeExtendedSensor(entry.runtime_data, description)
        for description in YTLOUNGE_EXTENDED_SENSORS
    )

    if entry.data.get(CONF_API_KEY):
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
        return cast(StateType, getattr(self.coordinator.data, self.entity_description.key))

class YTLoungeExtendedSensor(YTLoungeEntity, SensorEntity):
    """YTLounge sensor."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator,
        description: YtLoungeExtendedSensorEntityDescription,
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

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Handle updated data from the coordinator."""
        self._async_update_attrs()
        super()._handle_coordinator_update()

    @callback
    def _async_update_attrs(self) -> None:
        """Handle coordinator updates."""
        if self.available:
            self._attr_native_value = self.entity_description.state_fn(self.coordinator.data)
            self._attr_extra_state_attributes = self.entity_description.attrs_fn(self.coordinator.data)
