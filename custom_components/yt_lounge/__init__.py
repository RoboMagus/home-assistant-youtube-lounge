"""The YouTube Lounge integration."""

from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from pyytlounge import YtLoungeApi

from .const import DOMAIN, PLATFORMS
from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator


async def async_setup_entry(hass: HomeAssistant, entry: YTLoungeConfigEntry) -> bool:
    """Set up YTLounge from a config entry."""
    coordinator = YTLoungeDataUpdateCoordinator(
        hass, entry
    )
    await coordinator.async_initialize()
    await coordinator.async_config_entry_first_refresh()

    device_registry = dr.async_get(hass)
    device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        entry_type=dr.DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, coordinator.screen_id)},
        manufacturer="YouTube",
        name="Dummy",
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
    coordinator = config_entry.runtime_data

    return not device_entry.identifiers.intersection(
        (
            (DOMAIN, coordinator.server_id),
            *((DOMAIN, device_id) for device_id in coordinator.device_ids),
        )
    )
