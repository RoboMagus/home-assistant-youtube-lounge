"""Data update coordinator for the Jellyfin integration."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
import logging
from typing import Any, Optional
from time import time

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
from homeassistant.helpers.event import async_call_later, async_track_time_interval
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .const import CONF_API_KEY, CONF_AUTH_STATE, CONF_DEVICE_NAME, CONF_SCREEN_ID, CONF_SCREEN_NAME, DOMAIN

LOGGER = logging.getLogger(__name__)

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
            update_interval=timedelta(seconds=60),
        )

        self.api_client = YtLoungeApi("HomeAssistant", self, logging.getLogger(f"{__package__}.pyytlounge"))
        self.api_client.session = async_create_clientsession(hass, auto_cleanup=False)

        self.screen_id = config_entry.data[CONF_SCREEN_ID]
        self.screen_name = config_entry.data[CONF_SCREEN_NAME]
        self.device_name = config_entry.data[CONF_DEVICE_NAME]

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

        LOGGER.debug(f"ScreenID: {self.screen_id}")
        LOGGER.debug(f"ScreenName: {self.screen_name}")
        LOGGER.debug(f"DeviceName: {self.device_name}")

        @callback
        def _async_stop(_: Event) -> None:
            self.api_client.session.detach()
            if self.subscribe_task is not None:
                self.subscribe_task.cancel()
                self.subscribe_task = None

        # Make sure task is cancelled on shutdown (or tests complete)
        self.config_entry.async_on_unload(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
        )

        # Refresh auth every 72 hours; safe margin within 13 day limit
        async_track_time_interval(
            self.hass, self.refresh_auth, timedelta(hours=72), cancel_on_shutdown=True
        )

    async def refresh_auth(self, _now: datetime|None = None) -> None:
        await self.api_client.refresh_auth()

        data = {
            **self.config_entry.data,
            CONF_AUTH_STATE: self.api_client.auth.serialize(),
        }
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)

    async def get_now_playing(self, now: datetime | None = None) -> None:
        await self.api_client.get_now_playing()

    async def command(self, func_name: str, **kwargs) -> Any:
        f = getattr(self.api_client, func_name, None)
        if not f:
            raise NoSuchMethod

        if not self.connected:
            LOGGER.debug(f"Client not connected when calling {func_name}, trying to connect...")
            await self.api_client.connect()

        if not self.subscribed:
            LOGGER.debug(f"Subscribtion inactive when calling {func_name}, trying to subscribe...")
            await self.subscribe(True)

        LOGGER.debug(f"Command: {func_name}({kwargs})")
        return await f(**kwargs)

    @property
    def paired(self) -> bool:
        return self.api_client.paired()

    @property
    def linked(self) -> bool:
        return self.api_client.linked()

    @property
    def connected(self) -> bool:
        return self.api_client.connected()

    @property
    def subscribed(self) -> bool:
        return self.subscribe_task is not None

    async def subscribe(self, enable: bool):
        if enable != self.subscribed:
            LOGGER.info(f"Subscribe({enable})")
            if enable:
                async def subscribe_keepalive():
                    while True:
                        t0 = time()
                        if not self.connected:
                            LOGGER.debug("Client not connected in subscribe task, trying to connect...")
                            await self.api_client.connect()
                        await self.api_client.subscribe()
                        t1 = time()
                        LOGGER.info(f"Subscribe Keepalive; refresh after {t1 - t0}")

                self.subscribe_task = asyncio.create_task(subscribe_keepalive(), name="YtLounge-Subscribe")
                async_call_later(self.hass, timedelta(seconds=3), self.get_now_playing)
            else:
                if self.subscribe_task is not None:
                    self.subscribe_task.cancel()
                    self.subscribe_task = None

        await self.async_request_refresh()

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
        await self.async_refresh()

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
        await self.async_refresh()

    async def volume_changed(self, event: VolumeChangedEvent) -> None:
        """Called when volume or muted state changes"""
        self.live_data['connected'] = True
        self.live_data['volume'] = event.volume
        self.live_data['muted'] = event.muted
        LOGGER.debug(f"Volume changed: {event.volume}% muted: {event.muted}")
        await self.async_request_refresh()

    async def autoplay_changed(self, event: AutoplayModeChangedEvent) -> None:
        """Called when auto play mode changes"""
        self.live_data['connected'] = True
        self.live_data['autoplay'] = event.enabled
        LOGGER.debug(
            f"Auto play changed: {event.enabled} {'(not supported)' if not event.supported else ''}"
        )
        await self.async_request_refresh()

    async def playback_speed_changed(self, event: PlaybackSpeedEvent) -> None:
        """Called when playback speed changes"""
        self.live_data['connected'] = True
        self.live_data['playback_speed'] = event.playback_speed
        LOGGER.debug(f"Playback speed changed: {event.playback_speed}")
        await self.async_request_refresh()

    async def disconnected(self, event: DisconnectedEvent) -> None:
        """Called when the screen is no longer connected"""
        self.live_data['connected'] = False
        self.live_data['video_id'] = None
        LOGGER.debug(f"Disconnected with Reason: {event.reason}")
        await self.async_request_refresh()
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

class NoSuchMethod(exceptions.HomeAssistantError):
    """Requested method does not exist."""
