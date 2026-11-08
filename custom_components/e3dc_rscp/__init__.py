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

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import entity_registry as er

from .const import CONF_FARMCONTROLLER, DOMAIN, PLATFORMS

from homeassistant.const import (
    CONF_API_VERSION,
    CONF_PORT,
)
from .coordinator import E3DCCoordinator
from .services import async_setup_services
from e3dc._e3dc_rscp_local import DEFAULT_PORT as RSCP_PORT

_LOGGER = logging.getLogger(__name__)

# Entity keys previously shipped with entity_registry_enabled_default=False.
# Changing the description default alone does not re-enable existing registry
# entries that HA marked as disabled_by="integration" (issue #43).
_ADDITIONAL_PRODUCTION_KEY = "additional-production"

# Plant / status entities now enabled by default. Existing installs keep
# disabled_by="integration" until we clear it here. User opt-outs stay off.
_DEFAULT_ENABLE_TRANSLATION_KEYS = frozenset(
    {
        "system-derate-power",
        "system-ac-maxpower",
        "system-pv-derated",
        "pset-limit-discharge-minimum",
        "battery-module-soh-reported",
        "system-rescue-battery-enabled",
        "pset-powersaving-enabled",
    }
)


def _is_disabled_by_integration(entity_entry: Any) -> bool:
    """Return True when HA disabled the entity via entity_registry_enabled_default."""
    disabled_by = entity_entry.disabled_by
    if disabled_by is None:
        return False
    return getattr(disabled_by, "value", disabled_by) == "integration"


def _async_enable_integration_disabled(
    hass: HomeAssistant,
    entry: ConfigEntry,
    *,
    translation_keys: frozenset[str] | None = None,
    unique_id_suffix: str | None = None,
    reason: str,
) -> None:
    """Clear disabled_by=integration for matching entities. User disables stay."""
    ent_reg = er.async_get(hass)
    for entity_entry in er.async_entries_for_config_entry(ent_reg, entry.entry_id):
        if entity_entry.platform != DOMAIN:
            continue
        if not _is_disabled_by_integration(entity_entry):
            continue
        if translation_keys is not None:
            if getattr(entity_entry, "translation_key", None) not in translation_keys:
                continue
        elif unique_id_suffix is not None:
            if not entity_entry.unique_id.endswith(unique_id_suffix):
                continue
        else:
            continue
        _LOGGER.info("Enabling %s - %s", entity_entry.entity_id, reason)
        ent_reg.async_update_entity(entity_entry.entity_id, disabled_by=None)


async def _async_enable_additional_production_if_present(
    hass: HomeAssistant, entry: ConfigEntry, coordinator: E3DCCoordinator
) -> None:
    """Re-enable additional-production when an external source is present."""
    if not coordinator.additional_production_available:
        return
    _async_enable_integration_disabled(
        hass,
        entry,
        unique_id_suffix=f"_{_ADDITIONAL_PRODUCTION_KEY}",
        reason="additional production source detected",
    )


async def _async_enable_default_plant_entities(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Re-enable plant entities that are now default-on for existing installs."""
    _async_enable_integration_disabled(
        hass,
        entry,
        translation_keys=_DEFAULT_ENABLE_TRANSLATION_KEYS,
        reason="now enabled by default",
    )


async def async_migrate_entry(hass, config_entry: ConfigEntry) -> bool:
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
    await _async_enable_additional_production_if_present(hass, entry, coordinator)
    await _async_enable_default_plant_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await async_setup_services(hass)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.unique_id)

    return unload_ok
