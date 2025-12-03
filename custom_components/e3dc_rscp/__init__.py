"""The E3DC Remote Storage Control Protocol integration."""

# Open tasks from integration quality checklist:
# 1. Handles internet unavailable. Log a warning once when unavailable,
#    log once when reconnected.
#    -> Needs special care, as auth credentials change when E3DC is offline,
#       haven't tested this yet, so we work only as long as we're connected.
# 2. Handles device/service unavailable. Log a warning once when unavailable,
#    log once when reconnected.
#    -> Similar to previous point, right now, we'll run into connection errors,
#       we need an update to the E3DC lib to catch this safely, working on that one.
# 3. Set available property to False if appropriate
#    -> once 2 is done, update the entity's available state appropriately.

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import CONF_FARMCONTROLLER, DOMAIN, PLATFORMS

from homeassistant.const import (
    CONF_API_VERSION,
    CONF_PORT,
)
from .coordinator import E3DCCoordinator
from .services import async_setup_services
from e3dc._e3dc_rscp_local import PORT as RSCP_PORT

async def async_migrate_entry(hass, config_entry: ConfigEntry):
    """Migrate config entry to new format."""
    if config_entry.version < 2:
        # Migration durchführen
        new_data = dict(config_entry.data)
        new_data[CONF_API_VERSION] = 2
        new_data[CONF_PORT] = RSCP_PORT
        new_data[CONF_FARMCONTROLLER] = False
        hass.config_entries.async_update_entry(config_entry, data=new_data, version=2)

        return True
    return False

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up E3DC Remote Storage Control Protocol from a config entry."""

    coordinator: E3DCCoordinator = E3DCCoordinator(hass, entry)
    try:
        await coordinator.async_connect()
        await coordinator.async_config_entry_first_refresh()
    except ConfigEntryAuthFailed:
        raise
    except Exception as ex:
        raise ConfigEntryNotReady(f"Configuration not yet ready: {ex}") from ex

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.unique_id] = coordinator
    await coordinator.async_identify_farm(hass)
    await coordinator.async_identify_sgready()
    await coordinator.async_identify_wallboxes(hass)
    await coordinator.async_identify_batteries(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok
