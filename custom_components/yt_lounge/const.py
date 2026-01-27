"""Consts for YouTube Lounge integration."""

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "yt_lounge"

CONF_API_KEY: Final = "api_key"
CONF_AUTH_STATE: Final = "auth_state"
CONF_DEVICE_NAME: Final = "device_name"
CONF_SCREEN_ID: Final = "screen_id"
CONF_SCREEN_NAME: Final = "screen_name"
CONF_TV_CODE: Final = "tv_code"

SERVICE_CONNECT = "connect"
SERVICE_GET_NOW_PLAYING = "get_now_playing"
SERVICE_SUBSCRIBE = "subscribe"

PLATFORMS = [Platform.BINARY_SENSOR, Platform.MEDIA_PLAYER, Platform.SENSOR, Platform.SWITCH]
