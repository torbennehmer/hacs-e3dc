"""Diagnostics support for E3DC RSCP."""
from __future__ import annotations

import logging
from typing import Any

from e3dc import E3DC

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for our config entry."""
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    e3dc: E3DC = coordinator.e3dc

    return {
        "current_data": coordinator.data,
        "get_system_info": e3dc.get_system_info(),
        "get_system_status": e3dc.get_system_status(),
        "poll": e3dc.poll(),
        "switches": e3dc.poll_switches(),
        "get_pvis_data": e3dc.get_pvis_data(),
        "get_powermeters_data": e3dc.get_powermeters_data(),
        "get_batteries_data": e3dc.get_batteries_data(),
        "get_idle_periods": e3dc.get_idle_periods(),
        "get_power_settings": e3dc.get_power_settings(),
        "EMS_REQ_GET_MANUAL_CHARGE": e3dc.sendRequestTag(
            "EMS_REQ_GET_MANUAL_CHARGE", keepAlive=True
        ),
        "DB_REQ_HISTORY_DATA_DAY": e3dc.sendRequest(
            (
                "DB_REQ_HISTORY_DATA_DAY",
                "Container",
                [
                    (
                        "DB_REQ_HISTORY_TIME_START",
                        "Uint64",
                        coordinator.data["db-day-startts"],
                    ),
                    ("DB_REQ_HISTORY_TIME_INTERVAL", "Uint64", 86400),
                    ("DB_REQ_HISTORY_TIME_SPAN", "Uint64", 86400),
                ],
            ),
            keepAlive=True,
        ),
    }
