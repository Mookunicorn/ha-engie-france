"""Daily coordinator with a small on-disk cache."""
from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import EngieAuthError, EngieClient, EngieConnectionError
from .const import CACHE_MAX_AGE, DOMAIN, STORAGE_VERSION, UPDATE_INTERVAL
from .parser import EngiePrices, ParseError, parse_history

_LOGGER = logging.getLogger(__name__)


class EngieCoordinator(DataUpdateCoordinator[EngiePrices]):
    """Fetch the price history once a day."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, client: EngieClient) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self._client = client
        self._store: Store = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    async def _async_update_data(self) -> EngiePrices:
        today = dt_util.now().date()
        cached = await self._store.async_load()
        if cached:
            fetched = dt_util.parse_datetime(cached.get("fetched_at", ""))
            if fetched and dt_util.utcnow() - fetched < CACHE_MAX_AGE:
                try:
                    return parse_history(cached["history"], today)
                except ParseError:
                    pass  # stale/invalid cache: refetch

        try:
            history = await self._client.async_fetch_history()
            prices = parse_history(history, today)
        except EngieAuthError as err:
            raise ConfigEntryAuthFailed("Session Engie expirée") from err
        except EngieConnectionError as err:
            if cached:
                try:
                    return parse_history(cached["history"], today)
                except ParseError:
                    pass
            raise UpdateFailed(f"Engie injoignable: {err}") from err
        except ParseError as err:
            raise UpdateFailed(f"Réponse Engie inattendue: {err}") from err

        await self._store.async_save(
            {"fetched_at": datetime.now(dt_util.UTC).isoformat(), "history": history}
        )
        return prices
