"""Platform for select integration for YouTube Lounge."""

from __future__ import annotations


from collections.abc import Callable, Coroutine
from dataclasses import dataclass
from typing import Any

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription
)

from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator, YtLoungeData
from .entity import YTLoungeEntity

@dataclass(frozen=True, kw_only=True)
class YtLoungeSelectEntityDescription(SelectEntityDescription):
    """Describes YT Lounge entity."""

    options_fn: Callable[[YtLoungeData], Callable[[], Coroutine[Any, Any, None]]]
    set_fn: Callable[[YTLoungeDataUpdateCoordinator, bool], Callable[[], Coroutine[Any, Any, None]]]

YTLOUNGE_SELECTS: tuple[YtLoungeSelectEntityDescription, ...] = (
    YtLoungeSelectEntityDescription(
        key="subtitle_track",
        name="subtitles",
        icon="mdi:closed-caption",
        options_fn=lambda data: ['disabled'] + getattr(data, 'subtitle_options'),
        set_fn=lambda coordinator, value: coordinator.command('set_closed_captions', language_code='' if value == 'disabled' else value, video_id=coordinator.data.video_id),
    ),
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: YTLoungeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Platform setup using common elements."""

    async_add_entities(
        YTLoungeSelect(entry.runtime_data, description)
        for description in YTLOUNGE_SELECTS
    )

class YTLoungeSelect(YTLoungeEntity, SelectEntity):
    """YTLounge select entity."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator,
        description: YtLoungeSelectEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.screen_id}_{description.key}_select"
        self._attr_name = f"{self.device_name} {description.name}"

    @property
    def options(self) -> list[str]:
        """Return a list of available options."""
        return self.entity_description.options_fn(self.coordinator.data)

    @property
    def current_option(self) -> str | None:
        """Return the currently selected option."""
        return getattr(self.coordinator.data, self.entity_description.key)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.set_fn(self.coordinator, option)

