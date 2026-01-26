"""Platform for binary_sensor integration for YTLounge."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator
from .entity import YTLoungeEntity


YTLOUNGE_BINARYSENSORS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="paired",
        name="paired",
        icon="mdi:swap-horizontal",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="linked",
        name="linked",
        icon="mdi:link-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="connected",
        name="connected",
        icon="mdi:connection",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: YTLoungeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Platform setup using common elements."""

    async_add_entities(
        YTLoungeBinarySensor(entry.runtime_data, description)
        for description in YTLOUNGE_BINARYSENSORS
    )

class YTLoungeBinarySensor(YTLoungeEntity, BinarySensorEntity):
    """YTLounge binary sensor."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.screen_id}_{description.key}_binary_sensor"
        self._attr_name = f"{self.device_name} {description.name}"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return getattr(self.coordinator, self.entity_description.key)