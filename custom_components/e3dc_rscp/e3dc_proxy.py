"""Diagnostics support for E3DC RSCP."""
from __future__ import annotations

from functools import wraps
import logging
from typing import Any

from e3dc import E3DC, SendError, NotAvailableError, RSCPKeyError, AuthenticationError
from e3dc._rscpLib import rscpFindTag, rscpFindTagIndex
from e3dc._rscpTags import RscpTag, RscpType, PowermeterType

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError

from .const import CONF_RSCPKEY

_LOGGER = logging.getLogger(__name__)


def e3dc_call(func):
    """Wrap e3dc call in boilerplate exception handling."""

    @wraps(func)
    def wrapper_handle_e3dc_ex(*args, **kwargs) -> Any:
        """Send a call to E3DC asynchronusly and do general exception handling."""
        try:
            return func(*args, **kwargs)
        except NotAvailableError as ex:
            _LOGGER.debug("E3DC is unavailable: %s", ex, exc_info=True)
            raise HomeAssistantError(
                "Communication Failure: E3DC mot available"
            ) from ex
        except SendError as ex:
            _LOGGER.debug("Communication error with E3DC: %s", ex, exc_info=True)
            raise HomeAssistantError(
                "Communication Failure: Failed to send data"
            ) from ex
        except AuthenticationError as ex:
            _LOGGER.debug("Failed to authenticate with E3DC: %s", ex, exc_info=True)
            raise ConfigEntryAuthFailed("Failed to authenticate with E3DC") from ex
        except RSCPKeyError as ex:
            _LOGGER.debug("Encryption error with E3DC, key invalid: %s", ex, exc_info=True)
            raise ConfigEntryAuthFailed(
                "Encryption Error with E3DC, key invalid"
            ) from ex
        except (HomeAssistantError, ConfigEntryAuthFailed):
            raise
        except Exception as ex:
            _LOGGER.debug("Fatal error when talking to E3DC: %s", ex, exc_info=True)
            raise HomeAssistantError("Fatal error when talking to E3DC") from ex

    return wrapper_handle_e3dc_ex


class E3DCProxy:
    """Proxies requests to pye3dc, takes care of error and async handling."""

    def __init__(self, _hass: HomeAssistant, _config: ConfigEntry | dict[str, str]):
        """Initialize E3DC Proxy and connect."""
        # TODO: move to readonly properties
        self.e3dc: E3DC = None
        self.e3dc_config: dict[str, Any] = {}
        self._hass: HomeAssistant = _hass
        self._config: ConfigEntry = _config
        self._host: str
        self._username: str
        self._password: str
        self._rscpkey: str

        if isinstance(_config, ConfigEntry):
            self._host = self._config.data.get(CONF_HOST)
            self._username = self._config.data.get(CONF_USERNAME)
            self._password = self._config.data.get(CONF_PASSWORD)
            self._rscpkey = self._config.data.get(CONF_RSCPKEY)
        else:
            self._host = _config[CONF_HOST]
            self._username = _config[CONF_USERNAME]
            self._password = _config[CONF_PASSWORD]
            self._rscpkey = _config[CONF_RSCPKEY]

    @e3dc_call
    def connect(self, config: dict[str, Any] | None = None):
        """Connect to E3DC with an optional device setup."""
        if config is None:
            config = {}

        self.e3dc = E3DC(
            E3DC.CONNECT_LOCAL,
            username=self._username,
            password=self._password,
            ipAddress=self._host,
            key=self._rscpkey,
            configuration=config,
        )

        self.e3dc_config = config

    @e3dc_call
    def disconnect(self):
        """Disconnect from E3DC if connected."""
        if self.e3dc is None:
            return
        if self.e3dc.rscp.isConnected():
            self.e3dc.disconnect()
        self.e3dc = None

    @e3dc_call
    def get_db_data(self, timestamp: int, timespan_seconds: int) -> dict[str, Any]:
        """Return the statics data for the specified timespan."""
        return self.e3dc.get_db_data_timestamp(timestamp, timespan_seconds, True)

    @e3dc_call
    def get_manual_charge(self) -> dict[str, Any]:
        """Poll manual charging state."""
        try:
            data = self.e3dc.sendRequest(
                (RscpTag.EMS_REQ_GET_MANUAL_CHARGE, RscpType.NoneType, None), keepAlive=True
            )

            result: dict[str, Any] = {}
            result["active"] = rscpFindTag(data, RscpTag.EMS_MANUAL_CHARGE_ACTIVE)[2]

            # These seem to be kAh per individual cell, so this is considered very strange.
            # To get this working for a start, we assume 3,65 V per cell, taking my own unit
            # as a base, but this obviously will need some real work to base this on
            # current voltages.
            # Round to Watts, this should prevent negative values in the magnitude of 10^-6,
            # which are probably floating point errors.
            tmp = rscpFindTag(data, RscpTag.EMS_MANUAL_CHARGE_ENERGY_COUNTER)[2]
            powerfactor = 3.65
            result["energy"] = round(tmp * powerfactor, 3)

            # The timestamp seem to correctly show the UTC Date when manual charging started
            # Not yet enabled, just for reference.
            # self._mydata["manual-charge-start"] = rscpFindTag(
            #     request_data, "EMS_MANUAL_CHARGE_LASTSTART"
            # )[2]
        except SendError:
            _LOGGER.debug("Failed to query manual charging data, might be related to a recent E3DC API change, ignoring the error, reverting to empty defaults.")
            result: dict[str, Any] = {}
            result["active"] = False
            result["energy"] = 0

        return result

    @e3dc_call
    def get_power_settings(self) -> dict[str, Any]:
        """Retrieve current power settings."""
        return self.e3dc.get_power_settings(keepAlive=True)

    @e3dc_call
    def get_powermeters(self) -> dict[str, Any]:
        """Load available powermeters from E3DC."""
        return self.e3dc.get_powermeters(keepAlive=True)

    @e3dc_call
    def get_wallbox_data(self, wallbox_index: int) -> dict[str, Any]:
        """Poll current wallbox readings."""
        return self.e3dc.get_wallbox_data(wbIndex=wallbox_index, keepAlive=True)

    @e3dc_call
    def get_wallbox_identification_data(self, wallbox_index: int) -> dict[str, Any]:
        """Get identification data for wallbox with given index."""
        req = self.e3dc.sendRequest(
            (
                "WB_REQ_DATA",
                "Container",
                [
                    ("WB_INDEX", "UChar8", wallbox_index),
                    ("WB_REQ_FIRMWARE_VERSION", "None", None),
                    ("WB_REQ_MAC_ADDRESS", "None", None),
                    ("WB_REQ_DEVICE_NAME", "None", None),
                    ("WB_REQ_SERIAL", "None", None),
                    ("WB_REQ_WALLBOX_TYPE", "None", None),
                    ("WB_REQ_LOWER_CURRENT_LIMIT", "None", None),
                    ("WB_REQ_UPPER_CURRENT_LIMIT", "None", None)
                ],
            ),
            keepAlive=True,
        )

        outObj = {
            "index": rscpFindTagIndex(req, "WB_INDEX"),
        }

        firmware_version = rscpFindTag(req, "WB_FIRMWARE_VERSION")
        if firmware_version is not None:
            outObj["firmwareVersion"] = rscpFindTagIndex(firmware_version, "WB_FIRMWARE_VERSION")

        device_name = rscpFindTag(req, "WB_DEVICE_NAME")
        if device_name is not None:
            outObj["deviceName"] = rscpFindTagIndex(device_name, "WB_DEVICE_NAME")

        wallbox_serial = rscpFindTag(req, "WB_SERIAL")
        if wallbox_serial is not None:
            outObj["wallboxSerial"] = rscpFindTagIndex(wallbox_serial, "WB_SERIAL")

        mac_address = rscpFindTag(req, "WB_MAC_ADDRESS")
        if mac_address is not None:
            outObj["macAddress"] = rscpFindTagIndex(mac_address, "WB_MAC_ADDRESS")

        wallbox_type = rscpFindTag(req, "WB_WALLBOX_TYPE")
        if wallbox_type is not None:
            outObj["wallboxType"] = rscpFindTagIndex(wallbox_type, "WB_WALLBOX_TYPE")

        lower_current_limit = rscpFindTag(req, "WB_LOWER_CURRENT_LIMIT")
        if lower_current_limit is not None:
            outObj["lowerCurrentLimit"] = rscpFindTagIndex(lower_current_limit, "WB_LOWER_CURRENT_LIMIT")

        upper_current_limit = rscpFindTag(req, "WB_UPPER_CURRENT_LIMIT")
        if upper_current_limit is not None:
            outObj["upperCurrentLimit"] = rscpFindTagIndex(upper_current_limit, "WB_UPPER_CURRENT_LIMIT")

        return outObj


    @e3dc_call
    def get_powermeters_data(self) -> dict[str, Any]:
        """Poll all powermeters for their current readings."""
        data = self.e3dc.get_powermeters_data(keepAlive=True)
        result: dict[str, Any] = {}

        # Process and aggregate the data for each found powermeter
        for meter in data:
            # skip the root powermeter
            if meter["type"] == PowermeterType.PM_TYPE_ROOT.value:
                continue

            # TODO: Rewrite the config so that we can index into it.
            for config in self.e3dc_config["powermeters"]:
                if meter["index"] != config["index"]:
                    continue

                result[config["key"]] = (
                    meter["power"]["L1"] + meter["power"]["L2"] + meter["power"]["L3"]
                )

                # TODO: Store the total key in the config as well.
                result[config["key"] + "-total"] = (
                    meter["energy"]["L1"]
                    + meter["energy"]["L2"]
                    + meter["energy"]["L3"]
                )

                if config["negate-measure"]:
                    result[config["key"]] *= -1
                    result[config["key"] + "-total"] *= -1

        return result

    @e3dc_call
    def get_software_version(self) -> str:
        """Return the current software version of the E3DC."""
        return self.e3dc.sendRequestTag(RscpTag.INFO_REQ_SW_RELEASE, keepAlive=True)

    @e3dc_call
    def get_time(self) -> int:
        """Get current local timestamp."""
        return self.e3dc.sendRequestTag(RscpTag.INFO_REQ_TIME, keepAlive=True)

    @e3dc_call
    def get_timeutc(self) -> int:
        """Get current local timestamp."""
        return self.e3dc.sendRequestTag(RscpTag.INFO_REQ_UTC_TIME, keepAlive=True)

    @e3dc_call
    def get_timezone(self) -> str:
        """Load the E3DC Timezone."""
        return self.e3dc.sendRequestTag(RscpTag.INFO_REQ_TIME_ZONE, keepAlive=True)

    @e3dc_call
    def poll(self) -> dict[str, Any]:
        """Poll E3DC current state."""
        return self.e3dc.poll(keepAlive=True)

    @e3dc_call
    def start_manual_charge(self, charge_amount_wh: int) -> None:
        """Initiate the manual charging process, zero will stop charging."""
        result_data = self.e3dc.sendRequest(
            (RscpTag.EMS_REQ_START_MANUAL_CHARGE, RscpType.Uint32, charge_amount_wh),
            keepAlive=True,
        )
        result: bool = result_data[2]

        if not result:
            _LOGGER.warning("Manual charging could not be activated")

    @e3dc_call
    def set_wallbox_sun_mode(self, enabled: bool, wallbox_index: int):
        """Set wallbox charging mode to sun mode on/off.

        Args:
            enabled(bool): the desired state True = sun mode enabled, False = sun mode disabled
            wallbox_index (Optional[int]): index of the requested wallbox,

        Returns:
            nothing

        """
        result: bool = self.e3dc.set_wallbox_sunmode(enable=enabled, wbIndex=wallbox_index, keepAlive=True)
        if not result:
            raise HomeAssistantError("Failed to set wallbox to sun mode %s", enabled)

    @e3dc_call
    def set_wallbox_schuko(self, enabled: bool, wallbox_index: int):
        """Set wallbox power outlet (schuko) to on/off.

        Args:
            enabled(bool): the desired state True = on, False = off
            wallbox_index (Optional[int]): index of the requested wallbox,

        Returns:
            nothing

        """
        result: bool = self.e3dc.set_wallbox_schuko(enable=enabled, wbIndex=wallbox_index, keepAlive=True)
        if not result:
            raise HomeAssistantError("Failed to set wallbox schuko to %s", enabled)

    @e3dc_call
    def toggle_wallbox_charging(self, wallbox_index: int):
        """Toggle charging of the wallbox.

        Args:
            wallbox_index (Optional[int]): index of the requested wallbox,

        Returns:
            nothing

        """
        result: bool = self.e3dc.toggle_wallbox_charging(wbIndex=wallbox_index, keepAlive=True)
        if not result:
            raise HomeAssistantError("Failed to toggle wallbox charging")

    @e3dc_call
    def toggle_wallbox_phases(self, wallbox_index: int):
        """Toggle the phases of wallbox charging between 1 and 3 phases.

           Only works if "Phasen" in the portal/device is not set to Auto.

        Args:
            wallbox_index (Optional[int]): index of the requested wallbox,

        Returns:
            nothing

        """
        result: bool = self.e3dc.toggle_wallbox_phases(wbIndex=wallbox_index, keepAlive=True)
        if not result:
            raise HomeAssistantError("Failed to toggle wallbox phases")

    @e3dc_call
    def set_wallbox_max_charge_current(
        self, max_charge_current: int, wallbox_index: int
    ) -> bool:
        """Set the maximum charge current of the wallbox via RSCP protocol locally.

        Args:
            max_charge_current (int): maximum allowed charge current in A
            wallbox_index (Optional[int]): index of the requested wallbox

        Returns:
            True if success (wallbox has understood the request, but might have clipped the value)
            False if error

        """
        _LOGGER.debug("Wallbox %s: Setting max_charge_current to %s", wallbox_index, max_charge_current)

        return self.e3dc.set_wallbox_max_charge_current(
            max_charge_current=max_charge_current, wbIndex=wallbox_index, keepAlive=True
        )

    @e3dc_call
    def set_power_limits(
        self,
        enable: bool,
        max_charge: int | None = None,
        max_discharge: int | None = None,
        discharge_start: int | None = None,
    ) -> None:
        """Set or clear power limits."""
        result: int = self.e3dc.set_power_limits(
            enable, max_charge, max_discharge, discharge_start, True
        )

        if result == -1:
            raise HomeAssistantError("Failed to clear power limits")
        if result == 1:
            _LOGGER.warning("The given power limits are not optimal, continuing anyway")

    @e3dc_call
    def set_powersave(self, enabled: bool):
        """Set powersaving flag."""
        # The call would normally return the new state, however, various e3dc's
        # react differently here, my E3DC does not work as the way e3dc lib is
        # implemented, so so far we ignore the return value. If the change was
        # unsuccessful, the next polling cycle will reset this to the actual
        # value.
        # TODO: Find a way to deal with the powersaving api
        self.e3dc.set_powersave(enabled, True)

    @e3dc_call
    def set_weather_regulated_charge(self, enabled: bool):
        """Set weather regulated charging flag."""
        # The call would normally return the new state, however, various e3dc's
        # react differently here, my E3DC does not work as the way e3dc lib is
        # implemented, so so far we ignore the return value. If the change was
        # unsuccessful, the next polling cycle will reset this to the actual
        # value.
        # TODO: Find a way to deal with the weather regulation api
        self.e3dc.set_weather_regulated_charge(enabled, True)
