---
description: "Use when adding configuration keys, entity sensors/service definitions, enums, platform lists, or constants that define the E3DC integration's schema and behavior."
applyTo: "custom_components/e3dc_rscp/const.py"
---

# Constants & Schema (const.py)

## Configuration Keys

Only integration-specific keys are declared here. Standard keys — `CONF_USERNAME`, `CONF_PASSWORD`,
`CONF_HOST`, `CONF_PORT`, `CONF_API_VERSION` — are **imported from `homeassistant.const`**; do not
redefine them in this file.

Declared locally in `const.py`:
- **Auth**: `CONF_RSCPKEY`, `CONF_AUTH_TYPE`, plus the `AUTH_TYPE_CLOUD` / `AUTH_TYPE_LOCAL` selectors and
  `LOCAL_USERNAME`
- **Feature flags**: `CONF_FARMCONTROLLER` (bool)
- **Optional features**: `CONF_CREATE_BATTERY_DEVICES` (bool, with a `DEFAULT_<name>` default value)

Version bumping:
- `CONF_VERSION` = current schema version
- Increment when adding/removing/renaming config keys
- Corresponding migration logic must be in `__init__.async_migrate_entry()`

## Error Keys

Errors used in config flow must be defined as `ERROR_<name>` constants:
- `ERROR_AUTH_INVALID`: Authentication credentials rejected
- `ERROR_CANNOT_CONNECT`: Network/connection failure

These keys must match translation strings in `translations/en.json`.

## Sensor & Battery Module Definitions

Battery module sensors are organized as tuples of `(data_key, slug)` pairs:
- **Raw sensors** (`BATTERY_MODULE_RAW_SENSORS`, `BATTERY_PACK_RAW_SENSORS`): Retrieved directly from python-e3dc device data
- **Calculated sensors** (`BATTERY_MODULE_CALCULATED_SENSORS`, `BATTERY_PACK_CALCULATED_SENSORS`): Computed locally, not fetched from device

Example:
```python
BATTERY_MODULE_RAW_SENSORS = (
    ("current", "current"),         # (data_key, entity_slug)
    ("soc", "soc"),
)
BATTERY_MODULE_CALCULATED_SENSORS = (
    "soh",                          # Calculated from full/remaining capacity
)
```

- Slugs are used to generate entity unique IDs and translation keys (hyphens, no spaces)
- data_keys must match python-e3dc `Battery.properties` attribute names
- Keep in alphabetical order for maintainability

## Service Definitions

Service names (`SERVICE_<name>` constants):
- Correspond to `services.yaml` entry names (e.g., `SERVICE_SET_POWER_LIMITS` → `services.yaml` key `set_power_limits`)
- Translate hyphenated YAML keys to snake_case constants

Example:
```python
SERVICE_SET_POWER_LIMITS = "set_power_limits"  # Must match services.yaml key
```

## Platform List

`PLATFORMS` list must include all platform modules with entities:
```python
PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER,
]
```
- Only include platforms that have a corresponding `<platform>.py` file with setup
- Order: canonical HA platform order (sensor, binary_sensor, switch, etc.)

## Enums

Define behavior enums (e.g., `PowerMode`, `SetPowerMode`) as `Enum` subclasses:
- Use string values (e.g., `"0"`, `"1"`) that match RSCP protocol values
- Include helper methods (`has_value()`, `get_enum()`) for safe lookups
- Document enum semantics (e.g., "0=Idle, 1=Discharge, 2=Charge")

Example:
```python
class PowerMode(Enum):
    IDLE = "0"
    DISCHARGE = "1"
    CHARGE = "2"

    @classmethod
    def get_enum(cls, value: str) -> "PowerMode | None":
        return cls._value2member_map_.get(value, None)
```

## Backwards Compatibility

- Do **not** remove or rename constants that are part of the public config entry data
- Renaming sensor slugs breaks entity unique IDs → must provide migration in coordinator or entity registry
- Removing service names breaks automations → deprecate with warnings before removing

## Type Hints

- Always use type hints on tuple definitions: `tuple[tuple[str, str], ...]` (tuple of 2-tuples)
- Use `tuple[str, ...]` for single-element tuples

