"""The E3DC Remote Storage Control Protocol integration."""

# Open tasks from integration quality checklist:
# 1. Handles internet unavailable. Log a warning once when unavailable, log once when reconnected.
#    -> Needs special care, as auth credentials change when E3DC is offline,
#       haven't tested this yet, so we work only as long as we're connected.
# 2. Handles device/service unavailable. Log a warning once when unavailable, log once when reconnected.
#    -> Similar to previous point, right now, we'll run into connection errors,
#       we need an update to the E3DC lib to catch this safely, working on that one.
# 3. Set available property to False if appropriate
#    -> once 2 is done, update the entity's available state appropriately.

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from .const import DOMAIN, PLATFORMS
from .coordinator import E3DCCoordinator
from .services import async_setup_services


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
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok
