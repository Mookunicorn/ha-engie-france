"""Engie France - Prix électricité."""
from __future__ import annotations

import aiohttp
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession

from .api import EngieClient
from .const import CONF_EMAIL, CONF_PASSWORD, CONF_STORAGE_KEY
from .coordinator import EngieCoordinator, make_store

PLATFORMS = [Platform.SENSOR]

type EngieConfigEntry = ConfigEntry[EngieCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: EngieConfigEntry) -> bool:
    if not all(k in entry.data for k in (CONF_EMAIL, CONF_PASSWORD, CONF_STORAGE_KEY)):
        raise ConfigEntryAuthFailed("Identifiants manquants")  # entry created by v0.1
    # Dedicated session with its own cookie jar (login cookies live in it).
    session = async_create_clientsession(hass, cookie_jar=aiohttp.CookieJar())
    client = EngieClient(session, entry.data[CONF_EMAIL], entry.data[CONF_PASSWORD])
    coordinator = EngieCoordinator(hass, entry, client)
    await coordinator.async_load_session()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    options = dict(entry.options)

    async def _async_options_updated(hass: HomeAssistant, updated: EngieConfigEntry) -> None:
        if dict(updated.options) != options:  # reauth already reloads by itself
            await hass.config_entries.async_reload(updated.entry_id)

    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: EngieConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(hass: HomeAssistant, entry: EngieConfigEntry) -> None:
    if storage_key := entry.data.get(CONF_STORAGE_KEY):
        await make_store(hass, storage_key).async_remove()
