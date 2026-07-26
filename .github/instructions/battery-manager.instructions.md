---
description: "Use when implementing battery identification, processing battery pack/module sensor data, calculating derived battery values (SoH, energy), managing battery device lifecycle, or updating battery sensor values."
applyTo: "custom_components/e3dc_rscp/battery_manager.py"
---

# Battery Manager (battery_manager.py)

## Battery Data Model

Two-tier battery hierarchy:

```python
class E3DCBatteryPack(TypedDict):
    """Battery pack (e.g., 'S10' battery)."""
    index: int              # Pack index from RSCP
    key: str                # Unique key for data dict (e.g., "battery-0")
    uniqueId: str           # Entity unique ID base
    name: str               # Display name
    deviceInfo: DeviceInfo  # HA device registry info

class E3DCBattery(TypedDict):
    """Battery module (DCB inside a pack)."""
    packIndex: int          # Parent pack index
    dcbIndex: int           # DCB module index within pack
    key: str                # Data dict key
    deviceInfo: DeviceInfo  # HA device registry info
    hasDeviceReportedSoh: bool  # Whether device provides SoH
```

- **Pack**: Physical battery product (e.g., E3DC S10)
- **Module**: DCB module inside a pack (multiple per pack)
- Packs store aggregated values (total SoH, remaining energy, etc.)
- Modules store individual cell-level data (current, voltage, error flags, etc.)

## Initialization

```python
def __init__(
    self,
    hass: HomeAssistant,
    uid: str,
    proxy: E3DCProxy,
    mydata: dict[str, Any],  # Shared reference with coordinator
    create_battery_devices_callback: callable,
):
    self.hass = hass
    self.uid = uid  # E3DC unique ID
    self.proxy = proxy
    self._mydata = mydata  # Coordinator's data dict (shared)
    self._create_battery_devices_callback = create_battery_devices_callback
    self._batteries: list[E3DCBattery] = []
    self._battery_packs: list[E3DCBatteryPack] = []
    self._identify_lock = asyncio.Lock()
```

- Receive coordinator's `_mydata` dict by reference
- Updates to `_mydata` propagate to entities immediately
- Battery device creation controlled by user option (callback)
- Lock prevents concurrent identification calls

## Battery Identification (async_identify_batteries)

```python
async def async_identify_batteries(self) -> None:
    """Identify installed battery modules if enabled via options."""
    async with self._identify_lock:
        if not self.create_battery_devices:
            await self.async_clear_battery_devices()
            return

        # Get batteries from proxy
        batteries_config = await hass.async_add_executor_job(self.proxy.get_batteries)

        # For each pack, build E3DCBatteryPack and add to list
        for pack_index, pack_config in enumerate(batteries_config):
            pack = E3DCBatteryPack(
                index=pack_index,
                key=f"battery-pack-{pack_index}",
                uniqueId=f"{self.uid}-battery-pack-{pack_index}",
                name=f"Battery Pack {pack_index}",
                deviceInfo=DeviceInfo(...)
            )
            self._battery_packs.append(pack)

            # For each DCB module in pack
            dcbs = pack_config.get("dcbs", {})
            for dcb_index, dcb_config in enumerate(dcbs.items()):
                battery = E3DCBattery(
                    packIndex=pack_index,
                    dcbIndex=dcb_index,
                    key=f"battery-{pack_index}-{dcb_index}",
                    deviceInfo=DeviceInfo(...),
                    hasDeviceReportedSoh=...
                )
                self._batteries.append(battery)
```

- Called once during setup via `coordinator.async_identify_batteries()`
- Queries proxy for available batteries
- Creates DeviceInfo entries for device registry
- Stores lists for entity creation
- Always use executor: `await hass.async_add_executor_job(self.proxy.get_batteries)`

## Data Loading & Processing (async_load_and_process_battery_data)

```python
async def async_load_and_process_battery_data(
    self, battery_data: Any | None = None
) -> None:
    """Load and process battery sensor data."""
    # Fetch data if not provided
    data = battery_data
    if data is None:
        data = await hass.async_add_executor_job(self.proxy.get_battery_data)

    # Parse structure (dict or list)
    pack_map = {}
    if isinstance(data, list):
        for idx, pack_data in enumerate(data):
            pack_map[idx] = pack_data
    elif isinstance(data, dict):
        pack_map = data

    # Update pack-level values
    if self.create_battery_devices and self._battery_packs:
        for pack in self._battery_packs:
            pack_data = pack_map.get(pack["index"])
            if not pack_data:
                continue

            # Raw sensor values
            for data_key, slug in BATTERY_PACK_RAW_SENSORS:
                value = pack_data.get(data_key)
                self._mydata[f"{pack['key']}-{slug}"] = value

            # Calculated sensor values
            for slug in BATTERY_PACK_CALCULATED_SENSORS:
                value = self._calculate_battery_pack_value(slug, pack_data)
                self._mydata[f"{pack['key']}-{slug}"] = value

    # Update module-level values
    for battery in self.batteries:
        pack_data = pack_map.get(battery["packIndex"])
        if not pack_data:
            continue

        dcbs = pack_data.get("dcbs", {})
        dcb = dcbs.get(battery["dcbIndex"])
        if not dcb:
            continue

        for data_key, slug in BATTERY_MODULE_RAW_SENSORS:
            value = self._process_battery_sensor_value(data_key, dcb.get(data_key), dcb)
            self._mydata[f"{battery['key']}-{slug}"] = value
```

- Called from coordinator's `_async_update_data()` polling loop
- Transforms raw proxy data into entity-ready keys
- Updates `self._mydata` directly (shared with coordinator)
- Handles both dict and list response formats

## Calculated Battery Values

```python
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
```

The final `return pack.get(slug)` is the pass-through for raw values, so an unknown slug yields the raw
device reading rather than `None`. Add a new branch here for every new calculated sensor.

```python
def _calculate_battery_state_of_health(self, pack: dict[str, Any]) -> float | None:
    """Calculate SoH as (fcc / designCapacity) * 100."""
    try:
        design_capacity = float(pack.get("designCapacity", 0))
        full_charge_capacity = float(pack.get("fcc", 0))
        if design_capacity <= 0:
            return None
        return (full_charge_capacity / design_capacity) * 100
    except (TypeError, ValueError):
        return None
```

- Calculations are performed on proxy-provided data
- Always catch `TypeError` and `ValueError` (handle missing/malformed fields)
- Return `None` for invalid/missing intermediate values (not 0)
- Energy calculations use voltage, capacity, DCB count from pack metadata

## Battery Sensor Value Processing

```python
def _process_battery_sensor_value(
    self, data_key: str, value: Any, dcb: dict[str, Any]
) -> Any:
    """Normalize and validate individual sensor values."""
    # If a value is missing, try to calculate it
    if data_key == "soc" and value is None:
        return self._calculate_battery_soc_from_capacity(dcb)

    if value is None:
        return None

    # Parse special formats
    if data_key == "manufactureDate":
        return self._parse_battery_manufacture_date(value)

    # Normalize strings: strip and return None for empty
    if isinstance(value, str):
        value = value.strip()
        return None if not value else value

    return value
```

- **Missing values**: Some devices don't report all fields; use fallback calculations
- **Special formats**: Parse dates, enums, etc. from raw values
- **String normalization**: Strip whitespace, treat empty strings as None
- Return `None` for truly missing data, not empty defaults

## Battery Device Lifecycle

```python
async def async_clear_battery_devices(self) -> None:
    """Remove battery devices and clear data."""
    device_registry = dr.async_get(self.hass)

    # Find and remove devices by identifier prefix
    battery_prefixes = (
        f"{self.uid}-battery-",
        f"{self.uid}-battery-pack-",
    )
    for entry in device_registry.devices.values():
        for identifier in entry.identifiers:
            if identifier[0] == DOMAIN and any(
                identifier[1].startswith(prefix) for prefix in battery_prefixes
            ):
                device_registry.async_remove_device(entry.id)

    # Clear data
    self._batteries.clear()
    self._battery_packs.clear()

    # Remove from shared mydata dict
    for key in list(self._mydata.keys()):
        if key.startswith("battery-"):
            del self._mydata[key]
```

- Called when user disables battery device creation
- Remove from device registry (cleanup)
- Clear internal lists and data
- Entities depending on this data will stop updating

## Properties

```python
@property
def batteries(self) -> list[E3DCBattery]:
    """Identified battery modules."""
    return self._batteries

@property
def battery_packs(self) -> list[E3DCBatteryPack]:
    """Identified battery packs."""
    return self._battery_packs

@property
def create_battery_devices(self) -> bool:
    """Check if battery devices should be created."""
    return self._create_battery_devices_callback()
```

- Expose to coordinator, which exposes to entities
- `create_battery_devices` is dynamic (from config options)

## Data Dictionary Naming

Use consistent key patterns in `self._mydata`:

```
battery-{pack_index}-{slug}        # Pack sensor (e.g., battery-0-soc)
battery-{pack_index}-{dcb_index}-{slug}  # Module sensor (e.g., battery-0-1-voltage)
```

- Slugs use kebab-case (e.g., `full-charge-capacity`)
- Entity unique IDs tie to these keys; do not rename without migration

## Error Handling

- Calculations return `None` on invalid input, never raise
- Missing fields are expected (not all devices report all data)
- Log at `DEBUG` level for data transformation issues
- Never fail the entire polling cycle on one battery calculation error

## Backwards Compatibility

- Do not remove or rename sensor tuples in `BATTERY_*_SENSORS` (breaks entity unique IDs)
- Adding new calculated sensors is safe (new keys)
- Changing calculation logic should be backwards-compatible (same output keys)
