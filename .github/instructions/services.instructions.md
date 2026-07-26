---
description: "Use when registering services, validating service parameters, mapping device IDs to coordinators, or relaying service calls through the coordinator."
applyTo: "custom_components/e3dc_rscp/services.py"
---

# Services (services.py)

## Service Registration Pattern

Call `async_setup_services()` once during integration setup (from `__init__.async_setup_entry`):

```python
async def async_setup_services(hass: HomeAssistant) -> None:
    """Register all services."""

    async def async_call_set_power_limits(call: ServiceCall) -> None:
        await _async_set_power_limits(hass, call)

    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_SET_POWER_LIMITS,
        service_func=async_call_set_power_limits,
        schema=SCHEMA_SET_POWER_LIMITS,
    )
```

- Service names (e.g., `SERVICE_SET_POWER_LIMITS`) match `services.yaml` keys
- Each service gets a wrapper async function and a handler function (e.g., `_async_set_power_limits`)
- Schema validates input parameters (voluptuous)
- Register once per integration startup (not per entry if only one instance)

## Service YAML Definition

`services.yaml` declares service schema and UI:

```yaml
set_power_limits:
  fields:
    device_id:
      required: true
      example: "64d3b74a1bcf319288844ff9e93e4010"
      selector:
        device:
          filter:
            integration: e3dc_rscp
    max_charge:
      required: false
      example: "1000"
      selector:
        number:
          min: 0
          unit_of_measurement: W
```

- `device_id` required for all E3DC services (identifies target coordinator)
- Field names match service attribute constants (e.g., `ATTR_MAX_CHARGE`)
- Selectors provide HA UI pickers (device, number, select, etc.)
- Example values help documentation

## Parameter Validation Schema

```python
SCHEMA_SET_POWER_LIMITS = vol.Schema(
    {
        vol.Required(ATTR_DEVICEID): str,
        vol.Optional(ATTR_MAX_CHARGE): vol.All(int, vol.Range(min=0)),
        vol.Optional(ATTR_MAX_DISCHARGE): vol.All(int, vol.Range(min=0)),
    }
)
```

- `vol.Required` / `vol.Optional` for mandatory/optional parameters
- `vol.All(int, vol.Range(min=0))` chains validators (type + range)
- Schema is passed to `async_register(..., schema=SCHEMA_*)`
- HA validates input before calling handler

## Device ID Resolution

```python
def _resolve_device_id(hass: HomeAssistant, devid: str) -> E3DCCoordinator:
    """Map device_id to coordinator."""
    # Check cache first
    if devid in _device_map:
        return _device_map[devid]

    dev_reg = async_get(hass)
    dev = dev_reg.async_get(devid)

    # Follow via_device_id if applicable (for child devices)
    if dev.via_device_id is not None:
        via_dev = dev_reg.async_get(dev.via_device_id)
        if via_dev is not None and DOMAIN in [id[0] for id in via_dev.identifiers]:
            dev = via_dev

    # Extract UID from device identifiers
    uid = None
    for domain, identifier in dev.identifiers:
        if domain == DOMAIN:
            uid = identifier
            break

    if uid is None:
        raise HomeAssistantError(f"Device {devid} is not an E3DC")

    coordinator = hass.data[DOMAIN][uid]
    _device_map[devid] = coordinator  # Cache for performance
    return coordinator
```

- HA stores all integration instances in `hass.data[DOMAIN][uid]` (uid = unique_id from ConfigEntry)
- Device identifiers are `(DOMAIN, uid_string)` tuples
- `via_device_id` is used for child devices (e.g., wallbox under main E3DC); follow link to get parent
- Cache resolved coordinators for performance (_device_map)

## Wallbox ID Resolution

```python
def _resolve_wallbox_id(hass: HomeAssistant, devid: str) -> int | None:
    """Map wallbox device_id to wallbox index."""
    coordinator = _resolve_device_id(hass, devid)

    dev_reg = async_get(hass)
    dev = dev_reg.async_get(devid)

    # Find wallbox by matching device identifiers
    for wallbox in coordinator.wallboxes:
        wallbox_device_id = list(wallbox["deviceInfo"]["identifiers"])[0][1]
        dev_device_id = list(dev.identifiers)[0][1]
        if wallbox_device_id == dev_device_id:
            return wallbox["index"]

    raise HomeAssistantError(f"No wallbox found for device {devid}")
```

- Get wallbox index from coordinator.wallboxes list
- Match by comparing device identifiers
- Wallbox index is RSCP parameter for proxy method calls

## Service Handler Pattern

```python
async def _async_set_power_limits(hass: HomeAssistant, call: ServiceCall) -> None:
    """Extract parameters and relay to coordinator."""
    # Get coordinator from device_id
    coordinator = _resolve_device_id(hass, call.data.get(ATTR_DEVICEID))

    # Extract and validate parameters
    max_charge = call.data.get(ATTR_MAX_CHARGE)
    max_discharge = call.data.get(ATTR_MAX_DISCHARGE)

    if max_charge is None and max_discharge is None:
        raise ServiceValidationError(
            f"Need to set at least one of {ATTR_MAX_CHARGE} or {ATTR_MAX_DISCHARGE}"
        )

    # Relay to coordinator method (which wraps proxy call)
    await coordinator.async_set_power_limits(
        max_charge=max_charge,
        max_discharge=max_discharge
    )
```

- Extract and re-validate parameters (in addition to schema validation)
- Raise `ServiceValidationError` for business logic violations
- Call coordinator method (not proxy directly)
- Let exceptions propagate (HA logs them)

## Exception Handling

- **`ServiceValidationError`**: Invalid parameters (business logic) → user sees error in UI
- **`HomeAssistantError`**: Device communication error → logged as error, service fails
- **`ConfigEntryAuthFailed`**: Auth error → coordinator marks failed → re-auth flow
- Never catch exceptions silently; let HA handle propagation

## Translation Keys

Service parameter names should have translation keys in `translations/en.json`:

```json
{
  "services": {
    "set_power_limits": {
      "name": "Set power limits",
      "description": "Set maximum charge/discharge power",
      "fields": {
        "device_id": { "name": "Device" },
        "max_charge": { "name": "Max charge power" }
      }
    }
  }
}
```

- Add keys before first use; remove keys when service is removed
- Maintain across all `translations/*.json` files (at least en.json)

## Caching & Performance

- Cache device ID → coordinator mapping in `_device_map` to avoid registry lookups on every call
- Clear cache only if device registry changes (typically not done; cache persists for session)

## Service Ordering

Register services once during `async_setup_entry` in `__init__.py`, not per coordinator instance:
- Only register if first entry (check if already registered, or use flag)
- Services are global and handle all coordinator instances via device_id routing

## Backwards Compatibility

- Do not rename service names (breaks automations and scripts)
- Do not remove service parameters (mark as optional if no longer used)
- Adding new optional parameters is safe
- Changing parameter types must be done with migration/deprecation period
