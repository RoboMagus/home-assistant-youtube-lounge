"""Data update coordinator for the Jellyfin integration."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Optional

from googleapiclient.discovery import build
from pyytlounge import (
    YtLoungeApi,
    EventListener,
    PlaybackStateEvent,
    NowPlayingEvent,
    VolumeChangedEvent,
    AutoplayModeChangedEvent,
    DisconnectedEvent,
    PlaybackSpeedEvent,
)

from homeassistant import exceptions
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .const import CONF_API_KEY, CONF_AUTH_STATE, CONF_SCREEN_ID, DOMAIN, LOGGER

type YTLoungeConfigEntry = ConfigEntry[YTLoungeDataUpdateCoordinator]


class YTLoungeDataUpdateCoordinator(DataUpdateCoordinator[dict[str, dict[str, Any]]], EventListener):
    """Data update coordinator for the Jellyfin integration."""

    config_entry: YTLoungeConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: YTLoungeConfigEntry,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass=hass,
            logger=LOGGER,
            config_entry=config_entry,
            name=DOMAIN,
            update_interval=timedelta(seconds=10),
        )

        self.api_client = YtLoungeApi("Test", self, LOGGER)
        self.api_client.session = async_create_clientsession(hass, auto_cleanup=False)

        self.subscribe_task = None
        self.last_video_id = None
        self.live_data = {
            'state': None,
            'video_id': None,
            'video_title': None,
            'channel': None,
            'current_time': None,
            'current_time_updated': None,
            'duration': None,
            'volume': 100,
            'muted': False,
            'autoplay': None,
            'playback_speed': None,
            'connected': False,
        }

    async def async_initialize(self) -> None:
        """Initialize the coordinator."""

        # ToDo: Handle path with pairing code in config_flow!
        LOGGER.debug(f"Initializing with config_entry.data: {self.config_entry.data}")

        self.api_client.load_auth_state(self.config_entry.data[CONF_AUTH_STATE])
        LOGGER.debug(f"API: {self.api_client}")
        is_available = await self.api_client.is_available()
        LOGGER.debug(f"Screen availability: {is_available}")

        LOGGER.debug("Connecting...")
        connected = await self.api_client.connect()
        LOGGER.debug(connected and "success" or "failed")
        if not connected:
            raise CannotConnect

        self.screen_id = self.api_client.auth.screen_id
        self.screen_name = self.api_client.screen_name
        self.device_name = self.api_client.screen_device_name
        LOGGER.debug(f"ScreenID: {self.screen_id}")
        LOGGER.debug(f"ScreenName: {self.screen_name}")
        LOGGER.debug(f"DeviceName: {self.device_name}")

        # Subscribe may take a LONG while... run in background instead
        self.subscribe_task = asyncio.create_task(self.api_client.subscribe())

        @callback
        def _async_stop(_: Event) -> None:
            self.api_client.session.detach()
            if self.subscribe_task is not None:
                self.subscribe_task.cancel()

        # Make sure task is cancelled on shutdown (or tests complete)
        self.config_entry.async_on_unload(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
        )

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #   YTLounge Event listener hooks
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    async def playback_state_changed(self, event: PlaybackStateEvent) -> None:
        """Called when playback state changes (position, play/pause)"""
        self.live_data['connected'] = True
        self.live_data['state'] = event.state
        self.live_data['current_time'] = event.current_time
        self.live_data['current_time_updated'] = utcnow()
        self.live_data['duration'] = event.duration
        LOGGER.debug(
            f"New state: {event.state} = id: {self.live_data['video_id']} pos: {event.current_time} duration: {event.duration}"
        )

    async def now_playing_changed(self, event: NowPlayingEvent) -> None:
        """Called when active video changes"""
        self.live_data['connected'] = True
        self.live_data['state'] = event.state
        self.live_data['video_id'] = event.video_id
        self.live_data['current_time'] = event.current_time
        self.live_data['current_time_updated'] = utcnow()
        self.live_data['duration'] = event.duration
        LOGGER.debug(
            f"New state: {event.state} = id: {event.video_id} pos: {event.current_time} duration: {event.duration}"
        )

    async def volume_changed(self, event: VolumeChangedEvent) -> None:
        """Called when volume or muted state changes"""
        self.live_data['connected'] = True
        self.live_data['volume'] = event.volume
        self.live_data['muted'] = event.muted
        LOGGER.debug(f"Volume changed: {event.volume}% muted: {event.muted}")

    async def autoplay_changed(self, event: AutoplayModeChangedEvent) -> None:
        """Called when auto play mode changes"""
        self.live_data['connected'] = True
        self.live_data['autoplay'] = event.enabled
        LOGGER.debug(
            f"Auto play changed: {event.enabled} {'(not supported)' if not event.supported else ''}"
        )

    async def playback_speed_changed(self, event: PlaybackSpeedEvent) -> None:
        """Called when playback speed changes"""
        self.live_data['connected'] = True
        self.live_data['playback_speed'] = event.playback_speed
        LOGGER.debug(f"Playback speed changed: {event.playback_speed}")

    async def disconnected(self, event: DisconnectedEvent) -> None:
        """Called when the screen is no longer connected"""
        self.live_data['connected'] = False
        self.live_data['video_id'] = None
        LOGGER.debug(f"Disconnected with Reason: {event.reason}")
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    #   YTLounge Event listener hooks
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    async def _async_update_data(self) -> dict[str, dict[str, Any]]:
        """Get the latest data from Jellyfin."""
        LOGGER.debug(self.live_data)

        def get_video_data(video_id: str, api_key: str) -> dict:
            youtube = build('youtube', 'v3', developerKey=api_key)
            request = youtube.videos().list(part='snippet', id=video_id)
            return request.execute()

        if (vid := self.live_data['video_id']) and vid != self.last_video_id:
            self.last_video_id = vid
            video_data = await self.hass.async_add_executor_job(get_video_data, vid, self.config_entry.data[CONF_API_KEY])
            LOGGER.debug(f"YT API Response: {video_data}")
            self.live_data['video_title'] = video_data['items'][0]['snippet']['title']
            self.live_data['channel'] = video_data['items'][0]['snippet']['channelTitle']

        # ToDo: Fill structure...
        return {}

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate the server is unreachable."""