"""Config flow: paste the browser session cookie, validate it with one request."""
from __future__ import annotations

from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .api import EngieAuthError, EngieClient, EngieConnectionError
from .const import CONF_COOKIE, CONF_PART_HP, DEFAULT_PART_HP, DOMAIN
from .parser import ParseError, parse_history

COOKIE_SELECTOR = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))


class EngieConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def _validate(self, cookie: str) -> str | None:
        session = async_create_clientsession(self.hass, cookie_jar=aiohttp.DummyCookieJar())
        try:
            data = await EngieClient(session, cookie).async_fetch_history()
            parse_history(data, dt_util.now().date())
        except EngieAuthError:
            return "invalid_auth"
        except EngieConnectionError:
            return "cannot_connect"
        except ParseError:
            return "unexpected_response"
        return None

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._validate(user_input[CONF_COOKIE]):
                errors["base"] = error
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Engie France",
                    data={CONF_COOKIE: user_input[CONF_COOKIE].strip()},
                    options={CONF_PART_HP: DEFAULT_PART_HP},
                )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): COOKIE_SELECTOR}),
            errors=errors,
        )

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if error := await self._validate(user_input[CONF_COOKIE]):
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(
                    self._get_reauth_entry(),
                    data_updates={CONF_COOKIE: user_input[CONF_COOKIE].strip()},
                )
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_COOKIE): COOKIE_SELECTOR}),
            errors=errors,
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
