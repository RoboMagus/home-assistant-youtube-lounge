"""Consts for Cast integration."""

import logging
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "yt_lounge"

CONF_API_KEY: Final = "api_key"
CONF_AUTH_STATE: Final = "auth_state"
CONF_SCREEN_ID: Final = "screen_id"
CONF_TV_CODE: Final = "tv_code"

PLATFORMS = [Platform.MEDIA_PLAYER, Platform.SENSOR]
LOGGER = logging.getLogger(__package__)
