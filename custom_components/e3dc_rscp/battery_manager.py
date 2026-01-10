"""Battery management for E3DC integration."""

import asyncio
from datetime import date
import logging
from typing import Any, TypedDict

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.entity import DeviceInfo

from .e3dc_proxy import E3DCProxy

from .const import (
    DOMAIN,
    BATTERY_MODULE_RAW_SENSORS,
    BATTERY_MODULE_CALCULATED_SENSORS,
    BATTERY_PACK_RAW_SENSORS,
    BATTERY_PACK_CALCULATED_SENSORS,
)

_LOGGER = logging.getLogger(__name__)


class E3DCBattery(TypedDict):
    """E3DC Battery module, keeps module index, identifier and device info."""

    packIndex: int
    dcbIndex: int
    key: str
    deviceInfo: DeviceInfo


class E3DCBatteryPack(TypedDict):
    """E3DC Battery pack metadata used for sensors and device linking."""

    index: int
    key: str
    uniqueId: str
    name: str
    deviceInfo: DeviceInfo


class E3DCBatteryManager:
    """Manages battery identification, data processing, and device lifecycle."""

    def __init__(
        self,
        hass: HomeAssistant,
        uid: str,
        proxy: E3DCProxy,
        mydata: dict[str, Any],
        create_battery_devices_callback: callable,
    ) -> None:
        """Initialize the battery manager.

        Args:
            hass: Home Assistant instance
            uid: Unique identifier for the E3DC system
            proxy: E3DC proxy for communication
            mydata: Shared data dictionary for sensor values
            create_battery_devices_callback: Function that returns whether battery devices should be created

        """
        self.hass = hass
        self.uid = uid
        self.proxy = proxy
        self._mydata = mydata
        self._create_battery_devices_callback = create_battery_devices_callback
        self._batteries: list[E3DCBattery] = []
        self._battery_packs: list[E3DCBatteryPack] = []
        self._identify_lock = asyncio.Lock()

    @property
    def batteries(self) -> list[E3DCBattery]:
        """Get the list of identified battery modules."""
        return self._batteries

    @property
    def battery_packs(self) -> list[E3DCBatteryPack]:
        """Get the list of battery packs for the configured batteries."""
        return self._battery_packs

    @property
    def create_battery_devices(self) -> bool:
        """Check if battery devices should be created."""
        return self._create_battery_devices_callback()

    async def async_clear_battery_devices(self) -> None:
        """Remove any previously created battery devices and clear all battery data."""
        device_registry = dr.async_get(self.hass)
        battery_prefixes = (
            f"{self.uid}-battery-",
            f"{self.uid}-battery-pack-",
        )
        devices_to_remove: list[str] = []

        for entry in device_registry.devices.values():
            if any(
                identifier[0] == DOMAIN
                and any(identifier[1].startswith(prefix) for prefix in battery_prefixes)
                for identifier in entry.identifiers
            ):
                devices_to_remove.append(entry.id)

        for device_id in devices_to_remove:
            device_registry.async_remove_device(device_id)

        # Clear battery module data
        self._batteries.clear()
        battery_key_prefix = "battery-"
        for key in list(self._mydata.keys()):
            if key.startswith(battery_key_prefix):
                self._mydata.pop(key)

        # Clear battery pack data
        self._battery_packs.clear()

    async def async_identify_batteries(self) -> None:
        """Identify installed battery modules if enabled via options."""
        async with self._identify_lock:
            if not self.create_battery_devices:
                _LOGGER.debug("Battery devices disabled via options, skipping identification")
                await self.async_clear_battery_devices()
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
                    if stripped == "":
                        return None
                return value

            self._batteries.clear()
            pack_entries: dict[int, E3DCBatteryPack] = {}

            for battery_config in batteries_config or []:
                pack_index = battery_config.get("index", 0)
                dcb_count = battery_config.get("dcbs", 0)
                pack_details = battery_details_by_pack.get(pack_index, {})
                dcbs_details: dict[int, dict[str, Any]] = {}
                if isinstance(pack_details, dict):
                    dcbs = pack_details.get("dcbs")
                    if isinstance(dcbs, dict):
                        dcbs_details = dcbs

                pack_key = f"battery-pack-{pack_index}"
                pack_unique_id = f"{self.uid}-{pack_key}"
                pack_entry = pack_entries.get(pack_index)
                if pack_entry is None:
                    pack_manufacturer = _normalize(pack_details.get("manufactureName"))
                    pack_model = _normalize(pack_details.get("deviceName"))
                    pack_name = f"Battery Pack {pack_index + 1}"

                    deviceInfo: DeviceInfo = DeviceInfo(
                        identifiers={(DOMAIN, pack_unique_id)},
                        via_device=(DOMAIN, self.uid),
                        manufacturer=pack_manufacturer,
                        name=pack_name,
                        model=pack_model,
                    )

                    pack_entry = {
                        "index": pack_index,
                        "key": pack_key,
                        "uniqueId": pack_unique_id,
                        "name": pack_name,
                        "deviceInfo": deviceInfo,
                    }
                    pack_entries[pack_index] = pack_entry

                for dcb_index in range(dcb_count):
                    battery_key = f"battery-{pack_index}-{dcb_index}"
                    unique_id = f"{self.uid}-{battery_key}"
                    dcb_detail = dcbs_details.get(dcb_index, {}) if isinstance(dcbs_details, dict) else {}

                    manufacturer = _normalize(dcb_detail.get("manufactureName"))
                    model = _normalize(dcb_detail.get("deviceName"))
                    name = f"Battery Pack {pack_index + 1} Module {dcb_index + 1}"
                    serial_no = _normalize(dcb_detail.get("serialNo"))
                    fw_version = _normalize(dcb_detail.get("fwVersion"))
                    pcb_version = _normalize(dcb_detail.get("pcbVersion"))

                    deviceInfo = DeviceInfo(
                        identifiers={(DOMAIN, unique_id)},
                        via_device=(DOMAIN, pack_entry["uniqueId"]),
                        manufacturer=manufacturer,
                        name=name,
                        model=model,
                    )

                    if serial_no is not None:
                        deviceInfo["serial_number"] = str(serial_no)
                    if fw_version is not None:
                        deviceInfo["sw_version"] = str(fw_version)
                    if pcb_version is not None:
                        deviceInfo["hw_version"] = str(pcb_version)

                    battery_entry: E3DCBattery = {
                        "packIndex": pack_index,
                        "dcbIndex": dcb_index,
                        "key": battery_key,
                        "deviceInfo": deviceInfo,
                    }
                    self._batteries.append(battery_entry)

            self._battery_packs = [
                pack_entries[index] for index in sorted(pack_entries.keys())
            ]

            if len(self._batteries) > 0:
                await self.async_load_and_process_battery_data(battery_data)
                _LOGGER.debug("Identified %s battery modules across %s packs", len(self._batteries), len(self._battery_packs))
            else:
                _LOGGER.debug("No battery modules were identified")

    async def async_load_and_process_battery_data(self, battery_data: Any | None = None) -> None:
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

        # Update battery pack sensor values
        if self.create_battery_devices and self._battery_packs:
            for pack_entry in self._battery_packs:
                pack_index = pack_entry["index"]
                pack = pack_map.get(pack_index)

                if pack is None:
                    # No data for this pack, set sensors to None
                    pack_key = pack_entry["key"]
                    for _, slug in BATTERY_PACK_RAW_SENSORS:
                        full_key = f"{pack_key}-{slug}"
                        self._mydata[full_key] = None
                    for slug in BATTERY_PACK_CALCULATED_SENSORS:
                        full_key = f"{pack_key}-{slug}"
                        self._mydata[full_key] = None
                    continue

                pack_key = pack_entry["key"]

                # Process raw sensor values from pack data
                for data_key, slug in BATTERY_PACK_RAW_SENSORS:
                    full_key = f"{pack_key}-{slug}"
                    raw_value = pack.get(data_key)

                    if isinstance(raw_value, list | dict | set | tuple):
                        value = None
                    else:
                        value = raw_value

                    processed_value = self._process_battery_sensor_value(
                        data_key, value, pack
                    )
                    self._mydata[full_key] = processed_value

                # Process calculated sensor values
                for slug in BATTERY_PACK_CALCULATED_SENSORS:
                    full_key = f"{pack_key}-{slug}"
                    calculated_value = self._calculate_battery_pack_value(slug, pack)
                    self._mydata[full_key] = calculated_value

        # Update battery module sensor values
        for battery in self.batteries:
            pack = pack_map.get(battery["packIndex"], {})
            dcb_data: dict[str, Any] | None = None
            if isinstance(pack, dict):
                dcbs = pack.get("dcbs")
                if isinstance(dcbs, dict):
                    dcb_data = dcbs.get(battery["dcbIndex"])

            if not isinstance(dcb_data, dict):
                for _, slug in BATTERY_MODULE_RAW_SENSORS:
                    self._mydata[f"{battery['key']}-{slug}"] = None
                continue

            # Process raw sensor values
            for data_key, slug in BATTERY_MODULE_RAW_SENSORS:
                raw_value: Any = dcb_data.get(data_key)
                if isinstance(raw_value, list | dict | set | tuple):
                    continue

                processed_value = self._process_battery_sensor_value(
                    data_key, raw_value, dcb_data
                )

                self._mydata[f"{battery['key']}-{slug}"] = processed_value

            # Process calculated sensor values
            for slug in BATTERY_MODULE_CALCULATED_SENSORS:
                full_key = f"{battery['key']}-{slug}"
                if slug == "soh":
                    calculated_value = self._calculate_battery_soh_from_capacity(dcb_data)
                else:
                    calculated_value = None
                self._mydata[full_key] = calculated_value

    def _get_dcb_count_from_pack(self, pack: dict[str, Any]) -> int | None:
        """Get the number of DCB modules in a battery pack."""
        dcbs = pack.get("dcbs")
        if isinstance(dcbs, dict):
            if len(dcbs) > 0:
                return len(dcbs)
        elif isinstance(dcbs, list):
            if len(dcbs) > 0:
                return len(dcbs)

        raw_count = pack.get("dcbCount")
        try:
            return int(raw_count)
        except (TypeError, ValueError):
            return None

    def _get_dcb_design_voltage(self, pack: dict[str, Any]) -> Any:
        """Get the design voltage from the first DCB module in a pack.

        All DCB modules in a pack should have the same design voltage,
        so we retrieve it from the first available module.
        """
        dcbs = pack.get("dcbs")
        first: Any | None = None
        if isinstance(dcbs, dict) and len(dcbs) > 0:
            first = next(iter(dcbs.values()), None)
        elif isinstance(dcbs, list) and len(dcbs) > 0:
            first = dcbs[0]

        if isinstance(first, dict):
            return first.get("designVoltage")

        return None

    def _calculate_battery_design_energy(self, pack: dict[str, Any]) -> float | None:
        """Calculate battery pack design energy in kWh."""
        dcb_count = self._get_dcb_count_from_pack(pack)
        if dcb_count is None or dcb_count <= 0:
            return None

        design_capacity_raw = pack.get("designCapacity")
        design_voltage_raw = self._get_dcb_design_voltage(pack)

        try:
            design_capacity = float(design_capacity_raw)
            design_voltage = float(design_voltage_raw)
        except (TypeError, ValueError):
            return None

        return (design_capacity * (dcb_count * design_voltage)) / 1000

    def _calculate_battery_full_energy(self, pack: dict[str, Any]) -> float | None:
        """Calculate battery pack full charge energy in kWh."""
        dcb_count = self._get_dcb_count_from_pack(pack)
        if dcb_count is None or dcb_count <= 0:
            return None

        full_charge_capacity_raw = pack.get("fcc")
        design_voltage_raw = self._get_dcb_design_voltage(pack)

        try:
            full_charge_capacity = float(full_charge_capacity_raw)
            design_voltage = float(design_voltage_raw)
        except (TypeError, ValueError):
            return None

        return (full_charge_capacity * (dcb_count * design_voltage)) / 1000

    def _calculate_battery_remaining_energy(self, pack: dict[str, Any]) -> float | None:
        """Calculate battery pack remaining energy in kWh."""
        remaining_capacity_raw = pack.get("rc")
        module_voltage_raw = pack.get("moduleVoltage")
        try:
            remaining_capacity = float(remaining_capacity_raw)
            module_voltage = float(module_voltage_raw)
        except (TypeError, ValueError):
            return None

        return (remaining_capacity * module_voltage) / 1000

    def _calculate_battery_usable_remaining_energy(self, pack: dict[str, Any]) -> float | None:
        """Calculate battery pack usable remaining energy in kWh."""
        usable_remaining_capacity_raw = pack.get("usuableRemainingCapacity")
        module_voltage_raw = pack.get("moduleVoltage")
        try:
            usable_remaining_capacity = float(usable_remaining_capacity_raw)
            module_voltage = float(module_voltage_raw)
        except (TypeError, ValueError):
            return None

        return (usable_remaining_capacity * module_voltage) / 1000

    def _calculate_battery_state_of_health(self, pack: dict[str, Any]) -> float | None:
        """Calculate battery pack state of health as percentage."""
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

    def _calculate_battery_pack_value(self, slug: str, pack: dict[str, Any]) -> Any:
        """Calculate derived battery pack values."""
        if slug == "design-energy":
            return self._calculate_battery_design_energy(pack)
        if slug == "full-energy":
            return self._calculate_battery_full_energy(pack)
        if slug == "remaining-energy":
            return self._calculate_battery_remaining_energy(pack)
        if slug == "usable-remaining-energy":
            return self._calculate_battery_usable_remaining_energy(pack)
        if slug == "state-of-health":
            return self._calculate_battery_state_of_health(pack)

        return pack.get(slug)

    def _calculate_battery_soc_from_capacity(self, dcb: dict[str, Any]) -> float | None:
        """Calculate SOC from remaining capacity and voltage if not directly available."""
        remaining_capacity_raw = dcb.get("remainingCapacity")
        voltage_raw = dcb.get("voltage")
        try:
            remaining_capacity = float(remaining_capacity_raw)
            voltage = float(voltage_raw)
        except (TypeError, ValueError):
            return None
        return (remaining_capacity * voltage) / 1000

    def _calculate_battery_soh_from_capacity(self, dcb: dict[str, Any]) -> float | None:
        """Calculate SOH from full charge capacity and design capacity if not directly available."""
        full_charge_capacity_raw = dcb.get("fullChargeCapacity")
        design_capacity_raw = dcb.get("designCapacity")
        try:
            full_charge_capacity = float(full_charge_capacity_raw)
            design_capacity = float(design_capacity_raw)
        except (TypeError, ValueError):
            return None

        if design_capacity <= 0:
            return None

        return (full_charge_capacity / design_capacity) * 100

    def _parse_battery_manufacture_date(self, value: Any) -> str | None:
        """Parse battery manufacture date from numeric format to ISO date string."""
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

    def _process_battery_sensor_value(self, data_key: str, value: Any, dcb: dict[str, Any]) -> Any:
        """Process individual battery sensor values before storing."""
        if data_key == "soc" and value is None:
            return self._calculate_battery_soc_from_capacity(dcb)

        if value is None:
            return None

        if data_key == "manufactureDate":
            return self._parse_battery_manufacture_date(value)

        # Normalize string values: strip whitespace and return None for empty strings
        if isinstance(value, str):
            stripped = value.strip()
            return None if stripped == "" else stripped

        return value
