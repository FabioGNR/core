"""The YouTube Lounge integration."""
from __future__ import annotations

from pyytlounge import YtLoungeApi

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .util import device_name

PLATFORMS: list[Platform] = [Platform.MEDIA_PLAYER]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up YouTube Lounge from a config entry."""

    hass.data.setdefault(DOMAIN, {})

    api = YtLoungeApi(device_name(hass))
    api.auth.deserialize(entry.data["auth"])

    if await api.connect():
        hass.data[DOMAIN][entry.entry_id] = api
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
