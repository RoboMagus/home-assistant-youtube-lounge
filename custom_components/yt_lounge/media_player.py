"""Support for the YouTube Lounge media player."""

from __future__ import annotations

import logging
from datetime import datetime
from time import time
from typing import Any

from homeassistant import exceptions
from homeassistant.components.media_player import (
    ATTR_MEDIA_ENQUEUE,
    MediaPlayerEnqueue,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
)
from homeassistant.core import HomeAssistant, callback, ServiceResponse, SupportsResponse
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.entity_platform import (
    AddConfigEntryEntitiesCallback,
    async_get_current_platform,
)

from .const import DOMAIN, SERVICE_CONNECT, SERVICE_GET_NOW_PLAYING, SERVICE_SUBSCRIBE
from .coordinator import YTLoungeConfigEntry, YTLoungeDataUpdateCoordinator
from .entity import YTLoungeEntity

LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: YTLoungeConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up YTLounge media_player from a config entry."""
    coordinator = entry.runtime_data
    async_add_entities([YTLoungeMediaPlayer(coordinator)])

    platform = async_get_current_platform()
    platform.async_register_entity_service(
        name=SERVICE_CONNECT,
        schema=None,
        func="async_connect",
        supports_response=SupportsResponse.OPTIONAL
    )
    platform.async_register_entity_service(
        name=SERVICE_GET_NOW_PLAYING,
        schema=None,
        func="async_get_now_playing",
        supports_response=SupportsResponse.ONLY
    )
    platform.async_register_entity_service(
        name=SERVICE_SUBSCRIBE,
        schema=None,
        func="async_subscribe",
        supports_response=SupportsResponse.OPTIONAL
    )

class YTLoungeMediaPlayer(YTLoungeEntity, MediaPlayerEntity):
    """Represents a YTLounge Player device."""

    def __init__(
        self,
        coordinator: YTLoungeDataUpdateCoordinator,
    ) -> None:
        """Initialize the YTLounge Media Player entity."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.screen_id}_mediaplayer"
        self._attr_name = self.device_name
        self._attr_media_content_type = MediaType.VIDEO

    @callback
    def _handle_coordinator_update(self) -> None:
        super()._handle_coordinator_update()

    async def async_connect(self) -> ServiceResponse:
        """Connect Service-Call."""
        LOGGER.info("async_connect()")
        paired = self.coordinator.paired
        linked = self.coordinator.linked
        connected = self.coordinator.connected
        LOGGER.info(f"Paired({paired}), Linked({linked}), Connected({connected})")

        connected = await self.coordinator.api_client.connect()
        LOGGER.info(f"Connection succes: {connected}")

        return {
            "connected": connected,
        }

    async def async_get_now_playing(self) -> ServiceResponse:
        """Get now playing Service-Call."""
        r = await self.coordinator.command('get_now_playing')
        return {
            "now_playing": r,
        }

    async def async_subscribe(self) -> ServiceResponse:
        """Subscribe Service-Call."""
        t0 = time()
        await self.coordinator.api_client.subscribe()
        t1 = time()
        return {
            "time_elapsed": t1-t0,
        }

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #   State Properties
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    @property
    def state(self) -> MediaPlayerState | None:
        """State of the player."""
        return self.coordinator.data.mediaplayer_state

    @property
    def volume_level(self) -> float | None:
        """Volume level of the media player (0..1)."""
        return self.coordinator.data.volume / 100.0

    @property
    def is_volume_muted(self) -> bool | None:
        """Boolean if volume is currently muted."""
        return self.coordinator.data.muted

    @property
    def media_content_id(self) -> str | None:
        """Content ID of current playing media."""
        return self.coordinator.data.video_id

    @property
    def media_duration(self) -> int | None:
        """Duration of current playing media in seconds."""
        return self.coordinator.data.duration

    @property
    def media_position(self) -> int | None:
        """Position of current playing media in seconds."""
        return self.coordinator.data.current_time

    @property
    def media_position_updated_at(self) -> datetime | None:
        """When was the position of the current playing media valid.
        Returns value from homeassistant.util.dt.utcnow().
        """
        return self.coordinator.data.current_time_updated

    @property
    def media_image_url(self) -> str | None:
        """Image url of current playing media."""
        return self.coordinator.data.thumbnail_url

    @property
    def media_title(self) -> str | None:
        """Title of current playing media."""
        return self.coordinator.data.video_title

    @property
    def media_channel(self) -> str | None:
        """Channel currently playing."""
        return self.coordinator.data.channel

    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    #   State Properties
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        features =  (
            MediaPlayerEntityFeature.PLAY_MEDIA
            | MediaPlayerEntityFeature.PAUSE
            | MediaPlayerEntityFeature.PLAY
            | MediaPlayerEntityFeature.PREVIOUS_TRACK
            | MediaPlayerEntityFeature.NEXT_TRACK
            | MediaPlayerEntityFeature.VOLUME_SET
            | MediaPlayerEntityFeature.SEEK
            | MediaPlayerEntityFeature.MEDIA_ENQUEUE
        )
        return features

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    #   Actions
    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    async def async_media_pause(self) -> None:
        """Send pause command."""
        await self.coordinator.command('pause')

    async def async_media_play(self) -> None:
        """Send play command."""
        await self.coordinator.command('play')

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: Any
    ) -> None:
        """Play a piece of media."""

        enqueue: MediaPlayerEnqueue = kwargs.get(
            ATTR_MEDIA_ENQUEUE, MediaPlayerEnqueue.PLAY
        )

        # False => unsuccesfull...
        if enqueue == MediaPlayerEnqueue.ADD:
            # add given media item to end of the queue
            res = await self.coordinator.command('_command', command='addVideo', command_parameters={"videoId": media_id})
            LOGGER.debug(f"Add to queue: {media_id}   >   {res}")
        elif enqueue == MediaPlayerEnqueue.NEXT:
            # play the given media item next, keep queue
            res = await self.coordinator.command('_command', command='insertVideo', command_parameters={"videoId": media_id})
            LOGGER.debug(f"Add next: {media_id}   >   {res}")
        elif enqueue == MediaPlayerEnqueue.PLAY:
            # play the given media item now, keep queue
            res = await self.coordinator.command('_command', command='setVideo', command_parameters={"videoId": media_id})
            LOGGER.debug(f"Play now (keep queue): {media_id}   >   {res}")
        else: # REPLACE
            # play the given media item now, clear queue
            res = await self.coordinator.command('play_video', video_id=media_id)
            LOGGER.debug(f"Play now (clear queue): {media_id}   >   {res}")

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        await self.coordinator.command('previous')

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        await self.coordinator.command('next')

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        await self.coordinator.command('seek_to', time=position)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        await self.coordinator.command('set_volume', volume=int(volume * 100))

    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
    #   Actions
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
