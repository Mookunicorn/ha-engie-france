"""Config flow: e-mail + password, then the SMS/e-mail code if Engie asks for it."""
from __future__ import annotations

from typing import Any
from uuid import uuid4

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import (
    EngieAuthError,
    EngieClient,
    EngieConnectionError,
    EngieInvalidCode,
    LoginState,
)
from .const import (
    CONF_CODE,
    CONF_EMAIL,
    CONF_FACTOR,
    CONF_PART_HP,
    CONF_PASSWORD,
    CONF_STORAGE_KEY,
    DEFAULT_PART_HP,
    DOMAIN,
)
from .coordinator import make_store

CONNECT_ERRORS: tuple[tuple[type[Exception], str], ...] = (
    (EngieConnectionError, "cannot_connect"),
    (EngieAuthError, "invalid_auth"),
)


def _error_key(err: Exception) -> str:
    for cls, key in CONNECT_ERRORS:
        if isinstance(err, cls):
            return key
    return "unknown"


class EngieConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._client: EngieClient | None = None
        self._email = ""
        self._password = ""
        self._reauth = False

    # ----- credentials
    async def _credentials(
        self, step_id: str, user_input: dict[str, Any] | None, defaults: dict[str, str]
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            self._email = user_input[CONF_EMAIL].strip()
            self._password = user_input[CONF_PASSWORD]
            session = async_create_clientsession(self.hass, cookie_jar=aiohttp.CookieJar())
            self._client = EngieClient(session, self._email, self._password)
            try:
                state = await self._client.async_login()
            except (EngieAuthError, EngieConnectionError) as err:
                errors["base"] = _error_key(err)
            else:
                if state is LoginState.SUCCESS:
                    return await self._finish()
                types = self._client.factor_types
                if len(types) == 1:
                    return await self._send_code(types[0])
                return await self.async_step_factor()
        return self.async_show_form(
            step_id=step_id,
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.EMAIL)
                    ),
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return await self._credentials("user", user_input, {})

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._reauth = True
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        defaults = {CONF_EMAIL: self._get_reauth_entry().data.get(CONF_EMAIL, "")}
        return await self._credentials("reauth_confirm", user_input, defaults)

    # ----- one-time code
    async def async_step_factor(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        types = self._client.factor_types
        if user_input is not None:
            return await self._send_code(user_input[CONF_FACTOR])
        return self.async_show_form(
            step_id="factor",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_FACTOR, default=types[0]): SelectSelector(
                        SelectSelectorConfig(
                            options=types,
                            translation_key="factor",
                            mode=SelectSelectorMode.LIST,
                        )
                    )
                }
            ),
        )

    async def _send_code(self, factor: str) -> ConfigFlowResult:
        try:
            await self._client.async_send_code(factor)
        except (EngieAuthError, EngieConnectionError) as err:
            return self.async_abort(reason=_error_key(err))
        return await self.async_step_code()

    async def async_step_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                await self._client.async_verify_code(user_input[CONF_CODE].strip())
            except EngieInvalidCode:
                errors["base"] = "invalid_code"
            except (EngieAuthError, EngieConnectionError) as err:
                errors["base"] = _error_key(err)
            else:
                return await self._finish()
        return self.async_show_form(
            step_id="code",
            data_schema=vol.Schema({vol.Required(CONF_CODE): str}),
            errors=errors,
        )

    # ----- done
    async def _finish(self) -> ConfigFlowResult:
        if self._reauth:
            entry = self._get_reauth_entry()
            storage_key = entry.data[CONF_STORAGE_KEY] if CONF_STORAGE_KEY in entry.data else uuid4().hex
        else:
            storage_key = uuid4().hex
        # Keep the logged-in session (and the "remembered device" cookie) for the first refresh.
        await make_store(self.hass, storage_key).async_save(
            {"cookies": self._client.export_cookies()}
        )
        data = {CONF_EMAIL: self._email, CONF_PASSWORD: self._password, CONF_STORAGE_KEY: storage_key}
        if self._reauth:
            return self.async_update_reload_and_abort(self._get_reauth_entry(), data_updates=data)
        await self.async_set_unique_id(self._email.lower())
        self._abort_if_unique_id_configured()
        return self.async_create_entry(
            title="Engie France", data=data, options={CONF_PART_HP: DEFAULT_PART_HP}
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        return EngieOptionsFlow()


class EngieOptionsFlow(OptionsFlow):
    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        current = self.config_entry.options.get(CONF_PART_HP, DEFAULT_PART_HP)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PART_HP, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=0, max=100, step=1, unit_of_measurement="%",
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
