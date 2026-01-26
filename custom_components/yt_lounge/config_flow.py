"""Config flow for the Jellyfin integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from googleapiclient.discovery import build
from pyytlounge import YtLoungeApi

from homeassistant import exceptions
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.util.uuid import random_uuid_hex

from .const import CONF_API_KEY, CONF_AUTH_STATE, CONF_DEVICE_NAME, CONF_SCREEN_NAME, CONF_SCREEN_ID, CONF_TV_CODE, DOMAIN
from .coordinator import YTLoungeConfigEntry

LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TV_CODE): str,
        vol.Optional(CONF_API_KEY): str,
    }
)

def _generate_client_device_id() -> str:
    """Generate a random UUID4 string to identify ourselves."""
    return random_uuid_hex()

def _test_api_key(key: str) -> bool:
    youtube = build('youtube', 'v3', developerKey=key)
    request = youtube.videos().list(part='snippet', id="jNQXAC9IVRw")
    details = request.execute()

    LOGGER.debug(f"YT API Response: {details}")
    return True


class YTLoungeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Jellyfin."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the Jellyfin config flow."""

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a user defined configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            LOGGER.debug(f"User Input: {user_input}")

            try:
                if CONF_API_KEY in user_input:
                    api_key_valid = await self.hass.async_add_executor_job(_test_api_key, user_input[CONF_API_KEY])
                    if not api_key_valid:
                        raise InvalidApiKey

                async with YtLoungeApi("HA ConfigFlow", None, logging.getLogger(f"{__package__}.pyytlounge")) as client:
                    pairing_code = user_input[CONF_TV_CODE]
                    LOGGER.debug(f"Pairing with code {pairing_code}...")
                    paired = await client.pair(pairing_code)
                    LOGGER.debug(paired and "success" or "failed")
                    if not paired:
                        raise CannotConnect

                    is_available = await client.is_available()
                    LOGGER.debug(f"Screen availability: {is_available}")

                    LOGGER.debug("Connecting...")
                    connected = await client.connect()
                    LOGGER.debug(connected and "success" or "failed")
                    if not connected:
                        raise CannotConnect

                    auth_state = client.auth.serialize()
                    screen_id = client.screen_id
                    screen_name = client.screen_name
                    device_name = client.screen_device_name
                    LOGGER.debug(f"AuthState: {auth_state}")
                    LOGGER.debug(f"ScreenName: {screen_id}")
                    LOGGER.debug(f"ScreenName: {screen_name}")
                    LOGGER.debug(f"DeviceName: {device_name}")


            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except InvalidApiKey:
                errors["base"] = "invalid_api_key"
            except Exception:
                errors["base"] = "unknown"
                LOGGER.exception("Unexpected exception")
            else:

                await self.async_set_unique_id(auth_state['screenId'])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=screen_name,
                    data={
                        CONF_AUTH_STATE: auth_state,
                        CONF_API_KEY: user_input[CONF_API_KEY],
                        CONF_DEVICE_NAME: device_name,
                        CONF_SCREEN_NAME: screen_name,
                        CONF_SCREEN_ID: screen_id,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Dialog that informs the user that reauth is required."""
        errors: dict[str, str] = {}

        if user_input is not None:
            reauth_entry = self._get_reauth_entry()
            new_input = reauth_entry.data | user_input

            if self.client_device_id is None:
                self.client_device_id = _generate_client_device_id()

            client = create_client(device_id=self.client_device_id)
            try:
                await validate_input(self.hass, new_input, client)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                errors["base"] = "unknown"
                LOGGER.exception("Unexpected exception")
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=new_input)

        return self.async_show_form(
            step_id="reauth_confirm", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate the server is unreachable."""
class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate the TV-code is incorrect."""
class InvalidApiKey(exceptions.HomeAssistantError):
    """Error to indicate API key is invalid."""
