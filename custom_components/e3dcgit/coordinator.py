"""Coordinator for E3DC integration."""

from datetime import timedelta
import logging
from typing import Any

from e3dc import E3DC  # Missing Exports:; SendError,

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (  # CoordinatorEntity,; UpdateFailed,
    DataUpdateCoordinator,
)

from .const import CONF_RSCPKEY, DOMAIN

_LOGGER = logging.getLogger(__name__)


class E3DCCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """E3DC Coordinator, fetches all relevant data and provides proxies for all service calls."""

    e3dc: E3DC = None
    _mydata: dict[str, Any] = {}
    _sw_version: str = ""
    _update_guard_powersettings: bool = False

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize E3DC Coordinator and connect."""
        self.host: str | None = config_entry.data.get(CONF_HOST)
        self.username: str | None = config_entry.data.get(CONF_USERNAME)
        self.password: str | None = config_entry.data.get(CONF_PASSWORD)
        self.rscpkey: str | None = config_entry.data.get(CONF_RSCPKEY)
        assert isinstance(config_entry.unique_id, str)
        self.uid: str = config_entry.unique_id

        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=10)
        )

    async def async_connect(self):
        """Establish connection to E3DC."""
        try:
            self.e3dc: E3DC = await self.hass.async_add_executor_job(
                create_e3dcinstance,
                self.username,
                self.password,
                self.host,
                self.rscpkey,
            )
        except Exception as ex:
            raise ConfigEntryAuthFailed from ex

        self._mydata["derate_percent"] = self.e3dc.deratePercent
        self._mydata["derate_power"] = self.e3dc.deratePower
        self._mydata["ext_source_available"] = self.e3dc.externalSourceAvailable != 0
        self._mydata["installed_battery_capacity"] = self.e3dc.installedBatteryCapacity
        self._mydata["installed_peak_power"] = self.e3dc.installedPeakPower
        self._mydata["max_ac_power"] = self.e3dc.maxAcPower
        self._mydata["max_bat_charge_power"] = self.e3dc.maxBatChargePower
        self._mydata["max_bat_discharge_power"] = self.e3dc.maxBatDischargePower
        self._mydata["mac_address"] = self.e3dc.macAddress
        self._mydata["model"] = self.e3dc.model
        self._mydata["start_discharge_default"] = self.e3dc.startDischargeDefault

        # Idea: Maybe Port this to e3dc lib, it can query this in one go during startup.
        self._sw_version = await self._async_e3dc_request_single_tag(
            "INFO_REQ_SW_RELEASE"
        )

    async def _async_e3dc_request_single_tag(self, tag: str) -> Any:
        """Send a single tag request to E3DC, wraps lib call for async usage, supplies defaults."""

        # Signature for reference: Tag, Retries, Keepalive
        result = await self.hass.async_add_executor_job(
            self.e3dc.sendRequestTag, tag, 3, True
        )
        return result

    async def _async_update_data(self) -> dict[str, Any]:
        """Update all data required by our entities in one go."""

        # Now we've to update all dynamic values in self._mydata,
        # connect did already retrieve all static values.

        _LOGGER.debug("Polling general status information")
        poll_data: dict[str, Any] = await self.hass.async_add_executor_job(
            self.e3dc.poll, True
        )
        self._process_poll(poll_data)

        if self._update_guard_powersettings is False:
            _LOGGER.debug("Poll power settings")
            power_settings: dict[
                str, Any | None
            ] = await self.hass.async_add_executor_job(
                self.e3dc.get_power_settings, True
            )
            self._process_power_settings(power_settings)
        else:
            _LOGGER.debug("Not polling powersettings, they are updating right now")

        return self._mydata

    def _process_power_settings(self, power_settings: dict[str, Any | None]):
        """Process retrieved power settings."""
        self._mydata["pset_limits_charge_max"] = power_settings["maxChargePower"]
        self._mydata["pset_limits_discharge_max"] = power_settings["maxDischargePower"]
        self._mydata["pset_limits_discharge_start"] = power_settings[
            "dischargeStartPower"
        ]
        self._mydata["pset_limits_enabled"] = power_settings["powerLimitsUsed"]
        self._mydata["pset_powersave_enabled"] = power_settings["powerSaveEnabled"]
        self._mydata["pset_weatherregulation_enabled"] = power_settings[
            "weatherRegulatedChargeEnabled"
        ]

    def _process_poll(self, poll_data: dict[str, Any]):
        self._mydata["autarky"] = poll_data["autarky"]
        self._mydata["charge_battery"] = max(0, poll_data["consumption"]["battery"])
        self._mydata["consumption_battery"] = poll_data["consumption"]["battery"]
        self._mydata["consumption_grid"] = max(0, poll_data["production"]["grid"])
        self._mydata["consumption_house"] = poll_data["consumption"]["house"]
        self._mydata["consumption_wallbox"] = poll_data["consumption"]["wallbox"]
        self._mydata["delta_grid"] = poll_data["production"]["grid"]
        self._mydata["discharge_battery"] = (
            min(0, poll_data["consumption"]["battery"]) * -1
        )
        self._mydata["production_add"] = poll_data["production"]["add"]
        self._mydata["production_grid"] = min(0, poll_data["production"]["grid"]) * -1
        self._mydata["production_solar"] = poll_data["production"]["solar"]
        self._mydata["selfconsumption"] = poll_data["selfConsumption"]
        self._mydata["soc"] = poll_data["stateOfCharge"]

    def device_info(self) -> DeviceInfo:
        """Return default device info structure."""
        return DeviceInfo(
            manufacturer="E3DC",
            model=self.e3dc.model,
            name=self.e3dc.model,
            connections={(dr.CONNECTION_NETWORK_MAC, self.e3dc.macAddress)},
            identifiers={(DOMAIN, self.uid)},
            sw_version=self._sw_version,
            configuration_url="https://s10.e3dc.com/",
        )

    async def async_set_weather_regulated_charge(self, enabled: bool) -> bool:
        """Enable or disable weather regulated charging."""

        _LOGGER.debug("Updating weather regulated charging to %s", enabled)

        self._update_guard_powersettings = True
        self._mydata["pset_weatherregulation_enabled"] = enabled

        try:
            new_value: bool = await self.hass.async_add_executor_job(
                self.e3dc.set_weather_regulated_charge, enabled, True
            )
        except:
            _LOGGER.exception(
                "Failed to update weather regulated charging to %s", enabled
            )
            # Once we have better exception handling available, we need to throw
            # proper HomeAssistantErrors at this point.
            raise
        else:
            # Ignore newValue at this point, needs fixing e3dc lib.
            new_value = enabled
            self._mydata["pset_weatherregulation_enabled"] = new_value
        finally:
            self._update_guard_powersettings = False

        if new_value != enabled:
            raise HomeAssistantError(
                f"Failed to update weather regulated charging to {enabled}"
            )

        _LOGGER.debug("Successfully updated weather regulated charging to %s", enabled)
        return True

    async def async_set_powersave(self, enabled: bool) -> bool:
        """Enable or disable SmartPower powersaving."""

        _LOGGER.debug("Updating powersaving to %s", enabled)

        self._update_guard_powersettings = True
        self._mydata["pset_powersave_enabled"] = enabled

        try:
            new_value: bool = await self.hass.async_add_executor_job(
                self.e3dc.set_powersave, enabled, True
            )
        except:
            _LOGGER.exception("Failed to update powersaving to %s", enabled)
            # Once we have better exception handling available, we need to throw
            # proper HomeAssistantErrors at this point.
            raise
        else:
            # Ignore newValue at this point, needs fixing e3dc lib.
            new_value = enabled
            self._mydata["pset_powersave_enabled"] = new_value
        finally:
            self._update_guard_powersettings = False

        if new_value != enabled:
            raise HomeAssistantError(f"Failed to update powersaving to {enabled}")

        _LOGGER.debug("Successfully updated powersaving to %s", enabled)
        return True

    async def async_set_power_limits(
        self, max_charge: int | None, max_discharge: int | None
    ) -> None:
        """Set the given power limits and enable them."""

        # Validate the arguments, at least one has to be set.
        if max_charge is None and max_discharge is None:
            raise ValueError(
                "async_set_power_limits must be called with at least one of max_charge or max_discharge."
            )

        if max_charge is not None and max_charge > self.e3dc.maxBatChargePower:
            _LOGGER.debug("Limiting max_charge to %s", self.e3dc.maxBatChargePower)
            max_charge = self.e3dc.maxBatChargePower
        if max_discharge is not None and max_discharge > self.e3dc.maxBatDischargePower:
            _LOGGER.debug(
                "Limiting max_discharge to %s", self.e3dc.maxBatDischargePower
            )
            max_discharge = self.e3dc.maxBatDischargePower

        _LOGGER.debug(
            "Enabling power limits, max_charge: %s, max_discharge: %s",
            max_charge,
            max_discharge,
        )

        try:
            # Call RSCP service.
            # no update guard necessary, as we're called from a service, not an entity
            result: int = await self.hass.async_add_executor_job(
                self.e3dc.set_power_limits, True, max_charge, max_discharge, None, True
            )
        except Exception as ex:
            _LOGGER.exception("Failed to update power limits")
            raise HomeAssistantError("Failed to update power limits") from ex

        if result == -1:
            raise HomeAssistantError("Failed to update power limits")

        if result == 1:
            _LOGGER.warning("The given power limits are not optimal, continuing Anyway")
        else:
            _LOGGER.warning("Successfully set the power limits")


def create_e3dcinstance(username: str, password: str, host: str, rscpkey: str) -> E3DC:
    """Create the actual E3DC instance, this will try to connect and authenticate."""
    e3dc = E3DC(
        E3DC.CONNECT_LOCAL,
        username=username,
        password=password,
        ipAddress=host,
        key=rscpkey,
    )
    return e3dc
