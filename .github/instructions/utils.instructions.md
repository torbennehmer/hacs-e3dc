---
description: "Use when adding utility functions, helpers, discovery flows, farm controller initialization, or integration initialization logic that doesn't fit into other modules."
applyTo: "custom_components/e3dc_rscp/utils.py"
---

# Utilities (utils.py)

## Purpose

`utils.py` houses integration-level helper functions that don't belong to the proxy, coordinator, services, or battery manager classes. This is a catch-all for orchestration and initialization logic.

## Farm Controller Discovery Pattern

```python
async def initialize_farm_controller_flow_if_needed(
    hass,
    proxy: E3DCProxy,
    username: str | None,
    password: str | None,
    rscp: str | None,
):
    """Check if device is a farm member and initiate farm controller config flow."""
    # NOTE: as written today this is a *blocking* call made directly from async code.
    # It should be `await hass.async_add_executor_job(proxy.get_remote_control_ip)`.
    # Treat the current form as known debt - do not copy it into new code.
    remote_control_ip: str | None = proxy.get_remote_control_ip()

    if not remote_control_ip:
        return  # Not a farm member

    # Parse host:port from remote_control_ip
    parts = remote_control_ip.rsplit(":", 1)
    if len(parts) != 2:
        _LOGGER.warning("Invalid remote control IP format: %s", remote_control_ip)
        return

    host, port_str = parts
    try:
        port = int(port_str)
    except ValueError:
        _LOGGER.warning("Invalid port in remote control IP: %s", remote_control_ip)
        return

    # Check if farm controller entry already exists
    controller_found = False
    for entry in hass.config_entries.async_entries(DOMAIN):
        if (entry.data.get(CONF_HOST) == host and
            entry.data.get(CONF_PORT) == port):
            controller_found = True
            break

    if controller_found:
        return  # Already set up

    # Initiate config flow for farm controller
    _LOGGER.debug("Initiating farm controller flow for %s:%d", host, port)
    await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": SOURCE_INTEGRATION_DISCOVERY,
            "title_placeholders": {
                "name": f"E3DC Farm Controller at {host}"
            },
        },
        data={
            CONF_HOST: host,
            CONF_PORT: port,
            CONF_USERNAME: username,
            CONF_PASSWORD: password,
            CONF_RSCPKEY: rscp,
        },
    )
```

- Called once per device during setup (from `__init__.async_setup_entry`)
- Parse host:port from IP string
- Check if farm controller already configured (avoid duplicates)
- Initiate sub-flow with discovery source and pre-filled credentials
- Credentials inherited from member device (convenience for user)
- New proxy calls added here **must** go through `hass.async_add_executor_job()`

## Integration Discovery Flow

- Discovery is handled in `config_flow.py` via `async_step_ssdp()`
- Utils may contain helper functions for discovery processing
- SSDP matching rules are declared in `manifest.json`

## Helper Function Guidelines

When adding new utility functions:

1. **Single Responsibility**: Function does one thing clearly
2. **Async Where Needed**: Use `async/await` if coordinating HA APIs or calling proxy
3. **Error Handling**: Catch and log specific exceptions; don't let failures crash integration
4. **Type Hints**: All public functions must have type hints on parameters and return
5. **Logging**: Log at appropriate level (`DEBUG` for discovery details, `WARNING` for user action needed, `ERROR` for integration failures)

Example pattern:

```python
async def helper_function(
    hass: HomeAssistant,
    param1: str,
    param2: int,
) -> dict[str, Any] | None:
    """Brief one-line description.

    Args:
        hass: Home Assistant instance
        param1: Description
        param2: Description

    Returns:
        Result dict or None if operation failed

    Raises:
        HomeAssistantError: If specific condition occurs
    """
    try:
        # Implementation
        result = await hass.async_add_executor_job(blocking_function)
        _LOGGER.debug("Operation succeeded: %s", result)
        return result
    except SpecificException as ex:
        _LOGGER.warning("Operation failed: %s", ex)
        return None
```

## Executor Wrapping

Always use `hass.async_add_executor_job()` for blocking operations:

```python
# ❌ Bad: Direct proxy call
remote_ip = proxy.get_remote_control_ip()

# ✅ Good: Wrapped in executor
remote_ip = await hass.async_add_executor_job(proxy.get_remote_control_ip)
```

- Proxy methods are blocking (synchronous I/O)
- Never call blocking functions directly in async context
- Executor runs them in thread pool

## Caching & Performance

Avoid expensive re-computation:

```python
_cached_discovery_results: dict[str, Any] = {}

async def get_discovery_results(hass: HomeAssistant, key: str) -> dict[str, Any]:
    """Get discovery results with caching."""
    if key in _cached_discovery_results:
        return _cached_discovery_results[key]

    # Compute result
    result = {...}
    _cached_discovery_results[key] = result
    return result
```

- Module-level cache for discovery results or repeated queries
- Clear cache on integration reload if needed
- Cache keys must be stable across sessions

## Integration Configuration Helpers

Functions to assist setup process:

```python
def get_default_configuration() -> dict[str, Any]:
    """Return default configuration values."""
    return {
        CONF_PORT: RSCP_PORT,
        CONF_API_VERSION: 2,
        CONF_FARMCONTROLLER: False,
    }

async def validate_configuration(
    hass: HomeAssistant,
    config_data: dict[str, str],
) -> tuple[bool, str | None]:
    """Validate configuration before entry creation.

    Returns:
        (is_valid, error_message_if_invalid)
    """
    # Validation logic
    return True, None
```

- Provide sane defaults for new entries
- Centralize complex validation logic
- Return structured results (not bare booleans)

## Integration Update / Migration Helpers

If needed for migrations:

```python
async def migrate_entry_data(
    hass: HomeAssistant,
    entry: ConfigEntry,
    old_version: int,
    new_version: int,
) -> dict[str, Any]:
    """Transform entry data during migration."""
    data = dict(entry.data)

    if old_version < 2:
        # Migrate to version 2
        data[CONF_API_VERSION] = 2
        data[CONF_PORT] = RSCP_PORT

    return data
```

- Called from `async_migrate_entry()` in `__init__.py`
- Transform and return updated data dict
- Keep migrations separate and versioned

## Backwards Compatibility

- Preserve function signatures; never remove or reorder parameters
- If adding parameters, make them optional with sensible defaults
- Document breaking changes in changelog before making them
- Test migration flows when changing data structures

## Testing & Validation

- Keep utilities testable: pure functions > side effects
- Mock `hass` and `proxy` in unit tests
- Test error paths (missing fields, network errors, etc.)
- Log enough detail for debugging without leaking sensitive data (no passwords in logs)
