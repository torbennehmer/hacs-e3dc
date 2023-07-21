"""Coordinator for E3DC integration."""

from datetime import timedelta, datetime
import logging
from time import time
from typing import Any
import pytz

from e3dc import E3DC  # Missing Exports:; SendError,
from e3dc._rscpLib import rscpFindTag

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import as_timestamp, start_of_local_day
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import (  # CoordinatorEntity,; UpdateFailed,
    DataUpdateCoordinator,
)

from .const import CONF_RSCPKEY, DOMAIN

_LOGGER = logging.getLogger(__name__)
_STAT_REFRESH_INTERVAL = 60


class E3DCCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """E3DC Coordinator, fetches all relevant data and provides proxies for all service calls."""

    e3dc: E3DC = None
    _mydata: dict[str, Any] = {}
    _sw_version: str = ""
    _update_guard_powersettings: bool = False
    _timezone_offset: int = 0
    _next_stat_update: float = 0

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

        self._mydata["system-derate-percent"] = self.e3dc.deratePercent
        self._mydata["system-derate-power"] = self.e3dc.deratePower
        self._mydata["system-additional-source-available"] = (
            self.e3dc.externalSourceAvailable != 0
        )
        self._mydata[
            "system-battery-installed-capacity"
        ] = self.e3dc.installedBatteryCapacity
        self._mydata["system-battery-installed-peak"] = self.e3dc.installedPeakPower
        self._mydata["system-ac-maxpower"] = self.e3dc.maxAcPower
        self._mydata["system-battery-charge-max"] = self.e3dc.maxBatChargePower
        self._mydata["system-battery-discharge-max"] = self.e3dc.maxBatDischargePower
        self._mydata["system-mac"] = self.e3dc.macAddress
        self._mydata["model"] = self.e3dc.model
        self._mydata[
            "system-battery-discharge-minimum-default"
        ] = self.e3dc.startDischargeDefault

        # Idea: Maybe Port this to e3dc lib, it can query this in one go during startup.
        self._sw_version = await self._async_e3dc_request_single_tag(
            "INFO_REQ_SW_RELEASE"
        )

        await self._load_timezone_settings()

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

        _LOGGER.debug("Polling manual charge information")
        request_data = await self.hass.async_add_executor_job(
            self.e3dc.sendRequest, ("EMS_REQ_GET_MANUAL_CHARGE", "None", None), 3, True
        )
        self._process_manual_charge(request_data)

        # Only poll power statstics once per minute. E3DC updates it only once per 15
        # minutes anyway, this should be a good compromise to get the metrics shortly
        # before the end of the day.
        if self._next_stat_update < time():
            _LOGGER.debug("Polling today's power metrics")
            db_data_today: dict[str, Any] = await self.hass.async_add_executor_job(
                self.e3dc.get_db_data_timestamp,
                self._get_db_data_day_timestamp(),
                86400,
                True,
            )
            self._process_db_data_today(db_data_today)
            self._next_stat_update = time() + _STAT_REFRESH_INTERVAL
            # TODO: Reduce interval further, but take start_ts into account to get an
            # end of day reading of the metric.
        else:
            _LOGGER.debug("Skipping power metrics poll.")

        return self._mydata

    def _process_power_settings(self, power_settings: dict[str, Any | None]):
        """Process retrieved power settings."""
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

    def _process_poll(self, poll_data: dict[str, Any]):
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

    def _process_db_data_today(self, db_data: dict[str, Any | None]) -> None:
        """Process retrieved db data settings."""
        self._mydata["db-day-autarky"] = db_data["autarky"]
        self._mydata["db-day-battery-charge"] = db_data["bat_power_in"]
        self._mydata["db-day-battery-discharge"] = db_data["bat_power_out"]
        self._mydata["db-day-grid-consumption"] = db_data["grid_power_out"]
        self._mydata["db-day-grid-production"] = db_data["grid_power_in"]
        self._mydata["db-day-house-consumption"] = db_data["consumption"]
        self._mydata["db-day-selfconsumption"] = db_data["consumed_production"]
        self._mydata["db-day-solar-production"] = db_data["solarProduction"]
        self._mydata["db-day-startts"] = db_data["startTimestamp"]

    def _process_manual_charge(self, request_data) -> None:
        """Parse manual charge status"""
        self._mydata["manual-charge-active"] = rscpFindTag(
            request_data, "EMS_MANUAL_CHARGE_ACTIVE"
        )[2]
        self._mydata["manual-charge-energy"] = rscpFindTag(
            request_data, "EMS_MANUAL_CHARGE_ENERGY_COUNTER"
        )[2]

    async def _load_timezone_settings(self):
        """Load the current timezone offset from the E3DC, using its local timezone data.

        Required to correctly retrieve power statistics for today.
        """
        try:
            tz_name: str = await self._async_e3dc_request_single_tag(
                "INFO_REQ_TIME_ZONE"
            )
        except:
            _LOGGER.exception("Failed to loade timezone from E3DC")
            # Once we have better exception handling available, we need to throw
            # proper HomeAssistantErrors at this point.
            raise

        tz_offset: int | None = None
        try:
            tz_info: pytz.timezone = pytz.timezone(tz_name)
            dt_tmp: datetime = datetime.now(tz_info)
            tz_offset = dt_tmp.utcoffset().seconds
        except pytz.UnknownTimeZoneError:
            _LOGGER.exception("Failed to load timezone from E3DC")

        if tz_offset is None:
            try:
                # Fallback to compute the offset using current times from E3DC:
                ts_local: int = int(
                    await self._async_e3dc_request_single_tag("INFO_REQ_TIME")
                )
                ts_utc: int = int(
                    await self._async_e3dc_request_single_tag("INFO_REQ_UTC_TIME")
                )
                delta: int = ts_local - ts_utc
                tz_offset = int(1800 * round(delta / 1800))
            except:
                _LOGGER.exception("Failed to load timestamps from E3DC")
                # Once we have better exception handling available, we need to throw
                # proper HomeAssistantErrors at this point.
                raise

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
        _LOGGER.debug(
            "Midnight DB query timestamp is %s, applied offset: %s",
            today_ts,
            self._timezone_offset,
        )
        return today_ts

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
        self._mydata["pset-weatherregulationenabled"] = enabled

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
            self._mydata["pset-weatherregulationenabled"] = new_value
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
        self._mydata["pset-powersaving-enabled"] = enabled

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
            self._mydata["pset-powersaving-enabled"] = new_value
        finally:
            self._update_guard_powersettings = False

        if new_value != enabled:
            raise HomeAssistantError(f"Failed to update powersaving to {enabled}")

        _LOGGER.debug("Successfully updated powersaving to %s", enabled)
        return True

    async def async_clear_power_limits(self) -> None:
        """Clear any active power limit."""

        _LOGGER.debug("Clearing any active power limit.")

        try:
            # Call RSCP service.
            # no update guard necessary, as we're called from a service, not an entity
            result: int = await self.hass.async_add_executor_job(
                self.e3dc.set_power_limits, False, None, None, None, True
            )
        except Exception as ex:
            _LOGGER.exception("Failed to clear power limits")
            raise HomeAssistantError("Failed to clear power limits") from ex

        if result == -1:
            raise HomeAssistantError("Failed to clear power limits")

        if result == 1:
            _LOGGER.warning("The given power limits are not optimal, continuing anyway")
        else:
            _LOGGER.debug("Successfully cleared the power limits")

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

        if max_charge is not None and max_charge > self.e3dc.maxBatChargePower:
            _LOGGER.warning("Limiting max_charge to %s", self.e3dc.maxBatChargePower)
            max_charge = self.e3dc.maxBatChargePower
        if max_discharge is not None and max_discharge > self.e3dc.maxBatDischargePower:
            _LOGGER.warning(
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
            _LOGGER.exception("Failed to set power limits")
            raise HomeAssistantError("Failed to set power limits") from ex

        if result == -1:
            raise HomeAssistantError("Failed to set power limits")

        if result == 1:
            _LOGGER.warning("The given power limits are not optimal, continuing anyway")
        else:
            _LOGGER.debug("Successfully set the power limits")

    async def async_manual_charge(self, charge_amount: int) -> None:
        """Start manual charging the given amount, zero will stop charging."""

        # Validate the arguments
        if charge_amount < 0:
            raise ValueError("Charge amount must be positive or zero.")

        _LOGGER.debug(
            "Starting manual charge of: %s",
            charge_amount,
        )

        try:
            # Call RSCP service.
            # no update guard necessary, as we're called from a service, not an entity
            result_data = await self.hass.async_add_executor_job(
                self.e3dc.sendRequest,
                ("EMS_REQ_START_MANUAL_CHARGE", "Uint32", charge_amount),
                3,
                True,
            )
        except Exception as ex:
            _LOGGER.exception("Failed to initiate manual charging")
            raise HomeAssistantError("Failed to initiate manual charging") from ex

        result: bool = result_data[2]

        if not result:
            _LOGGER.warning("Manual charging could not be activated")
        else:
            _LOGGER.debug("Successfully started manual charging")


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
