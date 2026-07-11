"""Data update coordinator for the YouTube Lounge integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import partial
import json
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
    AdStateEvent,
    AdPlayingEvent,
    AutoplayModeChangedEvent,
    AutoplayUpNextEvent,
    DisconnectedEvent,
    PlaybackSpeedEvent,
    SubtitlesTrackEvent,
)
from pyytlounge.api import get_thumbnail_url
from pyytlounge.models import State as PlaybackState

from homeassistant import exceptions
from homeassistant.components.media_player import MediaPlayerState
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from .const import CONF_API_KEY, CONF_AUTH_STATE, CONF_DEVICE_NAME, CONF_SCREEN_ID, CONF_SCREEN_NAME, DOMAIN

LOGGER = logging.getLogger(__name__)

type YTLoungeConfigEntry = ConfigEntry[YTLoungeDataUpdateCoordinator]

@dataclass
class YtLoungeData:
    """Data from YouTube Lounge API."""

    connected: bool
    playback_state: PlaybackState
    mediaplayer_state: MediaPlayerState

    video_id: str | None
    video_title: str | None
    thumbnail_url: str | None
    channel: str | None

    subtitle_track: str | None
    subtitle_options: list[str]

    duration: float
    current_time: float
    current_time_updated: datetime | None

    volume: float
    muted: bool

def PlaybackState2MediaPlayerState(state: PlaybackState) -> MediaPlayerState:
    state_map = {
        PlaybackState.Stopped: MediaPlayerState.IDLE,
        PlaybackState.Buffering: MediaPlayerState.BUFFERING,
        PlaybackState.Playing: MediaPlayerState.PLAYING,
        PlaybackState.Paused: MediaPlayerState.PAUSED,
        PlaybackState.Starting: MediaPlayerState.BUFFERING,
    }

    return state_map.get(state, MediaPlayerState.IDLE)

class YTLoungeDataUpdateCoordinator(DataUpdateCoordinator[YtLoungeData], EventListener):
    """Data update coordinator for the YouTube Lounge integration."""

    config_entry: YTLoungeConfigEntry
    yt_api = None

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

        self.auto_disconnect = False
        self.cancel_auth_refresh = None
        self.subscribe_task = None
        self.last_video_id = None
        self.live_data = {
            'state': None,
            'video_id': None,
            'video_title': None,
            'channel': None,
            'subtitle_track': None,
            'subtitle_options': [],
            'current_time': None,
            'current_time_updated': None,
            'duration': None,
            'volume': 100,
            'muted': False,
            'autoplay': None,
            'playback_speed': None,
            'connected': False,
        }
        self.connected_devices = []

    async def async_initialize(self) -> None:
        """Initialize the coordinator."""

        if (api_key := self.config_entry.data.get(CONF_API_KEY)):
            self.yt_api = await self.hass.async_add_executor_job(
                partial(build, "youtube", "v3", cache_discovery=False, developerKey=api_key)
            )

        self.api_client.load_auth_state(self.config_entry.data[CONF_AUTH_STATE])

        connected = await self.api_client.connect()
        if not connected:
            raise CannotConnect

        @callback
        def _async_stop(_: Event) -> None:
            self.api_client.session.detach()
            if self.subscribe_task:
                self.subscribe_task.cancel()
                self.subscribe_task = None
            if self.cancel_auth_refresh:
                self.cancel_auth_refresh()
                self.cancel_auth_refresh = None

        # Make sure task is cancelled on shutdown (or tests complete)
        self.config_entry.async_on_unload(
            self.hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _async_stop)
        )

        self.schedule_auth_refresh()

    def schedule_auth_refresh(self) -> None:
        if self.cancel_auth_refresh:
            self.cancel_auth_refresh()

        # Refresh auth at least every 150 hours; safe margin within 13 day limit
        self.cancel_auth_refresh = async_call_later(
            self.hass, timedelta(hours=150), self.refresh_auth
        )
        LOGGER.debug(f"schedule_auth_refresh(next={datetime.now()+timedelta(hours=150)})")

    async def refresh_auth(self, _now: datetime|None = None) -> None:
        LOGGER.info(f"Refreshing Auth ({_now})")
        await self.api_client.refresh_auth()

        data = {
            **self.config_entry.data,
            CONF_AUTH_STATE: self.api_client.auth.serialize(),
        }
        self.hass.config_entries.async_update_entry(self.config_entry, data=data)
        self.schedule_auth_refresh()

    async def get_now_playing(self, now: datetime | None = None) -> None:
        await self.api_client.get_now_playing()

    async def command(self, func_name: str, **kwargs) -> Any:
        f = getattr(self.api_client, func_name, None)
        if not f:
            raise NoSuchMethod

        if not self.linked:
            LOGGER.info(f"Client not linked when calling {func_name}, trying to refresh auth...")
            await self.refresh_auth(utcnow())

        if not self.connected:
            LOGGER.info(f"Client not connected when calling {func_name}, trying to connect...")
            await self.api_client.connect()

        if not self.subscribed:
            LOGGER.info(f"Subscribtion inactive when calling {func_name}, trying to subscribe...")
            await self.subscribe(True)

        LOGGER.debug(f"Command: {func_name}({kwargs})")
        return await f(**kwargs)

    async def set_auto_disconnect(self, enable: bool):
        self.auto_disconnect = enable
        await self.async_request_refresh()

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

    @property
    def autoplay(self) -> bool:
        return self.live_data['autoplay']

    async def subscribe(self, enable: bool):
        if enable != self.subscribed:
            LOGGER.info(f"Subscribe({enable})")
            if enable:
                async def subscribe_keepalive():
                    while True:
                        t0 = time()
                        if not self.linked:
                            LOGGER.info(f"Client not linked in subscribe task, trying to refresh auth...")
                            await self.refresh_auth(utcnow())
                        if not self.connected:
                            LOGGER.info("Client not connected in subscribe task, trying to connect...")
                            await self.api_client.connect()
                        await self.api_client.subscribe()
                        t1 = time()
                        LOGGER.info(f"Subscribe Keepalive; refresh after {t1 - t0}")

                self.subscribe_task = asyncio.create_task(subscribe_keepalive(), name="YtLounge-Subscribe")
                async_call_later(self.hass, timedelta(seconds=5), self.get_now_playing)
            else:
                if self.subscribe_task is not None:
                    await self.api_client.disconnect()
                    self.subscribe_task.cancel()
                    self.subscribe_task = None

        await self.async_request_refresh()

    async def handle_connected_device_changed(self, devices):
        if self.auto_disconnect and len(devices) == 0 and len(self.connected_devices) > 0:
            try:
                LOGGER.info("Auto disconnect!")
                await self.subscribe(False)
                await self.api_client.disconnect()
            except Exception:
                pass

    async def get_video_data(self, video_id: str) -> dict:
        request = self.yt_api.videos().list(part='snippet', id=video_id)
        res = await self.hass.async_add_executor_job(request.execute)
        return res['items'][0]['snippet']

    async def get_video_subtitles(self, video_id: str) -> list:
        request = self.yt_api.captions().list(part='snippet', videoId=video_id)
        res = await self.hass.async_add_executor_job(request.execute)
        return list(set([sub['snippet']['language'] for sub in res['items']]))

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

    async def autoplay_up_next_changed(self, event: AutoplayUpNextEvent) -> None:
        """Called when up next video changes"""
        LOGGER.debug(
            f"Autoplay up next changed: {event.__dict__}"
        )

    async def ad_state_changed(self, event: AdStateEvent) -> None:
        """Called when ad state changes (position, play/pause, skippable)"""
        LOGGER.debug(
            f"Ad state changed: {event.__dict__}"
        )

    async def ad_playing_changed(self, event: AdPlayingEvent) -> None:
        """Called when ad starts playing"""
        LOGGER.debug(
            f"Ad playing changed: {event.__dict__}"
        )

    async def playback_speed_changed(self, event: PlaybackSpeedEvent) -> None:
        """Called when playback speed changes"""
        self.live_data['connected'] = True
        self.live_data['playback_speed'] = event.playback_speed
        LOGGER.debug(f"Playback speed changed: {event.playback_speed}")
        await self.async_request_refresh()

    async def subtitles_track_changed(self, event: SubtitlesTrackEvent) -> None:
        """Called when subtitles track changes"""
        self.live_data['subtitle_track'] = event.language_code or "disabled"
        LOGGER.debug(f"Subtitles track changed: {event.__dict__}")
        await self.async_request_refresh()

    async def disconnected(self, event: DisconnectedEvent) -> None:
        """Called when the screen is no longer connected"""
        self.live_data['connected'] = False
        self.live_data['video_id'] = None
        self.live_data['video_title'] = None
        self.live_data['channel'] = None
        self.live_data['subtitle_track'] = None
        self.live_data['subtitle_options'] = []
        LOGGER.info(f"Disconnected with Reason: {event.reason}")
        if self.subscribed:
            self.subscribe(False)
        await self.async_request_refresh()

    async def lounge_status_changed_raw(self, event: Any) -> None:
        """Called when launge status changes"""
        devices = json.loads(event["devices"])
        # Remove TV and Self instance:
        devices = [d for d in devices if d["type"] == "REMOTE_CONTROL" and d["name"] != "HomeAssistant"]
        LOGGER.debug(f"Lounge status changed event: {json.dumps(devices, sort_keys=True, indent=4, default=lambda o: '<< Not JSON Serializable... >>')}")
        await self.handle_connected_device_changed(devices)
        self.connected_devices = devices


    async def unknown_event_raw(self, event_type: str, event: Any) -> None:
        """Called when an unprocess event is received"""
        LOGGER.debug(f"Unknown event({event_type}): {json.dumps(event, sort_keys=True, indent=4, default=lambda o: '<< Not JSON Serializable... >>')}")
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    #   YTLounge Event listener hooks
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    async def _async_update_data(self) -> YtLoungeData:
        """Get the latest data from YTLounge API."""

        if (api_key := self.config_entry.data.get(CONF_API_KEY)) and (vid := self.live_data['video_id']):
            if vid != self.last_video_id or self.data.video_title is None:
                self.last_video_id = vid
                video_data = await self.get_video_data(vid)
                self.live_data['video_title'] = video_data['title']
                self.live_data['channel'] = video_data['channelTitle']
                self.live_data['subtitle_options'] = await self.get_video_subtitles(vid)
                LOGGER.info(f"GetVideoData: Title: {self.live_data['video_title']}, Channel:{self.live_data['channel']}")
                LOGGER.debug(f"Subtitles: {self.live_data['subtitle_options']}")
        else:
            self.live_data['video_title'] = None
            self.live_data['channel'] = None

        mediaplayer_state = MediaPlayerState.OFF
        if self.connected and self.subscribed:
            mediaplayer_state = PlaybackState2MediaPlayerState(self.live_data['state'])

        thumbnail_url = None
        if self.live_data['video_id']:
            thumbnail_url = get_thumbnail_url(self.live_data['video_id'], "maxresdefault")

        return YtLoungeData(
            self.live_data['connected'],
            self.live_data['state'],
            mediaplayer_state,
            self.live_data['video_id'],
            self.live_data['video_title'],
            thumbnail_url,
            self.live_data['channel'],
            self.live_data['subtitle_track'],
            self.live_data['subtitle_options'],
            self.live_data['duration'],
            self.live_data['current_time'],
            self.live_data['current_time_updated'],
            self.live_data['volume'],
            self.live_data['muted']
        )

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate the server is unreachable."""

class NoSuchMethod(exceptions.HomeAssistantError):
    """Requested method does not exist."""
