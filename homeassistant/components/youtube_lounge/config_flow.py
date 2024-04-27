"""Config flow for YouTube Lounge integration."""
from __future__ import annotations

import logging
from typing import Any

from aiogoogle import Aiogoogle
from aiogoogle.excs import HTTPError
from pyytlounge import YtLoungeApi
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .util import device_name

_LOGGER = logging.getLogger(__name__)

STEP_GOOGLE_API_DATA_SCHEMA = vol.Schema(
    {
        vol.Optional("google_api_key", description="google_api_key"): str,
    }
)

STEP_PAIR_DATA_SCHEMA = vol.Schema(
    {
        vol.Required("pairing_code", description="pairing_code"): str,
    }
)


async def validate_google_api_key(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_GOOGLE_API_DATA_SCHEMA with values provided by the user.
    """

    api_key = data["google_api_key"]
    # supplying a key is optional
    if api_key:
        async with Aiogoogle(api_key=api_key) as aiogoogle:
            yt_api = await aiogoogle.discover("youtube", "v3")
            request = yt_api.videos.list(part="snippet", id="oa__fLArsFk")
            try:
                await aiogoogle.as_api_key(request)
            except HTTPError as ex:
                if ex.res and ex.res.status_code == 400:
                    raise InvalidAuth from ex
                else:
                    raise CannotConnect from ex
            except Exception as ex:
                raise CannotConnect from ex

    return {}


async def validate_pairing_code(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input allows us to connect.

    Data has the keys from STEP_PAIR_DATA_SCHEMA with values provided by the user.
    """

    code: int
    try:
        code = int(data["pairing_code"])
    except Exception as ex:
        raise InvalidAuth from ex

    api = YtLoungeApi(device_name(hass))
    if await api.pair(code):
        data["auth"] = api.auth.serialize()
        return {"title": api.screen_name}

    raise InvalidAuth
    # todo: If you cannot connect:
    # throw CannotConnect


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for YouTube Lounge."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step to set the google api key."""
        if user_input is None:
            return self.async_show_form(
                step_id="user", data_schema=STEP_GOOGLE_API_DATA_SCHEMA
            )

        errors = {}

        try:
            await validate_google_api_key(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return await self.async_step_pair(user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_GOOGLE_API_DATA_SCHEMA, errors=errors
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the pairing step."""
        if user_input is None or "pairing_code" not in user_input:
            return self.async_show_form(
                step_id="pair", data_schema=STEP_PAIR_DATA_SCHEMA
            )

        errors = {}

        try:
            info = await validate_pairing_code(self.hass, user_input)
        except CannotConnect:
            errors["base"] = "cannot_connect"
        except InvalidAuth:
            errors["base"] = "invalid_auth"
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Unexpected exception")
            errors["base"] = "unknown"
        else:
            return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="pair", data_schema=STEP_PAIR_DATA_SCHEMA, errors=errors
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
