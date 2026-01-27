"""Platform for switch integration for YouTube Lounge."""

from __future__ import annotations


from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import (
    SwitchEntity,
    SwitchEntityDescription
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator
from .entity import YTLoungeEntity

@dataclass(frozen=True, kw_only=True)
class YtLoungeSwitchEntityDescription(SwitchEntityDescription):
    """Describes YT Lounge entity."""

    icon_fn: Callable[[YTLoungeDataUpdateCoordinator], Callable[[], Coroutine[Any, Any, None]]]
    set_fn: Callable[[YTLoungeDataUpdateCoordinator, bool], Callable[[], Coroutine[Any, Any, None]]]

YTLOUNGE_SWITCHES: tuple[YtLoungeSwitchEntityDescription, ...] = (
    YtLoungeSwitchEntityDescription(
        key="subscribed",
        name="subscribed",
        icon_fn=lambda is_on: "mdi:bell-ring" if is_on else "mdi:bell-off",
        set_fn=lambda coordinator, on: coordinator.subscribe(on),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: YTLoungeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Platform setup using common elements."""

    async_add_entities(
        YTLoungeSwitch(entry.runtime_data, description)
        for description in YTLOUNGE_SWITCHES
    )

class YTLoungeSwitch(YTLoungeEntity, SwitchEntity):
    """YTLounge binary sensor."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator,
        description: YtLoungeSwitchEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.screen_id}_{description.key}_switch"
        self._attr_name = f"{self.device_name} {description.name}"

    @property
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        return getattr(self.coordinator, self.entity_description.key)

    @property
    def icon(self) -> str | None:
        return self.entity_description.icon_fn(self.is_on)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn off the switch."""
        await self.entity_description.set_fn(self.coordinator, False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn on the switch."""
        await self.entity_description.set_fn(self.coordinator, True)
