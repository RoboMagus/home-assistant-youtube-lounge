"""Config flow for the YouTube Lounge integration."""

from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
import voluptuous as vol

from pyytlounge import YtLoungeApi

from homeassistant import exceptions
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback, HomeAssistant

from .const import CONF_API_KEY, CONF_AUTH_STATE, CONF_DEVICE_NAME, CONF_SCREEN_NAME, CONF_SCREEN_ID, CONF_TV_CODE, DOMAIN
from .coordinator import _async_get_video_data

LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_TV_CODE): str,
        vol.Optional(CONF_API_KEY): str,
    }
)
STEP_RECONFIG_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_TV_CODE, default="Unchanged"): str,
        vol.Optional(CONF_API_KEY): str,
    }
)

async def _test_api_key(hass: HomeAssistant, key: str) -> bool:
    details = await _async_get_video_data(hass, "jNQXAC9IVRw", key)
    LOGGER.debug(f"YT API Response: {details}")
    return True

async def _test_tv_key(pairing_code: str) -> dict[str, Any]:
    async with YtLoungeApi("HA ConfigFlow", None, logging.getLogger(f"{__package__}.pyytlounge")) as client:
        LOGGER.debug(f"Pairing with code {pairing_code}...")
        paired = await client.pair(pairing_code)
        LOGGER.debug(paired and "success" or "failed")
        if not paired:
            raise InvalidAuth

        is_available = await client.is_available()
        LOGGER.debug(f"Screen availability: {is_available}")

        LOGGER.debug("Connecting...")
        connected = await client.connect()
        LOGGER.debug(connected and "success" or "failed")
        if not connected:
            raise CannotConnect

        auth_state = client.auth.serialize()
        screen_id = client.auth.screen_id
        screen_name = client.screen_name
        device_name = client.screen_device_name or "Youtube-TV"
        LOGGER.debug(f"AuthState: {auth_state}")
        LOGGER.debug(f"ScreenName: {screen_id}")
        LOGGER.debug(f"ScreenName: {screen_name}")
        LOGGER.debug(f"DeviceName: {device_name}")

        return {
            "auth_state": auth_state,
            "screen_id": screen_id,
            "screen_name": screen_name,
            "device_name": device_name
        }

class YTLoungeConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YouTube Lounge."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize the YouTube Lounge config flow."""

    async def validate_input(self, user_input: dict[str, Any]):
        """Validate input from user input."""
        tv_pair_results: dict[str, Any] = {}
        errors: dict[str, str] = {}
        LOGGER.debug(f"User Input: {user_input}")

        try:
            if CONF_API_KEY in user_input:
                api_key_valid = await _test_api_key(self.hass, user_input[CONF_API_KEY])
                if not api_key_valid:
                    raise InvalidApiKey

            if user_input.get(CONF_TV_CODE) != "Unchanged":
                tv_pair_results = await _test_tv_key(user_input[CONF_TV_CODE])
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except InvalidApiKey:
            errors["base"] = "invalid_api_key"
        except Exception:
            errors["base"] = "unknown"
            LOGGER.exception("Unexpected exception")

        return (tv_pair_results, errors)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle a user defined configuration."""
        errors: dict[str, str] = {}

        if user_input is not None:
            tv_pair_results, errors = await self.validate_input(user_input)
            if not errors:
                await self.async_set_unique_id(tv_pair_results['auth_state']['screenId'])
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=tv_pair_results['screen_name'],
                    data={
                        CONF_API_KEY: user_input.get(CONF_API_KEY),
                        CONF_AUTH_STATE: tv_pair_results['auth_state'],
                        CONF_DEVICE_NAME: tv_pair_results['device_name'],
                        CONF_SCREEN_NAME: tv_pair_results['screen_name'],
                        CONF_SCREEN_ID: tv_pair_results['screen_id'],
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
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
        reauth_entry = self._get_reauth_entry()
        errors: dict[str, str] = {}

        if not user_input:
            return self.async_show_form(
                step_id="reauth_confirm",
                data_schema=self.add_suggested_values_to_schema(
                    STEP_RECONFIG_DATA_SCHEMA, reauth_entry.data
                ),
                errors=errors
            )

        tv_pair_results, errors = await self.validate_input(user_input)
        if not errors:
            data = {}
            if auth_state := tv_pair_results.get("auth_state"):
                data[CONF_AUTH_STATE] = auth_state
            if api_key := user_input.get(CONF_API_KEY):
                data[CONF_API_KEY] = api_key

            return self.async_update_reload_and_abort(
                self._get_reauth_entry(), data_updates=data
            )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Add reconfigure step to allow to manually reconfigure a config entry."""
        reconfigure_entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}

        if not user_input:
            return self.async_show_form(
                step_id="reconfigure",
                data_schema=self.add_suggested_values_to_schema(
                    STEP_RECONFIG_DATA_SCHEMA, reconfigure_entry.data
                ),
                errors=errors
            )

        tv_pair_results, errors = await self.validate_input(user_input)
        if not errors:
            data = {}
            if auth_state := tv_pair_results.get("auth_state"):
                data[CONF_AUTH_STATE] = auth_state
            if api_key := user_input.get(CONF_API_KEY):
                data[CONF_API_KEY] = api_key

            return self.async_update_reload_and_abort(
                self._get_reconfigure_entry(), data_updates=data
            )

class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate the server is unreachable."""
class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate the TV-code is incorrect."""
class InvalidApiKey(exceptions.HomeAssistantError):
    """Error to indicate API key is invalid."""
