"""Engie France - Prix électricité."""
from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EngieClient
from .const import CONF_COOKIE
from .coordinator import EngieCoordinator

PLATFORMS = [Platform.SENSOR]

type EngieConfigEntry = ConfigEntry[EngieCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EngieConfigEntry) -> bool:
    # Dedicated session; the dummy jar makes sure only our Cookie header is sent.
    session = async_create_clientsession(hass, cookie_jar=aiohttp.DummyCookieJar())
    coordinator = EngieCoordinator(hass, entry, EngieClient(session, entry.data[CONF_COOKIE]))
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_reload(hass: HomeAssistant, entry: EngieConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: EngieConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
