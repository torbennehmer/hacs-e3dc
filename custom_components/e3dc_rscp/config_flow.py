"""Config flow for E3DC Remote Storage Control Protocol integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import (
    CONF_API_VERSION,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError, ConfigEntryAuthFailed
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.core import callback

from .const import (
    CONF_CREATE_BATTERY_DEVICES,
    DEFAULT_CREATE_BATTERY_DEVICES,
    CONF_RSCPKEY,
    CONF_VERSION,
    DOMAIN,
    ERROR_AUTH_INVALID,
    ERROR_CANNOT_CONNECT,
)
from .e3dc_proxy import E3DCProxy

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_RSCPKEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


class E3DCConfigFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E3DC Remote Storage Control Protocol."""

    def __init__(self) -> None:
        """Initialize config flow."""
        self._entry: config_entries.ConfigEntry | None = None
        self._host: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._rscpkey: str | None = None
        self._proxy: E3DCProxy = None

    def _async_check_login(self) -> None:
        assert isinstance(self._username, str)
        assert isinstance(self._password, str)
        assert isinstance(self._host, str)
        assert isinstance(self._rscpkey, str)

        self._proxy = E3DCProxy(self.hass, {
            CONF_HOST: self._host,
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_RSCPKEY: self._rscpkey
        })
        self._proxy.connect()

    async def validate_input(self) -> str | None:
        """Validate the user input allows us to connect."""
        try:
            await self.hass.async_add_executor_job(self._async_check_login)
        except ConfigEntryAuthFailed:
            return ERROR_AUTH_INVALID
        except HomeAssistantError:
            return ERROR_CANNOT_CONNECT
        return None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}

        if user_input is None:
            return self._show_setup_form_init(errors)

        self._host = user_input[CONF_HOST]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._rscpkey = user_input[CONF_RSCPKEY]

        if error := await self.validate_input():
            return self._show_setup_form_init({"base": error})

        await self.async_set_unique_id(
            f"{self._proxy.e3dc.serialNumberPrefix}{self._proxy.e3dc.serialNumber}"
        )
        self._abort_if_unique_id_configured()
        final_data: dict[str, Any] = user_input
        final_data[CONF_API_VERSION] = CONF_VERSION

        return self.async_create_entry(
            title=f"E3DC {self._proxy.e3dc.model}", data=final_data
        )

    def _show_setup_form_init(self, errors: dict[str, str] | None = None) -> FlowResult:
        """Show the setup form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors or {},
        )

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> FlowResult:
        """Handle flow upon API authentication errors."""
        self._entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        self._host = entry_data[CONF_HOST]
        self._username = entry_data[CONF_USERNAME]
        self._password = entry_data[CONF_PASSWORD]
        self._rscpkey = entry_data[CONF_RSCPKEY]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Inform the user that a reauth is required."""

        if user_input is None:
            return self._show_setup_form_reauth_confirm()

        self._host = user_input[CONF_HOST]
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._rscpkey = user_input[CONF_RSCPKEY]

        if error := await self.validate_input():
            return self._show_setup_form_reauth_confirm({"base": error})

        assert isinstance(self._entry, config_entries.ConfigEntry)
        final_data: dict[str, Any] = user_input
        final_data[CONF_API_VERSION] = CONF_VERSION
        self.hass.config_entries.async_update_entry(
            self._entry,
            data=final_data,
        )
        await self.hass.config_entries.async_reload(self._entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    def _show_setup_form_reauth_confirm(
        self, errors: dict[str, str] | None = None
    ) -> FlowResult:
        """Show the setup form to the user."""
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors or {},
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Return the options flow handler for this integration."""
        return E3DCOptionsFlowHandler()


class E3DCOptionsFlowHandler(config_entries.OptionsFlowWithReload):
    """Handle options for E3DC Remote Storage Control Protocol."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_CREATE_BATTERY_DEVICES,
                        default=self.config_entry.options.get(
                            CONF_CREATE_BATTERY_DEVICES,
                            DEFAULT_CREATE_BATTERY_DEVICES,
                        ),
                    ): cv.boolean,
                }
            ),
        )
