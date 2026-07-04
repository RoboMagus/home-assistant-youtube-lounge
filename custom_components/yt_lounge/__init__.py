"""The YouTube Lounge integration."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .const import DOMAIN, PLATFORMS
from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: YTLoungeConfigEntry) -> bool:
    """Set up YTLounge from a config entry."""
    coordinator = YTLoungeDataUpdateCoordinator(
        hass, entry
    )
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()

    device_name_parts = coordinator.device_name.split(" ")
    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, coordinator.screen_id)},
        manufacturer=device_name_parts[0],
        model=device_name_parts[1] if len(device_name_parts) > 1 else None,
        name=coordinator.screen_name,
    )

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: YTLoungeConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_config_entry_device(
    hass: HomeAssistant, config_entry: YTLoungeConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    """Remove device from a config entry."""
    return True
