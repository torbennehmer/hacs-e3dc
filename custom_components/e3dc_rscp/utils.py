"""Utility functions for E3DC RSCP integration."""
import logging
from .const import CONF_RSCPKEY, DOMAIN

from .e3dc_proxy import E3DCProxy
from homeassistant.const import (
    CONF_HOST,
    CONF_PASSWORD,
    CONF_USERNAME,
    CONF_PORT,
)
from homeassistant.config_entries import (
    SOURCE_INTEGRATION_DISCOVERY
)

_LOGGER = logging.getLogger(__name__)

async def initialize_farm_controller_flow_if_needed(hass, proxy: E3DCProxy, username: str | None, password: str | None, rscp: str | None):
    """Check if farm controller flow needs to be initiated and do so if needed."""
    remote_control_ip: str | None = proxy.get_remote_control_ip()
    _LOGGER.debug(f"Found remote control IP: {remote_control_ip}")

    if (remote_control_ip):
        """ Initiate sub-flow for farm controller configuration. """

        host, port = remote_control_ip.split(":")
        port = int(port)
        controller_found = False

        """ try to find existing controller entry """
        for entry in hass.config_entries.async_entries(DOMAIN):
            is_host_and_port_match = (
                entry.data.get(CONF_HOST) == host and entry.data.get(CONF_PORT) == port
            )
            is_title_match = entry.title == f'E3DC Farm Controller at {host}'
            _LOGGER.debug(f"Checking existing entry {entry.title} for host/port match: {is_host_and_port_match}, title match: {is_title_match}")
            if is_host_and_port_match or is_title_match:
                controller_found = True

        if not controller_found:
            _LOGGER.debug(f"Creating sub-flow for farm controller at {host}:{port}")
            await hass.config_entries.flow.async_init(
                DOMAIN,
                context={
                    "source": SOURCE_INTEGRATION_DISCOVERY,
                    "title_placeholders": {"name": f'E3DC Farm Controller at {host}'}
                },
                data={
                    CONF_HOST: host,
                    CONF_PORT: port,
                    CONF_USERNAME: username,
                    CONF_PASSWORD: password,
                    CONF_RSCPKEY: rscp,
                },
            )