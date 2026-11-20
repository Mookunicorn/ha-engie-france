"""Client for the Engie France customer area (Okta login + OAuth + price API)."""
from __future__ import annotations

import secrets
import string
from enum import Enum
from typing import Any

import aiohttp
from yarl import URL

from .const import (
    BASE_URL,
    CALLBACK_URL,
    DGP_URL,
    HISTORY_PATH,
    OAUTH_CLIENT_ID,
    OAUTH_SCOPE,
    OKTA_URL,
    REFERER,
    STATE_SUFFIX,
)

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
TIMEOUT = aiohttp.ClientTimeout(total=30)


class EngieAuthError(Exception):
    """Credentials or session refused."""


class EngieMfaRequired(EngieAuthError):
    """A one-time code is needed to log in."""


class EngieInvalidCode(EngieAuthError):
    """The one-time code was wrong or expired."""


class EngieConnectionError(Exception):
    """Network or server problem."""


class LoginState(Enum):
    SUCCESS = "success"
    MFA_REQUIRED = "mfa_required"


def _hosts() -> list[str]:
    return [URL(u).host for u in (BASE_URL, OKTA_URL, DGP_URL)]


class EngieClient:
    """Log in (with optional SMS/e-mail code) and fetch the price history."""

    def __init__(self, session: aiohttp.ClientSession, email: str, password: str) -> None:
        self._session = session
        self._email = email
        self._password = password
        self._state_token: str | None = None
        self._factors: list[dict[str, Any]] = []
        self._verify_href: str | None = None

    # ---------- cookies (so that the session and the "remembered device" survive restarts)
    def export_cookies(self) -> list[dict[str, str]]:
        jar, out, seen = self._session.cookie_jar, [], set()
        for host in _hosts():
            for name, morsel in jar.filter_cookies(URL(f"https://{host}/")).items():
                if (host, name) not in seen:
                    seen.add((host, name))
                    out.append({"host": host, "name": name, "value": morsel.value})
        return out

    def import_cookies(self, items: list[dict[str, str]]) -> None:
        for it in items or []:
            self._session.cookie_jar.update_cookies(
                {it["name"]: it["value"]}, URL(f"https://{it['host']}/")
            )

    # ---------- login
    @property
    def factor_types(self) -> list[str]:
        types = [f.get("factorType") for f in self._factors if f.get("factorType")]
        return sorted(types, key=lambda t: (t != "sms", t))

    async def async_login(self) -> LoginState:
        data = await self._okta_post(
            f"{OKTA_URL}/api/v1/authn",
            {
                "username": self._email,
                "password": self._password,
                "options": {"multiOptionalFactorEnroll": True},
            },
        )
        status = data.get("status")
        if status == "SUCCESS":
            await self._finish_login(data["sessionToken"])
            return LoginState.SUCCESS
        if status == "MFA_REQUIRED":
            self._state_token = data["stateToken"]
            self._factors = data.get("_embedded", {}).get("factors", [])
            if not self.factor_types:
                raise EngieAuthError("MFA required but no usable factor")
            return LoginState.MFA_REQUIRED
        raise EngieAuthError(f"unexpected login status: {status}")

    async def async_send_code(self, factor_type: str) -> None:
        factor = next((f for f in self._factors if f.get("factorType") == factor_type), None)
        if factor is None or self._state_token is None:
            raise EngieAuthError("unknown factor")
        href = factor["_links"]["verify"]["href"]
        data = await self._okta_post(href, {"stateToken": self._state_token})
        if data.get("status") != "MFA_CHALLENGE":
            raise EngieAuthError(f"unexpected challenge status: {data.get('status')}")
        self._verify_href = href
        self._state_token = data.get("stateToken", self._state_token)

    async def async_verify_code(self, code: str) -> None:
        if not self._verify_href or not self._state_token:
            raise EngieAuthError("no pending challenge")
        data = await self._okta_post(
            self._verify_href + "?rememberDevice=true",
            {"passCode": code, "stateToken": self._state_token},
            bad_code_statuses=(401, 403),
        )
        if data.get("status") != "SUCCESS":
            raise EngieInvalidCode(f"status {data.get('status')}")
        await self._finish_login(data["sessionToken"])

    async def _okta_post(
        self, url: str, payload: dict[str, Any], bad_code_statuses: tuple[int, ...] = ()
    ) -> dict[str, Any]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "Origin": BASE_URL,
            "X-Okta-User-Agent-Extended": "okta-auth-js/4.9.2",
            "User-Agent": USER_AGENT,
        }
        try:
            async with self._session.post(
                url, json=payload, headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status in bad_code_statuses:
                    raise EngieInvalidCode(f"HTTP {resp.status}")
                if resp.status in (401, 403):
                    raise EngieAuthError(f"HTTP {resp.status}")
                if resp.status == 429 or resp.status >= 500:
                    raise EngieConnectionError(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise EngieAuthError(f"HTTP {resp.status}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EngieConnectionError(str(err)) from err

    async def _finish_login(self, session_token: str) -> None:
        """Exchange the Okta session token for a site session (OAuth redirects)."""
        state = "".join(secrets.choice(string.ascii_lowercase) for _ in range(10)) + STATE_SUFFIX
        params = {
            "client_id": OAUTH_CLIENT_ID,
            "redirect_uri": CALLBACK_URL,
            "response_type": "code",
            "sessionToken": session_token,
            "state": state,
            "scope": OAUTH_SCOPE,
        }
        try:
            async with self._session.get(
                f"{DGP_URL}/oauth/v1/authorize",
                params=params,
                headers={"Accept": "*/*", "User-Agent": USER_AGENT},
                timeout=TIMEOUT,
                allow_redirects=True,
            ) as resp:
                body = await resp.json(content_type=None) if resp.status == 200 else {}
                if resp.status != 200 or body.get("statut") != "OK":
                    raise EngieAuthError(f"OAuth callback failed (HTTP {resp.status})")
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EngieConnectionError(str(err)) from err
        finally:
            self._state_token = None

    # ---------- data
    async def async_fetch_history(self) -> dict[str, Any]:
        """Fetch prices; log in again once if the session is missing or expired."""
        try:
            return await self._get_history()
        except EngieAuthError:
            if await self.async_login() is LoginState.MFA_REQUIRED:
                raise EngieMfaRequired("code required") from None
            return await self._get_history()

    async def _get_history(self) -> dict[str, Any]:
        headers = {
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "fr-FR,fr;q=0.9",
            "Referer": REFERER,
            "User-Agent": USER_AGENT,
        }
        try:
            # The site does this on every page load, before its API calls.
            async with self._session.post(
                f"{BASE_URL}/digital-common-ws/api-management/creation-cookie",
                headers={**headers, "demandeur": "PARTICULIERS_WEB", "Origin": BASE_URL},
                timeout=TIMEOUT,
            ):
                pass
            async with self._session.get(
                BASE_URL + HISTORY_PATH, headers=headers, timeout=TIMEOUT, allow_redirects=False
            ) as resp:
                if resp.status in (301, 302, 303, 307, 308, 401, 403):
                    raise EngieAuthError(f"HTTP {resp.status}")
                if resp.status != 200:
                    raise EngieConnectionError(f"HTTP {resp.status}")
                if "json" not in resp.headers.get("Content-Type", ""):
                    raise EngieAuthError("non-JSON answer")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise EngieConnectionError(str(err)) from err
