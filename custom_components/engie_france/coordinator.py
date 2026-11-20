"""Daily coordinator: price cache + persisted login session."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EngieAuthError, EngieClient, EngieConnectionError
from .const import CACHE_MAX_AGE, CONF_STORAGE_KEY, DOMAIN, STORAGE_VERSION, UPDATE_INTERVAL
from .parser import EngiePrices, ParseError, parse_history

_LOGGER = logging.getLogger(__name__)


def make_store(hass: HomeAssistant, storage_key: str) -> Store:
    return Store(hass, STORAGE_VERSION, f"{DOMAIN}.{storage_key}")


class EngieCoordinator(DataUpdateCoordinator[EngiePrices]):
    """Fetch the price history once a day."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EngieClient) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=UPDATE_INTERVAL
        )
        self._client = client
        self._store = make_store(hass, entry.data[CONF_STORAGE_KEY])
        self._cache: dict[str, Any] = {}

    async def async_load_session(self) -> None:
        self._cache = await self._store.async_load() or {}
        self._client.import_cookies(self._cache.get("cookies", []))

    def _from_cache(self, today) -> EngiePrices | None:
        try:
            return parse_history(self._cache["history"], today)
        except (KeyError, ParseError):
            return None

    async def _async_update_data(self) -> EngiePrices:
        today = dt_util.now().date()
        fetched = dt_util.parse_datetime(self._cache.get("fetched_at", ""))
        if fetched and dt_util.utcnow() - fetched < CACHE_MAX_AGE:
            if (prices := self._from_cache(today)) is not None:
                return prices

        try:
            history = await self._client.async_fetch_history()
            prices = parse_history(history, today)
        except EngieAuthError as err:
            # Wrong password, or a one-time code is needed: ask the user (reauth).
            raise ConfigEntryAuthFailed(str(err)) from err
        except EngieConnectionError as err:
            if (prices := self._from_cache(today)) is not None:
                return prices
            raise UpdateFailed(f"Engie injoignable: {err}") from err
        except ParseError as err:
            raise UpdateFailed(f"Réponse Engie inattendue: {err}") from err

        self._cache = {
            "fetched_at": datetime.now(dt_util.UTC).isoformat(),
            "history": history,
            "cookies": self._client.export_cookies(),
        }
        await self._store.async_save(self._cache)
        return prices
