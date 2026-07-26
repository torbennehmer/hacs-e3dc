---
description: "Use when implementing data polling, coordinator lifecycle, async executor wrapping, data transformation pipelines, device identification (wallboxes/batteries/sgready), timezone handling, or service call relaying through the coordinator."
applyTo: "custom_components/e3dc_rscp/coordinator.py"
---

# Data Coordinator (coordinator.py)

## DataUpdateCoordinator Pattern

```python
class E3DCCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        self.uid = config_entry.unique_id  # Unique identifier for this E3DC
        self.proxy = E3DCProxy(hass, config_entry)
        self._mydata: dict[str, Any] = {}  # Shared data dict with battery_manager
        super().__init__(
            hass, _LOGGER, name=DOMAIN, update_interval=timedelta(seconds=10)
        )
```

- `DataUpdateCoordinator` handles polling lifecycle automatically
- `_async_update_data()` is called on interval and returns dict
- `self.last_update_success` tracks connection state
- Exceptions in `_async_update_data()` become `UpdateFailed` (logged, not fatal)

## Initialization Flow (async_connect)

Called once during integration setup:
1. Connect to E3DC via executor: `await self.hass.async_add_executor_job(self.proxy.connect)`
2. Query static system properties (derate, battery capacity, AC power, etc.) directly from `self.proxy.e3dc` attributes
3. Load timezone and software version via proxy methods in executor
4. Call device identification methods: `async_identify_farm()`, `async_identify_wallboxes()`, `async_identify_sgready()`, `async_identify_batteries()`
   - Note the signatures differ: `async_identify_sgready(self)` takes **no** `hass` argument, unlike the others.

## Device Identification Pattern

Each `async_identify_*` method discovers specific device classes:

```python
async def async_identify_wallboxes(self, hass: HomeAssistant):
    """Discover available wallboxes."""
    # NOTE: upper bound is exclusive of the last slot - keep this as-is
    for wallbox_index in range(0, MAX_WALLBOXES_POSSIBLE - 1):
        identification_data = await self.hass.async_add_executor_job(
            self.proxy.get_wallbox_identification_data, wallbox_index
        )
        if identification_data and identification_data.get("deviceName"):
            # Create E3DCWallbox dict, add to self._wallboxes list
            self._wallboxes.append({
                "index": wallbox_index,
                "key": f"wallbox-{wallbox_index}",
                "deviceInfo": DeviceInfo(...),
                ...
            })
```

- Run discovery during setup (async_setup_entry in __init__.py calls these)
- Wrap proxy method calls in `hass.async_add_executor_job()`
- Store discovered devices in list properties (e.g., `self._wallboxes`, delegate to `battery_manager.batteries`)
- Expose via `@property` for entity access

## Polling Loop (_async_update_data)

Called automatically on coordinator's update interval:

```python
async def _async_update_data(self) -> dict[str, Any]:
    """Coordinator calls this automatically."""
    await self._load_and_process_poll()

    # Guards suppress a reload while a user-initiated write is still in flight,
    # otherwise the UI would flicker back to the pre-write value.
    if self._update_guard_powersettings is False:
        await self._load_and_process_power_settings()

    await self._load_and_process_manual_charge()
    await self._load_and_process_sgready_state()

    if self._update_guard_wallboxsettings is False:
        await self._load_and_process_powermeters_data()

    if len(self.wallboxes) > 0:
        await self._load_and_process_wallbox_data()

    if self.create_battery_devices:
        await self.battery_manager.async_load_and_process_battery_data()

    if self._next_stat_update < time():
        await self._load_and_process_db_data_today()

    return self._mydata  # Return shared data dict
```

- Never call proxy methods directly; use executor: `await self.hass.async_add_executor_job(self.proxy.method, args)`
- Aggregate all updates into `self._mydata` dict
- Return the dict for entities to subscribe to
- Exceptions become `UpdateFailed`; coordinator handles retries
- All blocking I/O is executor-wrapped
- Statistics are time-gated via `self._next_stat_update`, not refreshed every cycle

## Data Transformation (_load_and_process_* Methods)

Pattern for each load method:

```python
async def _load_and_process_poll(self):
    """Fetch poll data and update self._mydata."""
    poll_data = await self.hass.async_add_executor_job(
        self.proxy.poll  # Proxy method returns structured dict
    )

    # Transform and normalize
    self._mydata["system-pv-power"] = poll_data.get("pvPower", 0)
    self._mydata["battery-soc"] = poll_data.get("soc", 0)
    # ... update many keys
```

- Fetch structured data from proxy methods (never raw RSCP tuples)
- Transform keys to entity-friendly slugs (kebab-case)
- Store in `self._mydata` with consistent key naming
- Handle missing keys gracefully (use `.get(key, default)`)
- No calculations here; transformations only (calculations done in entities or battery_manager)

## Timezone & Timestamp Handling

E3/DC returns Unix timestamps in **local device time** (not UTC):

```python
async def _load_timezone_settings(self):
    """Load timezone offset once at startup."""
    tz_name = await self.hass.async_add_executor_job(self.proxy.get_timezone)
    device_time = await self.hass.async_add_executor_job(self.proxy.get_time)
    utc_time = await self.hass.async_add_executor_job(self.proxy.get_timeutc)

    self._timezone_offset = device_time - utc_time  # Seconds offset
    self._mydata["timezone"] = tz_name
```

- Store offset at startup
- Apply offset when converting timestamps: `utc_timestamp = local_timestamp - self._timezone_offset`
- Never mix local timestamps and UTC in data dict; always convert to UTC for HA

## Service Relay Methods

Coordinator exposes async methods that services call:

```python
async def async_set_power_limits(self, max_charge: int | None, max_discharge: int | None) -> None:
    """Relay service call to proxy."""
    await self.hass.async_add_executor_job(
        self.proxy.set_power_limits,
        enable=True,
        max_charge=max_charge,
        max_discharge=max_discharge,
    )
    # Re-poll immediately to reflect change
    await self.async_request_refresh()
```

- Service handler calls coordinator method (not proxy directly)
- Coordinator wraps proxy call in executor
- After state-changing operations, call `await self.async_request_refresh()` to re-poll
- Exceptions (ConfigEntryAuthFailed, HomeAssistantError) propagate to service handler

## State Update Guards

Use flags to prevent concurrent updates to same resource:

```python
async def async_set_wallbox_max_charge_current(self, current: int, wallbox_index: int) -> None:
    """Set wallbox charging current with guard."""
    if self._update_guard_wallboxsettings:
        raise HomeAssistantError("Wallbox settings update already in progress")

    self._update_guard_wallboxsettings = True
    try:
        await self.hass.async_add_executor_job(
            self.proxy.set_wallbox_max_charge_current, current, wallbox_index
        )
        await self.async_request_refresh()
    finally:
        self._update_guard_wallboxsettings = False
```

- Use boolean guard flag for concurrent operation prevention
- Always set flag in try/finally to prevent deadlock

## Data Access Patterns

```python
@property
def wallboxes(self) -> list[E3DCWallbox]:
    """Expose identified wallboxes to entities."""
    return self._wallboxes

def setWallboxValue(self, index: int, key: str, value: Any) -> None:
    """Update individual wallbox state value."""
    for wallbox in self._wallboxes:
        if wallbox["index"] == index:
            wallbox[key] = value
            return
    raise ValueError(f"Wallbox {index} not found")
```

- Properties expose lists (wallboxes, batteries, battery_packs)
- Setters allow entities to update specific values
- Getters retrieve specific values for entity state

## Battery Manager Integration

```python
self.battery_manager = E3DCBatteryManager(
    hass=hass,
    uid=self.uid,
    proxy=self.proxy,
    mydata=self._mydata,  # Shared reference
    create_battery_devices_callback=lambda: self.config_entry.options.get(...)
)

# In _async_update_data():
await self.battery_manager.async_load_and_process_battery_data()

# Properties delegate to battery_manager:
@property
def batteries(self) -> list[E3DCBattery]:
    return self.battery_manager.batteries
```

- Pass `self._mydata` by reference (shared dict)
- Battery manager updates the dict during polling
- Expose battery manager's properties via coordinator properties

## Error Handling

- Exceptions in `_async_update_data()` → caught by coordinator → `UpdateFailed` logged
- Service relay methods raise `HomeAssistantError` or `ServiceValidationError` (caught by HA)
- `ConfigEntryAuthFailed` from proxy → coordinator marks connection failed → re-auth flow triggered

## Backwards Compatibility

- Do not rename `self._mydata` keys (breaks entity unique IDs tied to old sensor keys)
- When adding new data keys, use new keys; migrate old keys to new ones during polling
- Device info identifiers must remain stable; wallbox/battery indices must not change across firmware versions
