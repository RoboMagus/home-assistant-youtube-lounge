"""Base Entity for YouTube Lounge."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import YTLoungeDataUpdateCoordinator


class YTLoungeEntity(CoordinatorEntity[YTLoungeDataUpdateCoordinator]):
    """Defines a base YouTube Lounge entity."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator
    ) -> None:
        """Initialize the YouTube Lounge entity."""
        super().__init__(coordinator)
        self.device_name: str = coordinator.device_name or "?"
        self.screen_name: str = coordinator.screen_name or "?"

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.screen_id)},
            model=self.screen_name,
            name=self.device_name,
        )