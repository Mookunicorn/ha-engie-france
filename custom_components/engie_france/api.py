"""HTTP client for the Engie France customer area (session-cookie based)."""
from __future__ import annotations

from typing import Any

import aiohttp

from .const import BASE_URL, HISTORY_PATH, REFERER

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)


class EngieAuthError(Exception):
    """The session is missing, expired or refused."""


class EngieConnectionError(Exception):
    """Network or server problem."""


class EngieClient:
    """Fetch the price history using the browser session cookie."""

    def __init__(self, session: aiohttp.ClientSession, cookie: str) -> None:
        self._session = session
        self._cookie = cookie.strip()

    async def async_fetch_history(self) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Referer": REFERER,
            "User-Agent": USER_AGENT,
            "Cookie": self._cookie,
        }
        try:
            async with self._session.get(
                BASE_URL + HISTORY_PATH,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
                allow_redirects=False,
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308, 401, 403):
                    raise EngieAuthError(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise EngieConnectionError(f"HTTP {resp.status}")
                if "json" not in resp.headers.get("Content-Type", ""):
                    raise EngieAuthError("non-JSON answer (login page?)")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EngieConnectionError(str(err)) from err
