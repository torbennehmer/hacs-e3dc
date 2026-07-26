---
description: "Use when modifying integration entry setup (async_setup_entry, async_unload_entry, async_migrate_entry), handling ConfigEntry lifecycle, coordinator initialization, platform forwarding, or service setup in the E3DC integration."
applyTo: "custom_components/e3dc_rscp/__init__.py"
---

# Integration Setup (__init__.py)

## Entry Lifecycle Pattern

**Setup Flow** (`async_setup_entry`):
1. Create `E3DCCoordinator` instance
2. Connect and perform first refresh (raises `ConfigEntryAuthFailed` or `ConfigEntryNotReady`)
3. Store coordinator in `hass.data[DOMAIN][entry.unique_id]`
4. Run device identification tasks: `async_identify_farm()`, `async_identify_sgready()`, `async_identify_wallboxes()`, `async_identify_batteries()`
5. Forward entry setup to all platforms in `PLATFORMS` list
6. Call `async_setup_services(hass)` once

**Unload Flow** (`async_unload_entry`):
- Use `async_unload_platforms(entry, PLATFORMS)` to clean up entities
- Remove coordinator from `hass.data[DOMAIN]` only if platforms unloaded successfully
- Always return unload status

## Migration Handling

- Check `config_entry.version`
- Create new data dict with required keys: `CONF_API_VERSION`, `CONF_PORT`, `CONF_FARMCONTROLLER`
- Use `hass.config_entries.async_update_entry(config_entry, data=new_data, version=X)`
- Return `True` on successful migration, `False` if no migration needed

## Exception Handling

- **`ConfigEntryAuthFailed`**: Authentication failure → re-raise immediately (HA will mark entry unusable)
- **Other exceptions**: Wrap in `ConfigEntryNotReady` with descriptive message (HA will retry)
- Never catch exceptions silently in setup

## Data Storage

- Always use `hass.data.setdefault(DOMAIN, {})`
- Key by `entry.unique_id` (set in config flow)
- Coordinator is the single source of truth for device state; do not cache state in separate dicts

## Platform Integration

- `PLATFORMS` list must match the platform files present (`sensor.py`, `button.py`, etc.)
- Forward entries via `async_forward_entry_setups(entry, PLATFORMS)` (plural) to allow HA to manage platform discovery
- Only add new platforms after they are fully implemented with entities and platform setup

## Service Setup

- Call `async_setup_services(hass)` once per integration (not per entry if only one instance)
- Ensure service YAML definitions in `services.yaml` match service call handlers
