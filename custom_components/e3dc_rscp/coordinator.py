"""Coordinator for E3DC integration."""

from datetime import timedelta, datetime, date
import logging
from time import time
from typing import Any, TypedDict
import pytz
import re

from e3dc._rscpTags import PowermeterType

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback, Event
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util.dt import as_timestamp, start_of_local_day
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.components.sensor import SensorStateClass
from homeassistant.util.event_type import EventType

from .const import (
    CONF_CREATE_BATTERY_DEVICES,
    DEFAULT_CREATE_BATTERY_DEVICES,
    DOMAIN,
    MAX_WALLBOXES_POSSIBLE,
    CONF_CREATE_BATTERY_DIAGNOSTIC_SENSORS,
    DEFAULT_CREATE_BATTERY_DIAGNOSTIC_SENSORS,
    BATTERY_MODULE_SENSORS,
    BATTERY_PACK_SENSORS,
    PowerMode,
    SetPowerMode,
)

from .e3dc_proxy import E3DCProxy

_LOGGER = logging.getLogger(__name__)
_STAT_REFRESH_INTERVAL = 60


class E3DCWallbox(TypedDict):
    """E3DC Wallbox, keeps general information, attributes and identity data for an individual wallbox."""

    index: int
    key: str
    deviceInfo: DeviceInfo
    lowerCurrentLimit: int
    upperCurrentLimit: int


class E3DCBattery(TypedDict):
    """E3DC Battery module, keeps module index, identifier and device info."""

    pack_index: int
    dcb_index: int
    key: str
    deviceInfo: DeviceInfo


class E3DCBatteryPack(TypedDict):
    """E3DC Battery pack metadata used for diagnostic sensors."""

    index: int
    key: str
    name: str


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
        self.config_entry: ConfigEntry = config_entry
        self._wallboxes: list[E3DCWallbox] = []
        self._batteries: list[E3DCBattery] = []
        self._battery_packs: list[E3DCBatteryPack] = []
        self._timezone_offset: int = 0
        self._next_stat_update: float = 0

        self._stop_set_power_mode: callback = None
        hass.bus.async_listen_once(
            EventType("homeassistant_stop"), self._shutdown_power_mode
        )

        self._mydata["set-power-mode"] = SetPowerMode.NORMAL.value
        self._mydata["set-power-value"] = None

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
        self._mydata["system-battery-installed-capacity"] = (
            self.proxy.e3dc.installedBatteryCapacity
        )
        self._mydata["system-battery-installed-peak"] = (
            self.proxy.e3dc.installedPeakPower
        )
        self._mydata["system-ac-maxpower"] = self.proxy.e3dc.maxAcPower
        self._mydata["system-battery-charge-max"] = self.proxy.e3dc.maxBatChargePower
        self._mydata["system-battery-discharge-max"] = (
            self.proxy.e3dc.maxBatDischargePower
        )
        self._mydata["system-mac"] = self.proxy.e3dc.macAddress
        self._mydata["model"] = self.proxy.e3dc.model
        self._mydata["system-battery-discharge-minimum-default"] = (
            self.proxy.e3dc.startDischargeDefault
        )

        # Idea: Maybe Port this to e3dc lib, it can query this in one go during startup.
        self._sw_version = await self.hass.async_add_executor_job(
            self.proxy.get_software_version
        )

        await self._load_timezone_settings()

    async def async_identify_wallboxes(self, hass: HomeAssistant):
        """Identify availability of Wallboxes if get_wallbox_identification_data() returns meaningful data."""

        for wallbox_index in range(0, MAX_WALLBOXES_POSSIBLE - 1):
            try:
                request_data: dict[str, Any] = await self.hass.async_add_executor_job(
                    self.proxy.get_wallbox_identification_data, wallbox_index
                )
            except HomeAssistantError as ex:
                _LOGGER.warning(
                    "Failed to load wallbox with index %s, not updating data: %s",
                    wallbox_index,
                    ex,
                )
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
                    connections={
                        (
                            dr.CONNECTION_NETWORK_MAC,
                            dr.format_mac(request_data["macAddress"]),
                        )
                    },
                    configuration_url="https://my.e3dc.com/",
                )

                wallbox: E3DCWallbox = {
                    "index": wallbox_index,
                    "key": unique_id,
                    "deviceInfo": deviceInfo,
                    "lowerCurrentLimit": request_data["lowerCurrentLimit"],
                    "upperCurrentLimit": request_data["upperCurrentLimit"],
                }
                self.wallboxes.append(wallbox)
            else:
                _LOGGER.debug("No Wallbox with index %s has been found", wallbox_index)

    # Getter for _wallboxes
    @property
    def wallboxes(self) -> list[E3DCWallbox]:
        """Get the list of wallboxes."""
        return self._wallboxes

    @property
    def create_battery_devices(self) -> bool:
        """Flag indicating if battery devices should be created."""
        return self.config_entry.options.get(
            CONF_CREATE_BATTERY_DEVICES, DEFAULT_CREATE_BATTERY_DEVICES
        )

    @property
    def batteries(self) -> list[E3DCBattery]:
        """Get the list of identified battery modules."""
        return self._batteries

    @property
    def battery_packs(self) -> list[E3DCBatteryPack]:
        """Get the list of battery packs for diagnostic sensors."""
        return self._battery_packs

    async def _async_clear_battery_devices(self) -> None:
        """Remove any previously created battery devices."""
        device_registry = dr.async_get(self.hass)
        battery_prefix = f"{self.uid}-battery-"
        devices_to_remove: list[str] = []

        for entry in device_registry.devices.values():
            if any(
                identifier[0] == DOMAIN and identifier[1].startswith(battery_prefix)
                for identifier in entry.identifiers
            ):
                devices_to_remove.append(entry.id)

        for device_id in devices_to_remove:
            device_registry.async_remove_device(device_id)

        self._batteries.clear()
        battery_key_prefix = "battery-"
        for key in list(self._mydata.keys()):
            if key.startswith("battery-pack-"):
                continue
            if key.startswith(battery_key_prefix):
                self._mydata.pop(key)

    def _clear_battery_diagnostic_data(self) -> None:
        """Clear previously stored diagnostic battery sensor data."""
        pack_prefix = "battery-pack-"
        for key in list(self._mydata.keys()):
            if key.startswith(pack_prefix):
                self._mydata.pop(key)
        self._battery_packs.clear()

    async def async_identify_batteries(self, hass: HomeAssistant) -> None:
        """Identify installed battery modules if enabled via options."""
        if not self.create_battery_devices:
            _LOGGER.debug("Battery devices disabled via options, skipping identification")
            await self._async_clear_battery_devices()
            return

        try:
            batteries_config: list[dict[str, Any]] = await self.hass.async_add_executor_job(
                self.proxy.get_batteries
            )
        except HomeAssistantError as ex:
            _LOGGER.warning(
                "Failed to load battery configuration, skipping battery devices: %s", ex
            )
            return

        try:
            battery_data: Any = await self.hass.async_add_executor_job(
                self.proxy.get_battery_data
            )
        except HomeAssistantError as ex:
            _LOGGER.warning(
                "Failed to load battery data, continuing with limited information: %s", ex
            )
            battery_data = None

        if not isinstance(batteries_config, list):
            _LOGGER.debug("Battery configuration returned unexpected payload: %s", batteries_config)
            batteries_config = []

        battery_details_by_pack: dict[int, dict[str, Any]] = {}
        if isinstance(battery_data, list):
            for pack in battery_data:
                if isinstance(pack, dict) and "index" in pack:
                    battery_details_by_pack[pack["index"]] = pack
        elif isinstance(battery_data, dict):
            pack_index = battery_data.get("index", 0)
            battery_details_by_pack[pack_index] = battery_data

        def _normalize(value: Any) -> Any:
            if isinstance(value, str):
                stripped = value.strip()
                if stripped == "" or stripped.upper() == "TODO":
                    return None
            return value

        self._batteries.clear()

        for battery_config in batteries_config or []:
            pack_index = battery_config.get("index", 0)
            dcb_count = battery_config.get("dcbs", 0)
            pack_details = battery_details_by_pack.get(pack_index, {})
            dcbs_details: dict[int, dict[str, Any]] = {}
            if isinstance(pack_details, dict):
                dcbs = pack_details.get("dcbs")
                if isinstance(dcbs, dict):
                    dcbs_details = dcbs

            for dcb_index in range(dcb_count):
                battery_key = f"battery-{pack_index}-{dcb_index}"
                unique_id = f"{self.uid}-{battery_key}"
                dcb_detail = dcbs_details.get(dcb_index, {}) if isinstance(dcbs_details, dict) else {}

                manufacturer = _normalize(dcb_detail.get("manufactureName")) or "E3DC"
                model = _normalize(dcb_detail.get("deviceName")) or _normalize(pack_details.get("deviceName")) or "Battery Module"
                default_name = f"Battery {pack_index + 1} Module {dcb_index + 1}"
                name = _normalize(dcb_detail.get("deviceName")) or default_name
                serial = _normalize(dcb_detail.get("serialCode")) or _normalize(dcb_detail.get("serialNo"))
                fw_version = _normalize(dcb_detail.get("fwVersion"))
                pcb_version = _normalize(dcb_detail.get("pcbVersion"))

                device_info = DeviceInfo(
                    identifiers={(DOMAIN, unique_id)},
                    via_device=(DOMAIN, self.uid),
                    manufacturer=manufacturer,
                    name=name,
                    model=model,
                    configuration_url="https://my.e3dc.com/",
                )

                if serial is not None:
                    device_info["serial_number"] = str(serial)
                if fw_version is not None:
                    device_info["sw_version"] = str(fw_version)
                if pcb_version is not None:
                    device_info["hw_version"] = str(pcb_version)

                battery_entry: E3DCBattery = {
                    "pack_index": pack_index,
                    "dcb_index": dcb_index,
                    "key": battery_key,
                    "deviceInfo": device_info,
                }
                self._batteries.append(battery_entry)

        if len(self._batteries) > 0:
            await self._load_and_process_battery_data(battery_data)

        if len(self._batteries) == 0:
            _LOGGER.debug("No battery modules were identified")
        else:
            _LOGGER.debug("Identified %s battery modules", len(self._batteries))

    @property
    def create_battery_diagnostic_sensors(self) -> bool:
        """Flag indicating if diagnostic battery sensors should be created."""
        return self.config_entry.options.get(
            CONF_CREATE_BATTERY_DIAGNOSTIC_SENSORS,
            DEFAULT_CREATE_BATTERY_DIAGNOSTIC_SENSORS,
        )

    # Setter for individual wallbox values
    def setWallboxValue(self, index: int, key: str, value: Any) -> None:
        """Set the value for a specific key in a wallbox identified by its index."""
        for wallbox in self._wallboxes:
            if wallbox["index"] == index:
                wallbox[key] = value
                _LOGGER.debug(f"Set {key} to {value} for wallbox with index {index}")
                return
        raise ValueError(f"Wallbox with index {index} not found")

    # Getter for individual wallbox values
    def getWallboxValue(self, index: int, key: str) -> Any:
        """Get the value for a specific key in a wallbox identified by its index."""
        for wallbox in self._wallboxes:
            if wallbox["index"] == index:
                value = wallbox.get(key)
                if value is not None:
                    _LOGGER.debug(
                        f"Got {key} value {value} for wallbox with index {index}"
                    )
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
                    case (
                        PowermeterType.PM_TYPE_ADDITIONAL_PRODUCTION.value
                        | PowermeterType.PM_TYPE_ADDITIONAL.value
                    ):
                        powermeter["total-state-class"] = (
                            SensorStateClass.TOTAL_INCREASING
                        )
                        powermeter["negate-measure"] = True

                    case PowermeterType.PM_TYPE_ADDITIONAL_CONSUMPTION.value:
                        powermeter["total-state-class"] = (
                            SensorStateClass.TOTAL_INCREASING
                        )
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

        if self.create_battery_devices or self.create_battery_diagnostic_sensors:
            _LOGGER.debug("Polling battery data")
            await self._load_and_process_battery_data()
        else:
            self._clear_battery_diagnostic_data()

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
            power_settings: dict[str, Any] = await self.hass.async_add_executor_job(
                self.proxy.get_power_settings
            )
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
            poll_data: dict[str, Any] = await self.hass.async_add_executor_job(
                self.proxy.poll
            )
            power_mode_job = self.hass.async_add_executor_job(self.proxy.get_power_mode)
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

        power_mode: str = str(await power_mode_job)
        if PowerMode.has_value(power_mode):
            self._mydata["power-mode"] = power_mode
        else:
            _LOGGER.debug("Unknown power mode %s", power_mode)
            self._mydata["power-mode"] = f"Power mode {power_mode}"

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
            request_data: dict[str, Any] = await self.hass.async_add_executor_job(
                self.proxy.get_manual_charge
            )
        except HomeAssistantError as ex:
            _LOGGER.warning(
                "Failed to load manual charge state, not updating data: %s", ex
            )
            return

        self._mydata["manual-charge-active"] = request_data["active"]
        self._mydata["manual-charge-energy"] = request_data["energy"]

    async def _load_and_process_powermeters_data(self) -> None:
        """Load and process additional sources to existing data."""
        try:
            request_data: dict[str, Any] = await self.hass.async_add_executor_job(
                self.proxy.get_powermeters_data
            )
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
                formatted_key = re.sub(
                    r"(?<!^)(?=[A-Z])", "-", key
                ).lower()  # RegEx to convert from CamelCase to kebab-case
                if formatted_key == "plug-locked":
                    formatted_key = "plug-lock"
                    value = (
                        not value
                    )  # Inverse to match HA's Lock On/Off interpretation
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

    async def _load_and_process_battery_data(self, battery_data: Any | None = None) -> None:
        """Load and process battery module data."""
        data: Any | None = battery_data
        if data is None:
            try:
                data = await self.hass.async_add_executor_job(
                    self.proxy.get_battery_data
                )
            except HomeAssistantError as ex:
                _LOGGER.warning("Failed to load battery data, not updating sensors: %s", ex)
                return

        pack_map: dict[int, dict[str, Any]] = {}
        if isinstance(data, list):
            for pack in data:
                if isinstance(pack, dict) and "index" in pack:
                    pack_map[pack["index"]] = pack
        elif isinstance(data, dict):
            pack_index = data.get("index", 0)
            pack_map[pack_index] = data

        if self.create_battery_diagnostic_sensors:
            self._update_battery_pack_data(pack_map)
        else:
            self._clear_battery_diagnostic_data()

        for battery in self.batteries:
            pack = pack_map.get(battery["pack_index"], {})
            dcb_data: dict[str, Any] | None = None
            if isinstance(pack, dict):
                dcbs = pack.get("dcbs")
                if isinstance(dcbs, dict):
                    dcb_data = dcbs.get(battery["dcb_index"])

            if not isinstance(dcb_data, dict):
                for _, slug in BATTERY_MODULE_SENSORS:
                    self._mydata[f"{battery['key']}-{slug}"] = None
                continue

            for data_key, slug in BATTERY_MODULE_SENSORS:
                raw_value: Any = dcb_data.get(data_key)
                if isinstance(raw_value, list | dict | set | tuple):
                    continue

                processed_value: Any = self._process_battery_sensor_value(
                    data_key, raw_value
                )
                self._mydata[f"{battery['key']}-{slug}"] = processed_value

    def _update_battery_pack_data(self, pack_map: dict[int, dict[str, Any]]) -> None:
        """Update diagnostic sensor data for battery packs."""
        existing_keys = {key for key in self._mydata if key.startswith("battery-pack-")}
        new_keys: set[str] = set()
        self._battery_packs.clear()

        for pack_index in sorted(pack_map.keys()):
            pack = pack_map[pack_index]
            pack_key = f"battery-pack-{pack_index}"
            pack_name_raw = pack.get("deviceName")
            pack_name_processed = self._process_battery_sensor_value(
                "deviceName", pack_name_raw
            )
            pack_name = (
                str(pack_name_processed)
                if pack_name_processed is not None
                else f"Battery Pack {pack_index + 1}"
            )
            self._battery_packs.append(
                {"index": pack_index, "key": pack_key, "name": pack_name}
            )

            for data_key, slug in BATTERY_PACK_SENSORS:
                full_key = f"{pack_key}-{slug}"
                new_keys.add(full_key)

                if data_key is None:
                    value = self._calculate_battery_pack_value(slug, pack)
                else:
                    raw_value = pack.get(data_key)
                    if isinstance(raw_value, list | dict | set | tuple):
                        value = None
                    else:
                        value = raw_value

                processed_value = self._process_battery_sensor_value(
                    data_key or slug, value
                )
                self._mydata[full_key] = processed_value

        for stale_key in existing_keys - new_keys:
            self._mydata.pop(stale_key, None)

    def _calculate_battery_pack_value(self, slug: str, pack: dict[str, Any]) -> Any:
        """Calculate derived battery pack values."""
        if slug == "state-of-health":
            design_capacity = pack.get("designCapacity")
            full_charge_capacity = pack.get("fcc")
            try:
                design_capacity_float = float(design_capacity)
                full_charge_capacity_float = float(full_charge_capacity)
            except (TypeError, ValueError):
                return None

            if design_capacity_float <= 0:
                return None

            return (full_charge_capacity_float / design_capacity_float) * 100

        return pack.get(slug)

    def _process_battery_sensor_value(self, data_key: str, value: Any) -> Any:
        """Process individual battery sensor values before storing."""
        if value is None:
            return None

        if data_key == "manufactureDate":
            try:
                value_int: int = int(value)
            except (TypeError, ValueError):
                return None

            value_str: str = f"{value_int:06d}"
            year_raw = int(value_str[:2])
            month = int(value_str[2:4])
            day = int(value_str[4:6])

            if not 1 <= month <= 12 or not 1 <= day <= 31:
                return None

            year = 2000 + year_raw if year_raw < 90 else 1900 + year_raw
            try:
                manufacture_date = date(year, month, day)
            except ValueError:
                return None
            return manufacture_date.isoformat()

        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "" or stripped.upper() == "TODO":
                return None
            return stripped

        return value

    async def _load_timezone_settings(self):
        """Load the current timezone offset from the E3DC, using its local timezone data.

        Required to correctly retrieve power statistics for today.
        """
        tz_name: str = await self.hass.async_add_executor_job(self.proxy.get_timezone)

        tz_offset: int | None = None
        try:
            tz_info: pytz.timezone = await self.hass.async_add_executor_job(
                pytz.timezone, tz_name
            )
            dt_tmp: datetime = datetime.now(tz_info)
            tz_offset = dt_tmp.utcoffset().seconds
        except pytz.UnknownTimeZoneError:
            _LOGGER.exception(
                "Failed to load timezone from E3DC, falling back to heuristics."
            )

        if tz_offset is None:
            # Fallback to compute the offset using current times from E3DC:
            ts_local: int = await self.hass.async_add_executor_job(self.proxy.get_time)
            ts_utc: int = await self.hass.async_add_executor_job(self.proxy.get_timeutc)
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

    async def async_set_wallbox_sun_mode(
        self, enabled: bool, wallbox_index: int
    ) -> bool:
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

    async def async_set_wallbox_max_charge_current(
        self, current: int | None, wallbox_index: int
    ) -> None:
        """Set the wallbox max charge current."""

        # TODO: Add more refined way to deal with maximum charge current, right now it's hard coded to 32A. The max current is dependant on the local installations, many WBs are throttled at 16A, not 32A due to power grid restrictions.

        # Validate the argument
        if current is None or current <= 0:
            raise ServiceValidationError(
                "async_set_wallbox_max_charge_current must be called with a positive current value."
            )

        if wallbox_index < 0 or wallbox_index >= MAX_WALLBOXES_POSSIBLE:
            raise ServiceValidationError(
                "async_set_wallbox_max_charge_current must be called with a valid wallbox id."
            )

        upperCurrentLimit = self.getWallboxValue(wallbox_index, "upperCurrentLimit")
        if current > upperCurrentLimit:
            _LOGGER.warning(
                "Requested Wallbox current of %s is too high. Limiting current to %s",
                current,
                upperCurrentLimit,
            )
            current = upperCurrentLimit

        lowerCurrentLimit = self.getWallboxValue(wallbox_index, "lowerCurrentLimit")
        if current < lowerCurrentLimit:
            _LOGGER.warning(
                "Requested Wallbox current of %s is too low. Limiting current to %s",
                current,
                lowerCurrentLimit,
            )
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
            raise ServiceValidationError(
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
            raise ServiceValidationError("Charge amount must be positive or zero.")

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

    @callback
    def _shutdown_power_mode(self, _event: Event | None) -> None:
        """Handle shutdown event to stop power mode updates."""
        self._stop_power_mode()

    @callback
    def _stop_power_mode(self) -> None:
        """Stop the power mode updates."""
        if self._stop_set_power_mode is not None:
            _LOGGER.debug("Stopping power mode")
            self._stop_set_power_mode()
            self._stop_set_power_mode = None
        self._mydata["set-power-mode"] = SetPowerMode.NORMAL.value
        self._mydata["set-power-value"] = None

    async def _async_set_power(self, keepAlive: bool = True) -> None:
        """Set the power mode and value based on the current state."""
        _LOGGER.debug(
            "Setting power mode: %s at %s W",
            SetPowerMode.get_enum(self._mydata["set-power-mode"]).name,
            self._mydata["set-power-value"],
        )

        try:
            power_value: int = await self.hass.async_add_executor_job(
                self.proxy.set_power_mode,
                int(self._mydata["set-power-mode"]),
                self._mydata["set-power-value"],
            )
            self._mydata["set-power-value"] = power_value
            power_mode_str: str = str(self.proxy.get_power_mode())
            if PowerMode.has_value(str(power_mode_str)):
                self._mydata["power-mode"] = power_mode_str
            else:
                _LOGGER.debug("Unknown power mode %s", power_mode_str)
                self._mydata["power-mode"] = f"Power mode {power_mode_str}"
        except HomeAssistantError as ex:
            _LOGGER.warning("Failed set power mode: %s", ex)
            self._stop_power_mode()

    async def async_set_power_mode(self, mode: SetPowerMode, value: int | None) -> None:
        """Set the power mode and value."""
        self._mydata["set-power-mode"] = mode.value
        self._mydata["set-power-value"] = value

        if mode == SetPowerMode.NORMAL and self._stop_set_power_mode is not None:
            self._stop_power_mode()
        else:
            if mode != SetPowerMode.NORMAL:
                _LOGGER.debug("Starting power mode")
                await self._async_set_power()
                if self._stop_set_power_mode is None:
                    self._stop_set_power_mode = async_track_time_interval(
                        self.hass, self._async_set_power, timedelta(seconds=10)
                    )
