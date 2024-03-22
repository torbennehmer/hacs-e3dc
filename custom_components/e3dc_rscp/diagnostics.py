"""Diagnostics support for E3DC RSCP."""

from __future__ import annotations

from collections.abc import Callable
import logging
import re
from traceback import format_exception
from typing import Any

from e3dc import E3DC
from e3dc._rscpTags import RscpTag, RscpType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import E3DCCoordinator
from .e3dc_proxy import E3DCProxy

_LOGGER = logging.getLogger(__name__)

_redact_regex = re.compile("(system-mac|macAddress|serial)", re.IGNORECASE)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for our config entry."""

    dumper: _DiagnosticsDumper = _DiagnosticsDumper(hass, entry)
    dumper.create_dump()
    return dumper.get_dump()


class _DiagnosticsDumper:
    """Helper class to collect a diagnostic dump in a failsafe way."""

    e3dc: E3DC = None
    coordinator: E3DCCoordinator = None
    proxy: E3DCProxy = None
    hass: HomeAssistant = None
    entry: ConfigEntry = None
    result: dict[str, Any] = {}

    def __init__(self, _hass: HomeAssistant, _entry: ConfigEntry):
        """Initialize the dumper and set up a few references."""
        self.hass = _hass
        self.entry = _entry
        self.coordinator = self.hass.data[DOMAIN][self.entry.unique_id]
        self.proxy = self.coordinator.proxy
        self.e3dc = self.proxy.e3dc

    def create_dump(self):
        """Create the dump data and redact pricate data, central call-in point."""
        self._collect_data()
        self._redact_private_information(self.result)

    def get_dump(self) -> dict[str, Any]:
        """Get the collected data."""
        return self.result

    def _collect_data(self):
        """Collect the individual dumped data successivley."""
        self.result: dict[str, Any] = {
            "current_data": self.coordinator.data,
            "get_system_info": self._query_data_for_dump(self.e3dc.get_system_info),
            "get_system_status": self._query_data_for_dump(self.e3dc.get_system_status),
            "get_powermeters": self._query_data_for_dump(self.e3dc.get_powermeters),
            "e3dc_config": self.proxy.e3dc_config,
            "poll": self._query_data_for_dump(self.e3dc.poll),
            "switches": self._query_data_for_dump(self.e3dc.poll_switches),
            "get_pvis_data": self._query_data_for_dump(self.e3dc.get_pvis_data),
            "get_powermeters_data": self._query_data_for_dump(
                self.e3dc.get_powermeters_data
            ),
            "get_batteries_data": self._query_data_for_dump(
                self.e3dc.get_batteries_data
            ),
            "get_idle_periods": self._query_data_for_dump(self.e3dc.get_idle_periods),
            "get_power_settings": self._query_data_for_dump(
                self.e3dc.get_power_settings
            ),
            "EMS_REQ_GET_MANUAL_CHARGE": self._query_data_for_dump(
                lambda: self.e3dc.sendRequestTag(
                    RscpTag.EMS_REQ_GET_MANUAL_CHARGE, keepAlive=True
                )
            ),
            "DB_REQ_HISTORY_DATA_DAY": self._query_data_for_dump(
                lambda: self.e3dc.sendRequest(
                    (
                        RscpTag.DB_REQ_HISTORY_DATA_DAY,
                        "Container",
                        [
                            (
                                RscpTag.DB_REQ_HISTORY_TIME_START,
                                RscpType.Uint64,
                                self.coordinator.data["db-day-startts"],
                            ),
                            (
                                RscpTag.DB_REQ_HISTORY_TIME_INTERVAL,
                                RscpType.Uint64,
                                86400,
                            ),
                            (RscpTag.DB_REQ_HISTORY_TIME_SPAN, RscpType.Uint64, 86400),
                        ],
                    ),
                    keepAlive=True,
                )
            ),
        }

    def _query_data_for_dump(self, call: Callable[[], Any]) -> Any:
        """Query an individual data point using a lambda, protect by exception handling."""
        try:
            tmp = call()
            return tmp
        except Exception as ex:  # pylint: disable=broad-exception-caught
            return {"exception": format_exception(ex)}

    def _redact_private_information(self, data: Any):
        """Redact data recursively so that it can be shared."""

        if isinstance(data, dict | list):
            for key, value in (
                data.items() if isinstance(data, dict) else enumerate(data)
            ):
                if (
                    isinstance(value, str)
                    and isinstance(key, str)
                    and _redact_regex.search(key) is not None
                ):
                    data[key] = f"{value[:3]}<redacted>"
                self._redact_private_information(value)
