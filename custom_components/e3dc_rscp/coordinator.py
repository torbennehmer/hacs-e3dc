"""Coordinator for E3DC integration."""

from datetime import timedelta, datetime
import logging
from time import time
from typing import Any
import pytz
import re

from e3dc._rscpTags import PowermeterType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util.dt import as_timestamp, start_of_local_day
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.sensor import SensorStateClass

from .const import DOMAIN, MAX_WALLBOXES_POSSIBLE

from .e3dc_proxy import E3DCProxy

_LOGGER = logging.getLogger(__name__)
_STAT_REFRESH_INTERVAL = 60


class E3DCCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """E3DC Coordinator, fetches all relevant data and provides proxies for all service calls."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize E3DC Coordinator and connect."""
        assert isinstance(config_entry.unique_id, str)
        self.uid: str = config_entry.unique_id
        self.proxy = E3DCProxy(hass, config_entry)
        self._mydata: dict[str, Any] = {}
        self._sw_version: str = ""
        self._update_guard_powersettings: bool = False
        self._update_guard_wallboxsettings: bool = False
        self._wallboxes: list[dict[str, str | int]] = []
        self._timezone_offset: int = 0
        self._next_stat_update: float = 0

        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=10)
        )

    async def async_connect(self):
        """Establish connection to E3DC."""

        # TODO: Beautify this, make the code flow with the connects/disconnects more natural.
        # Have a call to autoconf, then connect with it.
        await self.hass.async_add_executor_job(self.proxy.connect)
        await self._async_connect_additional_powermeters()

        self._mydata["system-derate-percent"] = self.proxy.e3dc.deratePercent
        self._mydata["system-derate-power"] = self.proxy.e3dc.deratePower
        self._mydata["system-additional-source-available"] = (
            self.proxy.e3dc.externalSourceAvailable != 0
        )
        self._mydata[
            "system-battery-installed-capacity"
        ] = self.proxy.e3dc.installedBatteryCapacity
        self._mydata[
            "system-battery-installed-peak"
        ] = self.proxy.e3dc.installedPeakPower
        self._mydata["system-ac-maxpower"] = self.proxy.e3dc.maxAcPower
        self._mydata["system-battery-charge-max"] = self.proxy.e3dc.maxBatChargePower
        self._mydata[
            "system-battery-discharge-max"
        ] = self.proxy.e3dc.maxBatDischargePower
        self._mydata["system-mac"] = self.proxy.e3dc.macAddress
        self._mydata["model"] = self.proxy.e3dc.model
        self._mydata[
            "system-battery-discharge-minimum-default"
        ] = self.proxy.e3dc.startDischargeDefault

        # Idea: Maybe Port this to e3dc lib, it can query this in one go during startup.
        self._sw_version = await self.hass.async_add_executor_job(
            self.proxy.get_software_version
        )

        await self._load_timezone_settings()


    async def async_identify_wallboxes(self, hass: HomeAssistant):
        """Identify availability of Wallboxes if get_wallbox_identification_data() returns meaningful data."""

        for wallbox_index in range(0, MAX_WALLBOXES_POSSIBLE-1):
            try:
                request_data: dict[str, Any] = await self.hass.async_add_executor_job(
                    self.proxy.get_wallbox_identification_data, wallbox_index
                )
            except HomeAssistantError as ex:
                _LOGGER.warning("Failed to load wallbox with index %s, not updating data: %s", wallbox_index, ex)
                return

            if "macAddress" in request_data:
                _LOGGER.debug("Wallbox with index %s has been found", wallbox_index)

                unique_id = dr.format_mac(request_data["macAddress"])
                wallboxType = request_data["wallboxType"]
                model = f"Wallbox Type {wallboxType}"

                deviceInfo = DeviceInfo(
                    identifiers={(DOMAIN, unique_id)},
                    via_device=(DOMAIN, self.uid),
                    manufacturer="E3DC",
                    name=request_data["deviceName"],
                    model=model,
                    sw_version=request_data["firmwareVersion"],
                    serial_number=request_data["wallboxSerial"],
                    connections={(dr.CONNECTION_NETWORK_MAC, dr.format_mac(request_data["macAddress"]))},
                    configuration_url="https://my.e3dc.com/",
                )

                wallbox = {
                    "index": wallbox_index,
                    "key": unique_id,
                    "deviceInfo": deviceInfo,
                    "lowerCurrentLimit": request_data["lowerCurrentLimit"],
                    "upperCurrentLimit": request_data["upperCurrentLimit"]
                }
                self.wallboxes.append(wallbox)
            else:
                _LOGGER.debug("No Wallbox with index %s has been found", wallbox_index)

    # Getter for _wallboxes
    @property
    def wallboxes(self) -> list[dict[str, str | int]]:
        """Get the list of wallboxes."""
        return self._wallboxes

    # Setter for _wallboxes
    @wallboxes.setter
    def wallboxes(self, value: list[dict[str, str | int]]) -> None:
        """Set the list of wallboxes."""
        self._wallboxes = value

    # Setter for individual wallbox values
    def setWallboxValue(self, index: int, key: str, value: Any) -> None:
        """Set the value for a specific key in a wallbox identified by its index."""
        for wallbox in self._wallboxes:
            if wallbox['index'] == index:
                wallbox[key] = value
                _LOGGER.debug(f"Set {key} to {value} for wallbox with index {index}")
                return
        raise ValueError(f"Wallbox with index {index} not found")

    # Getter for individual wallbox values
    def getWallboxValue(self, index: int, key: str) -> Any:
        """Get the value for a specific key in a wallbox identified by its index."""
        for wallbox in self._wallboxes:
            if wallbox['index'] == index:
                value = wallbox.get(key)
                if value is not None:
                    _LOGGER.debug(f"Got {key} value {value} for wallbox with index {index}")
                    return value
                else:
                    raise KeyError(f"Key {key} not found in wallbox with index {index}")
        raise ValueError(f"Wallbox with index {index} not found")

    async def _async_connect_additional_powermeters(self):
        """Identify the installed powermeters and reconnect to E3DC with this config."""
        # TODO: Restructure config so that we are indexed by powemeter ID.
        self.proxy.e3dc_config["powermeters"] = await self.hass.async_add_executor_job(
            self.proxy.get_powermeters
        )

        for powermeter in self.proxy.e3dc_config["powermeters"]:
            if powermeter["type"] == PowermeterType.PM_TYPE_ROOT.value:
                powermeter["name"] = "Root PM"
                powermeter["key"] = "root-pm"
                powermeter["total-state-class"] = SensorStateClass.TOTAL
                powermeter["negate-measure"] = False

            else:
                powermeter["name"] = (
                    powermeter["typeName"]
                    .replace("PM_TYPE_", "")
                    .replace("_", " ")
                    .capitalize()
                )
                powermeter["key"] = (
                    powermeter["typeName"]
                    .replace("PM_TYPE_", "")
                    .replace("_", "-")
                    .lower()
                    + "-"
                    + str(powermeter["index"])
                )

                match powermeter["type"]:
                    case ( PowermeterType.PM_TYPE_ADDITIONAL_PRODUCTION.value
                          | PowermeterType.PM_TYPE_ADDITIONAL.value
                    ):
                        powermeter[
                            "total-state-class"
                        ] = SensorStateClass.TOTAL_INCREASING
                        powermeter["negate-measure"] = True

                    case PowermeterType.PM_TYPE_ADDITIONAL_CONSUMPTION.value:
                        powermeter[
                            "total-state-class"
                        ] = SensorStateClass.TOTAL_INCREASING
                        powermeter["negate-measure"] = False

                    case _:
                        powermeter["total-state-class"] = SensorStateClass.TOTAL
                        powermeter["negate-measure"] = False

        await self.hass.async_add_executor_job(self.proxy.disconnect)
        await self.hass.async_add_executor_job(
            self.proxy.connect,
            self.proxy.e3dc_config,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update all data required by our entities in one go."""

        # Now we've to update all dynamic values in self._mydata,
        # connect did already retrieve all static values.

        _LOGGER.debug("Polling general status information")
        await self._load_and_process_poll()

        # TODO: Check if we need to replace this with a safe IPC sync
        if self._update_guard_powersettings is False:
            _LOGGER.debug("Poll power settings")
            await self._load_and_process_power_settings()
        else:
            _LOGGER.debug("Not polling powersettings, they are updating right now")

        _LOGGER.debug("Polling manual charge information")
        await self._load_and_process_manual_charge()

        if self._update_guard_wallboxsettings is False:
            _LOGGER.debug("Polling additional powermeters")
            await self._load_and_process_powermeters_data()
        else:
            _LOGGER.debug("Not polling wallbox, they are updating right now")

        if len(self.wallboxes) > 0:
            _LOGGER.debug("Polling wallbox")
            await self._load_and_process_wallbox_data()

        # Only poll power statstics once per minute. E3DC updates it only once per 15
        # minutes anyway, this should be a good compromise to get the metrics shortly
        # before the end of the day.
        if self._next_stat_update < time():
            _LOGGER.debug("Polling today's power metrics")
            await self._load_and_process_db_data_today()
            self._next_stat_update = time() + _STAT_REFRESH_INTERVAL
            # TODO: Reduce interval further, but take start_ts into account to get an
            # end of day reading of the metric.
        else:
            _LOGGER.debug("Skipping power metrics poll.")

        return self._mydata

    async def _load_and_process_power_settings(self):
        """Load and process power settings."""
        try:
            power_settings: dict[str, Any] = await self.hass.async_add_executor_job(self.proxy.get_power_settings)
        except HomeAssistantError as ex:
            _LOGGER.warning("Failed to load power settings, not updating data: %s", ex)
            return

        self._mydata["pset-limit-charge"] = power_settings["maxChargePower"]
        self._mydata["pset-limit-discharge"] = power_settings["maxDischargePower"]
        self._mydata["pset-limit-discharge-minimum"] = power_settings[
            "dischargeStartPower"
        ]
        self._mydata["pset-limit-enabled"] = power_settings["powerLimitsUsed"]
        self._mydata["pset-powersaving-enabled"] = power_settings["powerSaveEnabled"]
        self._mydata["pset-weatherregulationenabled"] = power_settings[
            "weatherRegulatedChargeEnabled"
        ]

    async def _load_and_process_poll(self):
        """Load and process standard poll data."""
        try:
            poll_data: dict[str, Any] = await self.hass.async_add_executor_job(self.proxy.poll)
        except HomeAssistantError as ex:
            _LOGGER.warning("Failed to poll, not updating data: %s", ex)
            return

        self._mydata["additional-production"] = poll_data["production"]["add"]
        self._mydata["autarky"] = poll_data["autarky"]
        self._mydata["battery-charge"] = max(0, poll_data["consumption"]["battery"])
        self._mydata["battery-discharge"] = (
            min(0, poll_data["consumption"]["battery"]) * -1
        )
        self._mydata["battery-netchange"] = poll_data["consumption"]["battery"]
        self._mydata["grid-consumption"] = max(0, poll_data["production"]["grid"])
        self._mydata["grid-netchange"] = poll_data["production"]["grid"]
        self._mydata["grid-production"] = min(0, poll_data["production"]["grid"]) * -1
        self._mydata["house-consumption"] = poll_data["consumption"]["house"]
        self._mydata["selfconsumption"] = poll_data["selfConsumption"]
        self._mydata["soc"] = poll_data["stateOfCharge"]
        self._mydata["solar-production"] = poll_data["production"]["solar"]
        self._mydata["wallbox-consumption"] = poll_data["consumption"]["wallbox"]

    async def _load_and_process_db_data_today(self) -> None:
        """Load and process retrieved db data settings."""
        try:
            db_data: dict[str, Any] = await self.hass.async_add_executor_job(
                self.proxy.get_db_data, self._get_db_data_day_timestamp(), 86400
            )
        except HomeAssistantError as ex:
            _LOGGER.warning("Failed to load daily stats, not updating data: %s", ex)
            return

        self._mydata["db-day-autarky"] = db_data["autarky"]
        self._mydata["db-day-battery-charge"] = db_data["bat_power_in"]
        self._mydata["db-day-battery-discharge"] = db_data["bat_power_out"]
        self._mydata["db-day-grid-consumption"] = db_data["grid_power_out"]
        self._mydata["db-day-grid-production"] = db_data["grid_power_in"]
        self._mydata["db-day-house-consumption"] = db_data["consumption"]
        self._mydata["db-day-selfconsumption"] = db_data["consumed_production"]
        self._mydata["db-day-solar-production"] = db_data["solarProduction"]
        self._mydata["db-day-startts"] = db_data["startTimestamp"]

    async def _load_and_process_manual_charge(self) -> None:
        """Loand and process manual charge status."""
        try:
            request_data: dict[str, Any] = await self.hass.async_add_executor_job(self.proxy.get_manual_charge)
        except HomeAssistantError as ex:
            _LOGGER.warning("Failed to load manual charge state, not updating data: %s", ex)
            return

        self._mydata["manual-charge-active"] = request_data["active"]
        self._mydata["manual-charge-energy"] = request_data["energy"]

    async def _load_and_process_powermeters_data(self) -> None:
        """Load and process additional sources to existing data."""
        try:
            request_data: dict[str, Any] = await self.hass.async_add_executor_job(self.proxy.get_powermeters_data)
        except HomeAssistantError as ex:
            _LOGGER.warning("Failed to load powermeters, not updating data: %s", ex)
            return

        for key, value in request_data.items():
            self._mydata[key] = value

    async def _load_and_process_wallbox_data(self) -> None:
        """Load and process wallbox data to existing data."""

        for wallbox in self.wallboxes:
            try:
                request_data: dict[str, Any] = await self.hass.async_add_executor_job(
                    self.proxy.get_wallbox_data, wallbox["index"]
                )
            except HomeAssistantError as ex:
                _LOGGER.warning("Failed to load wallboxes, not updating data: %s", ex)
                return

            for key, value in request_data.items():
                formatted_key = re.sub(r'(?<!^)(?=[A-Z])', '-', key).lower()   #RegEx to convert from CamelCase to kebab-case
                if formatted_key == "plug-locked":
                    formatted_key = "plug-lock"
                    value = not value  # Inverse to match HA's Lock On/Off interpretation
                if formatted_key == "plugged":
                    formatted_key = "plug"
                if formatted_key == "schuko-on":
                    formatted_key = "schuko"
                if formatted_key == "sun-mode-on":
                    formatted_key = "sun-mode"
                if formatted_key == "charging-active":
                    formatted_key = "charging"
                wallbox_key = wallbox["key"]
                self._mydata[f"{wallbox_key}-{formatted_key}"] = value

    async def _load_timezone_settings(self):
        """Load the current timezone offset from the E3DC, using its local timezone data.

        Required to correctly retrieve power statistics for today.
        """
        tz_name: str = await self.hass.async_add_executor_job(self.proxy.get_timezone)

        tz_offset: int | None = None
        try:
            tz_info: pytz.timezone = await self.hass.async_add_executor_job(pytz.timezone, tz_name)
            dt_tmp: datetime = datetime.now(tz_info)
            tz_offset = dt_tmp.utcoffset().seconds
        except pytz.UnknownTimeZoneError:
            _LOGGER.exception("Failed to load timezone from E3DC, falling back to heuristics.")

        if tz_offset is None:
            # Fallback to compute the offset using current times from E3DC:
            ts_local: int = await self.hass.async_add_executor_job(
                self.proxy.get_time
            )
            ts_utc: int = await self.hass.async_add_executor_job(
                self.proxy.get_timeutc
            )
            delta: int = ts_local - ts_utc
            tz_offset = int(1800 * round(delta / 1800))

        self._mydata["e3dc_timezone"] = tz_name
        self._timezone_offset = tz_offset

    def _get_db_data_day_timestamp(self) -> int:
        """Get the local start-of-day timestamp for DB Query, needs some tweaking."""
        today: datetime = start_of_local_day()
        today_ts: int = int(as_timestamp(today))
        _LOGGER.debug(
            "Midnight is %s, DB query timestamp is %s, applied offset: %s",
            today,
            today_ts,
            self._timezone_offset,
        )
        # tz_hass: pytz.timezone = pytz.timezone("Europe/Berlin")
        # today: datetime = datetime.now(tz_hass).replace(hour=0, minute=0, second=0, microsecond=0)
        # today_ts: int = today.timestamp()
        # Move to local time, the Timestamp needed by the E3DC DB queries are
        # not in UTC as they should be.
        today_ts += self._timezone_offset
        return today_ts

    def device_info(self) -> DeviceInfo:
        """Return default device info structure."""
        return DeviceInfo(
            manufacturer="E3DC",
            model=self.proxy.e3dc.model,
            name=self.proxy.e3dc.model,
            serial_number=self.proxy.e3dc.serialNumber,
            connections={(dr.CONNECTION_NETWORK_MAC, self.proxy.e3dc.macAddress)},
            identifiers={(DOMAIN, self.uid)},
            sw_version=self._sw_version,
            configuration_url="https://my.e3dc.com/",
        )

    async def async_set_weather_regulated_charge(self, enabled: bool) -> bool:
        """Enable or disable weather regulated charging."""
        _LOGGER.debug("Updating weather regulated chargsing to %s", enabled)

        try:
            self._update_guard_powersettings = True
            await self.hass.async_add_executor_job(
                self.proxy.set_weather_regulated_charge, enabled
            )
            self._mydata["pset-weatherregulationenabled"] = enabled
        finally:
            self._update_guard_powersettings = False

        _LOGGER.debug("Successfully updated weather regulated charging to %s", enabled)
        return True

    async def async_set_powersave(self, enabled: bool) -> bool:
        """Enable or disable SmartPower powersaving."""
        _LOGGER.debug("Updating powersaving to %s", enabled)

        try:
            self._update_guard_powersettings = True
            await self.hass.async_add_executor_job(self.proxy.set_powersave, enabled)
            self._mydata["pset-powersaving-enabled"] = enabled
        finally:
            self._update_guard_powersettings = False

        _LOGGER.debug("Updated powersaving to %s", enabled)
        return True

    async def async_set_wallbox_sun_mode(self, enabled: bool, wallbox_index: int) -> bool:
        """Enable or disable wallbox sun mode."""
        _LOGGER.debug("Updating wallbox sun mode to %s", enabled)

        try:
            self._update_guard_wallboxsettings = True
            await self.hass.async_add_executor_job(
                self.proxy.set_wallbox_sun_mode, enabled, wallbox_index
            )
            self._mydata["wallbox-sun-mode"] = enabled
        except Exception as ex:
            _LOGGER.error("Failed to set wallbox sun mode to %s: %s", enabled, ex)
            return False
        finally:
            self._update_guard_wallboxsettings = False

        _LOGGER.debug("Successfully updated wallbox sun mode to %s", enabled)
        return True

    async def async_set_wallbox_schuko(self, enabled: bool, wallbox_index: int) -> bool:
        """Enable or disable wallbox schuko."""
        _LOGGER.debug("Updating wallbox schuko to %s", enabled)

        try:
            self._update_guard_wallboxsettings = True
            await self.hass.async_add_executor_job(
                self.proxy.set_wallbox_schuko, enabled, wallbox_index
            )
            self._mydata["wallbox-schuko"] = enabled
        except Exception as ex:
            _LOGGER.error("Failed to set wallbox schuko to %s: %s", enabled, ex)
            return False
        finally:
            self._update_guard_wallboxsettings = False

        _LOGGER.debug("Successfully updated wallbox schuko to %s", enabled)
        return True

    async def async_toggle_wallbox_phases(self, wallbox_index: int) -> bool:
        """Toggle the Wallbox Phases between 1 and 3."""
        _LOGGER.debug("Toggling the Wallbox Phases")

        try:
            await self.hass.async_add_executor_job(
                self.proxy.toggle_wallbox_phases, wallbox_index
            )
        except Exception as ex:
            _LOGGER.error("Failed to toggle wallbox phases: %s", ex)
            return False

        _LOGGER.debug("Successfully toggled wallbox phases")
        return True

    async def async_toggle_wallbox_charging(self, wallbox_index: int) -> bool:
        """Toggle the Wallbox charging state."""
        _LOGGER.debug("Toggling the Wallbox charging state")

        try:
            await self.hass.async_add_executor_job(
                self.proxy.toggle_wallbox_charging, wallbox_index
            )
        except Exception as ex:
            _LOGGER.error("Failed to toggle wallbox charging state: %s", ex)
            return False

        _LOGGER.debug("Successfully toggled wallbox charging state")
        return True

    async def async_clear_power_limits(self) -> None:
        """Clear any active power limit."""

        _LOGGER.debug("Clearing any active power limit.")

        # Call RSCP service.
        # no update guard necessary, as we're called from a service, not an entity
        await self.hass.async_add_executor_job(
            self.proxy.set_power_limits, False, None, None, None
        )

        _LOGGER.debug("Successfully cleared the power limits")

    async def async_set_wallbox_max_charge_current(self, current: int | None, wallbox_index: int) -> None:
        """Set the wallbox max charge current."""

        # TODO: Add more refined way to deal with maximum charge current, right now it's hard coded to 32A. The max current is dependant on the local installations, many WBs are throttled at 16A, not 32A due to power grid restrictions.

        # Validate the argument
        if current is None or current <= 0:
            raise ValueError(
                "async_set_wallbox_max_charge_current must be called with a positive current value."
            )

        if wallbox_index < 0 or wallbox_index >= MAX_WALLBOXES_POSSIBLE:
            raise ValueError(
                "async_set_wallbox_max_charge_current must be called with a valid wallbox id."
            )

        upperCurrentLimit = self.getWallboxValue(wallbox_index, "upperCurrentLimit")
        if current > upperCurrentLimit:
            _LOGGER.warning("Requested Wallbox current of %s is too high. Limiting current to %s", current, upperCurrentLimit)
            current = upperCurrentLimit

        lowerCurrentLimit = self.getWallboxValue(wallbox_index, "lowerCurrentLimit")
        if current < lowerCurrentLimit:
            _LOGGER.warning("Requested Wallbox current of %s is too low. Limiting current to %s", current, lowerCurrentLimit)
            current = lowerCurrentLimit


        _LOGGER.debug("Setting wallbox max charge current to %s", current)

        await self.hass.async_add_executor_job(
            self.proxy.set_wallbox_max_charge_current, current, wallbox_index
        )

        _LOGGER.debug("Successfully set the wallbox max charge current to %s", current)

    async def async_set_power_limits(
        self, max_charge: int | None, max_discharge: int | None
    ) -> None:
        """Set the given power limits and enable them."""

        # Validate the arguments, at least one has to be set.
        if max_charge is None and max_discharge is None:
            raise ValueError(
                "async_set_power_limits must be called with at least one of "
                "max_charge or max_discharge."
            )

        if max_charge is not None and max_charge > self.proxy.e3dc.maxBatChargePower:
            _LOGGER.warning(
                "Limiting max_charge to %s", self.proxy.e3dc.maxBatChargePower
            )
            max_charge = self.proxy.e3dc.maxBatChargePower
        if (
            max_discharge is not None
            and max_discharge > self.proxy.e3dc.maxBatDischargePower
        ):
            _LOGGER.warning(
                "Limiting max_discharge to %s", self.proxy.e3dc.maxBatDischargePower
            )
            max_discharge = self.proxy.e3dc.maxBatDischargePower

        _LOGGER.debug(
            "Enabling power limits, max_charge: %s, max_discharge: %s",
            max_charge,
            max_discharge,
        )

        await self.hass.async_add_executor_job(
            self.proxy.set_power_limits, True, max_charge, max_discharge, None
        )

        _LOGGER.debug("Successfully set the power limits")

    async def async_manual_charge(self, charge_amount_wh: int) -> None:
        """Start manual charging the given amount, zero will stop charging."""

        # Validate the arguments
        if charge_amount_wh < 0:
            raise ValueError("Charge amount must be positive or zero.")

        _LOGGER.debug(
            "Starting manual charge of: %s Wh",
            charge_amount_wh,
        )

        # Call RSCP service.
        # no update guard necessary, as we're called from a service, not an entity
        await self.hass.async_add_executor_job(
            self.proxy.start_manual_charge, charge_amount_wh
        )

        _LOGGER.debug("Manual charging start command has been sent.")
