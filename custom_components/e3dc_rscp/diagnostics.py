"""Diagnostics support for E3DC RSCP."""
from __future__ import annotations

from collections.abc import Callable
import logging
from traceback import format_exception
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

    dumper: _DiagnosticsDumper = _DiagnosticsDumper(hass, entry)
    dumper.create_dump()
    return dumper.get_dump()


class _DiagnosticsDumper:
    """Helper class to collect a diagnostic dump in a failsafe way."""

    e3dc: E3DC = None
    coordinator: E3DCCoordinator = None
    hass: HomeAssistant = None
    entry: ConfigEntry = None
    result: dict[str, Any] = {}

    def __init__(self, _hass: HomeAssistant, _entry: ConfigEntry):
        """Initialize the dumper and set up a few references."""
        self.hass = _hass
        self.entry = _entry
        self.coordinator = self.hass.data[DOMAIN][self.entry.unique_id]
        self.e3dc = self.coordinator.e3dc

    def create_dump(self):
        """Create the dump data and redact pricate data, central call-in point."""
        self._collect_data()
        self._redact_private_information_from_dump()

    def get_dump(self) -> dict[str, Any]:
        """Get the collected data."""
        return self.result

    def _collect_data(self):
        """Collect the individual dumped data successivley."""
        self.result: dict[str, Any] = {
            "current_data": self.coordinator.data,
            "get_system_info": self._query_data_for_dump(self.e3dc.get_system_info),
            "get_system_status": self._query_data_for_dump(self.e3dc.get_system_status),
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
                    "EMS_REQ_GET_MANUAL_CHARGE", keepAlive=True
                )
            ),
            "DB_REQ_HISTORY_DATA_DAY": self._query_data_for_dump(
                lambda: self.e3dc.sendRequest(
                    (
                        "DB_REQ_HISTORY_DATA_DAY",
                        "Container",
                        [
                            (
                                "DB_REQ_HISTORY_TIME_START",
                                "Uint64",
                                self.coordinator.data["db-day-startts"],
                            ),
                            ("DB_REQ_HISTORY_TIME_INTERVAL", "Uint64", 86400),
                            ("DB_REQ_HISTORY_TIME_SPAN", "Uint64", 86400),
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

    def _redact_private_information_from_dump(self):
        """Redact sensitive data from the dump so that it can be shared."""
        self.result["current_data"]["system-mac"] = "<redacted>"
        self.result["get_system_info"]["macAddress"] = "<redacted>"
        self.result["get_system_info"][
            "serial"
        ] = f"{self.result['get_system_info']['serial'][:3]}<redacted>"

        for pvi in self.result["get_pvis_data"]:
            pvi["serialNumber"] = f"{pvi['serialNumber'][:3]}<redacted>"

        for bat in self.result["get_batteries_data"]:
            for dcb in bat["dcbs"]:
                bat["dcbs"][dcb][
                    "serialCode"
                ] = f"{bat['dcbs'][dcb]['serialCode'][:3]}<redacted>"
