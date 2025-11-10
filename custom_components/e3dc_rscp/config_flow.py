"""Config flow for E3DC Remote Storage Control Protocol integration."""
from __future__ import annotations

from collections.abc import Mapping
import logging
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult
)
from homeassistant.const import (
    CONF_API_VERSION,
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_PORT,
)
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError, ConfigEntryAuthFailed
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.helpers.service_info.ssdp import (
    ATTR_UPNP_FRIENDLY_NAME,
    ATTR_UPNP_SERIAL,
    SsdpServiceInfo,
)

from custom_components.e3dc_rscp.utils import initialize_farm_controller_flow_if_needed

from .const import (
    CONF_RSCPKEY,
    CONF_FARMCONTROLLER,
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


class E3DCConfigFlowHandler(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for E3DC Remote Storage Control Protocol."""

    VERSION = CONF_VERSION

    def __init__(self) -> None:
        """Initialize config flow."""
        self._entry: ConfigEntry | None = None
        self._host: str | None = None
        self._username: str | None = None
        self._password: str | None = None
        self._rscpkey: str | None = None
        self._port: int | None = None
        self._proxy: E3DCProxy = None
        self._discovered_info: dict[str, Any] | None = None

    def _async_check_login(self) -> None:
        """Check the login credentials."""
        assert isinstance(self._username, str)
        assert isinstance(self._password, str)
        assert isinstance(self._host, str)
        assert isinstance(self._rscpkey, str)

        self._proxy = E3DCProxy(self.hass, {
            CONF_HOST: self._host,
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_RSCPKEY: self._rscpkey,
            CONF_PORT: self._port,
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
        self._port = user_input.get(CONF_PORT, None)

        if error := await self.validate_input():
            return self._show_setup_form_init({"base": error})

        await self.async_set_unique_id(
            f"{self._proxy.e3dc.serialNumberPrefix}{self._proxy.e3dc.serialNumber}"
        )
        self._abort_if_unique_id_configured()
        final_data: dict[str, Any] = user_input
        final_data[CONF_FARMCONTROLLER] = len(self._proxy.e3dc.serialNumber) >= 6 and self._proxy.e3dc.serialNumber[-6] == "1"
        final_data[CONF_API_VERSION] = CONF_VERSION

        return self.async_create_entry(
            title=f"E3DC {'Farm Controller ' if final_data[CONF_FARMCONTROLLER] else ''}{self._proxy.e3dc.model}",
            data=final_data,
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

        assert isinstance(self._entry, ConfigEntry)
        final_data: dict[str, Any] = user_input
        final_data[CONF_API_VERSION] = CONF_VERSION
        self.hass.config_entries.async_update_entry(
            self._entry,
            data=final_data,
        )
        await self.hass.config_entries.async_reload(self._entry.entry_id)
        return self.async_abort(reason="reauth_successful")

    async def async_step_ssdp(
        self, discovery_info: SsdpServiceInfo
    ) -> ConfigFlowResult:
        """Handle a discovered E3DC via SSDP."""

        # Extract serial number from the SSDP headers
        serial_number = None
        if discovery_info.upnp.get(ATTR_UPNP_SERIAL):
            serial_number = discovery_info.upnp[ATTR_UPNP_SERIAL]
        elif discovery_info.ssdp_headers.get("X-SN.E3DC.COM"):
            serial_number = discovery_info.ssdp_headers["X-SN.E3DC.COM"]

        if serial_number:
            await self.async_set_unique_id(serial_number)
            self._abort_if_unique_id_configured()

        # Extract host from SSDP location
        if discovery_info.ssdp_location:
            try:
                parsed_url = urlparse(discovery_info.ssdp_location)
                self._host = parsed_url.hostname
            except Exception:
                # Fallback: simple string parsing
                self._host = discovery_info.ssdp_location.split("/")[2].split(":")[0]

        # Store discovered information for later use
        model = discovery_info.upnp.get('modelName', discovery_info.upnp.get(ATTR_UPNP_FRIENDLY_NAME, ''))
        self._discovered_info = {
            "host": self._host,
            "friendly_name": f"E3DC {model} at {self._host}",
            "serial": serial_number,
            "location": discovery_info.ssdp_location,
        }

        # Set title placeholders for the UI
        friendly_name = self._discovered_info.get("friendly_name")
        self.context["title_placeholders"] = {"name": friendly_name}

        return await self.async_step_ssdp_confirm()

    async def async_step_ssdp_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm ssdp discovery and ask for credentials."""
        if user_input is None:
            friendly_name = self._discovered_info.get("friendly_name", f"E3DC at {self._host}")
            return self.async_show_form(
                step_id="ssdp_confirm",
                data_schema=vol.Schema({
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_RSCPKEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }),
                description_placeholders={
                    "name": friendly_name,
                    "host": self._host,
                },
            )

        # User provided credentials, validate them
        self._username = user_input[CONF_USERNAME]
        self._password = user_input[CONF_PASSWORD]
        self._rscpkey = user_input[CONF_RSCPKEY]

        if error := await self.validate_input():
            return self.async_show_form(
                step_id="ssdp_confirm",
                data_schema=vol.Schema({
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Required(CONF_RSCPKEY): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    ),
                }),
                errors={"base": error},
                description_placeholders={
                    "name": self._discovered_info.get("friendly_name", f"E3DC at {self._host}"),
                    "host": self._host,
                },
            )

        # Create the entry
        final_data = {
            CONF_HOST: self._host,
            CONF_USERNAME: self._username,
            CONF_PASSWORD: self._password,
            CONF_RSCPKEY: self._rscpkey,
            CONF_PORT: self._port,
            CONF_API_VERSION: CONF_VERSION,
        }

        return await self.async_step_check_is_farm(final_data)

    async def async_step_check_is_farm(
        self, data: dict[str, Any] | None = None
    ) -> FlowResult:
        """Check if device is part of a farm and initiate farm controller configuration if so."""
        await initialize_farm_controller_flow_if_needed(
            self.hass,
            self._proxy,
            self._username,
            self._password,
            self._rscpkey
            )

        return self.async_create_entry(
            title=f"E3DC {self._proxy.e3dc.model}",
            data=data,
        )

    async def async_step_integration_discovery(self, user_input) -> FlowResult:
        """Handle the integration discovery step."""

        _LOGGER.debug("init farm controller")
        self._host = self.init_data[CONF_HOST]
        self._username = self.init_data[CONF_USERNAME]
        self._password = self.init_data[CONF_PASSWORD]
        self._rscpkey = self.init_data[CONF_RSCPKEY]
        self._port = self.init_data.get(CONF_PORT, None)

        if error := await self.validate_input():
            return self._show_setup_form_init(errors={"base": error})

        _LOGGER.debug(f"unique id: {self.unique_id} / {self._host}:{self._port}:{self._proxy.e3dc.serialNumber}")
        if not self.unique_id:
            await self.async_set_unique_id(
                f"{self._proxy.e3dc.serialNumberPrefix}{self._proxy.e3dc.serialNumber}"
            )
            return self.async_show_form(
                step_id="integration_discovery",
                description_placeholders={"info": "create farm controller device"},
            )
        self._abort_if_unique_id_configured()

        final_data: dict[str, Any] = self.init_data
        final_data[CONF_FARMCONTROLLER] = len(self._proxy.e3dc.serialNumber) >= 6 and self._proxy.e3dc.serialNumber[-6] == "1"
        final_data[CONF_API_VERSION] = CONF_VERSION

        return self.async_create_entry(
            title=f"E3DC {'Farm Controller ' if final_data[CONF_FARMCONTROLLER] else ''}{self._proxy.e3dc.model}",
            data=final_data,
        )


    # async def async_step_integration_discovery_continue(self, discovery_info) -> FlowResult:
    #     """Continue the integration discovery step."""
    #     result =  await self.async_step_user(discovery_info)
    #     return result

    def _show_setup_form_init(self, errors: dict[str, str] | None = None) -> FlowResult:
        """Show the setup form to the user."""
        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors or {},
        )

    def _show_setup_form_reauth_confirm(
        self, errors: dict[str, str] | None = None
    ) -> FlowResult:
        """Show the setup form to the user."""
        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors or {},
        )
