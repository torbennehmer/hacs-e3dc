# Copilot Instructions – hacs-e3dc

## Project Overview

This repository contains a **Home Assistant Custom Component (HACS)** for E3/DC solar storage systems.
It integrates with E3/DC devices via the **RSCP protocol** (Remote Storage Control Protocol).

## Architecture & Key Dependencies

### This repo
- Custom HA component: `custom_components/e3dc_rscp/`
- Language: Python 3.11+, follows Home Assistant component conventions
- Linter: `ruff` (config in `pyproject.toml`)
- Dev environment: `.devcontainer.json` / VS Code devcontainer

### Upstream dependency (read-only reference)
- **python-e3dc**: https://github.com/fsantini/python-e3dc
  - Provides `E3DC` class for connection/authentication and RSCP tag constants
  - Do NOT reimplement logic already present there; call through the library
  - Follow RSCP tag-handling rules defined in the `RSCP / E3/DC protocol` section below

### Reference libraries for RSCP tags & protocol
- **rscp-lib (RscpTags.py)**: https://github.com/tobias-terhaar/rscp-lib/blob/main/rscp_lib/RscpTags.py
  - Comprehensive RSCP tag enum; use only as a secondary comparison source for missing tags
- **e3dc_rscp_connect**: https://github.com/tobias-terhaar/e3dc_rscp_connect
  - Shows practical usage patterns for direct RSCP requests; useful when python-e3dc doesn't expose a tag

### Downstream dependent
- **hacs-e3dc-maestro**: https://github.com/TommiG1/hacs-e3dc-maestro
  - Extended fork that depends on this component
  - Avoid breaking changes to the public interface (config entries, entity unique IDs, service calls)

## Development Conventions

### Home Assistant specifics
- All entities inherit from HA base classes (`SensorEntity`, `BinarySensorEntity`, etc.)
- Use `DataUpdateCoordinator` pattern for polling; never fetch data directly in entity methods
- Config flow must remain backwards-compatible; bump `VERSION` on schema changes and provide migration
- If configuration entries are missing or invalid, provide a detailed error and remediation options, then ask the developer whether to require manual correction, retry with adjusted input, or abort setup
- Translations go into `translations/` (en.json minimum); add keys before referencing them in code
- Follow HA's `CoordinatorEntity` pattern; never store state in entities directly
- Coding best practices must follow established Home Assistant integration rules. Fall back to Python best practices when HA conventions are not specific.

### RSCP / E3/DC protocol & Mandatory Proxy Pattern

**CRITICAL RULE**: All E3DC communication must go through `E3DCProxy` in `e3dc_proxy.py`. This is the ONLY place where:
- `E3DC` class is instantiated
- RSCP tag constants (`RscpTag`, `RscpType`) are used directly
- `sendRequest()` / `sendRequestTag()` calls are made
- `rscpFindTag()`, `rscpFindTagIndex()` are called
- pye3dc exceptions are caught and converted to HA exceptions

**Forbidden**: Do not import `E3DC`, `RscpTag`, or pye3dc exception classes in `coordinator.py`, `services.py`, or entity files. Call proxy methods instead.

Additional rules:
- Tag constants: use only `python-e3dc` tag constants; `rscp-lib` is comparison-only and must not be used as an implementation source
- If a required tag is missing in `python-e3dc`, fail the operation clearly and recommend raising a PR to `python-e3dc`; do not apply temporary local tag workarounds
- All RSCP communication is synchronous blocking I/O – coordinator wraps proxy calls in `hass.async_add_executor_job()`
- All proxy methods must be `@e3dc_call` decorated to handle exceptions uniformly
- Proxy methods must use `keepAlive=True` on all `sendRequest` / `sendRequestTag` calls
- Proxy methods return **structured data** (dicts), never raw RSCP tuples
- Connection errors should be caught and surfaced as `UpdateFailed` in the coordinator, not as exceptions
- Time values from E3/DC are Unix timestamps in **local device time**, not UTC – handle timezone offset explicitly in coordinator or entity, never in proxy

### Code style
- Ruff enforced (`ruff check` + `ruff format`); run before committing
- Type hints required on all public functions/methods
- No bare `except`; always catch specific exception types
- Log at `DEBUG` for per-poll noise, `WARNING` for recoverable issues, `ERROR` for non-recoverable

### Dev Container specifics
- The HA dev Container uses /usr/local/bin/python
- All packages are installed systemwide using /usr/local/bin/pip
- /usr/local/bin is prioritized in the path env
- no venv is in use

## Development Commands

### Quick Start for Development
```bash
scripts/setup        # Install all dependencies (requirements.txt + requirements-dev.txt)
scripts/ruff         # Lint and format code (ruff check --fix && ruff format)
scripts/typecheck    # Type checking with Pyright
scripts/develop      # Run Home Assistant dev server on port 8124 (HA web UI at http://localhost:8124)
```

### CI/CD Pipeline
- **lint.yml**: Runs `ruff` linter on Python 3.13 (all commits)
- **validate.yml**: Additional validation checks (all commits)
- **release.yml** / **release-drafter.yml**: Automated release on tag

### Pre-Commit Workflow
Before pushing changes:
```bash
scripts/ruff         # Must pass with no fixes needed
scripts/typecheck    # All type hints must pass Pyright
```

## Common Development Patterns

### Entity Creation Pattern

All entities inherit `CoordinatorEntity` + platform base and share one constructor shape:

```python
def __init__(
    self,
    coordinator: E3DCCoordinator,
    description: E3DCSensorEntityDescription,  # per-platform subclass
    uid: str,
    device_info: DeviceInfo | None = None,
) -> None:
    super().__init__(coordinator)
    self.entity_description = description
    self._attr_unique_id = f"{uid}_{description.key}"
```

Key facts:
- `uid` is **passed in**, never derived from the coordinator — child devices pass their own uid
- State is read with `self.coordinator.data.get(self.entity_description.key)` — the description `key` *is* the coordinator data key; there is no separate `data_key` field
- Each platform defines its own `E3DC*EntityDescription` subclass **in its own platform file**, not in `const.py`

**Details:** [entity platform instructions](/.github/instructions/entity-platforms.instructions.md)

### Coordinator Lifecycle

**Initialization (called once in `async_setup_entry`):**
1. Create `coordinator = E3DCCoordinator(hass, config_entry)`
2. Call `await coordinator.async_connect()` → Establish E3DC connection
3. Query static properties (capacity, max power, etc.)
4. Discover child devices: `await coordinator.async_identify_wallboxes()`, `async_identify_batteries()`, `async_identify_sgready()`
5. Call `await coordinator.async_config_entry_first_refresh()` → Trigger first poll + raise if failed

**Polling** (`_async_update_data`, every 10s) calls a series of `_load_and_process_*()` helpers that each
write into the shared `self._mydata` dict and return it. Several are conditional:
- `_update_guard_powersettings` / `_update_guard_wallboxsettings` suppress a reload while a user-initiated
  write is in flight, so the UI does not flicker back to the old value
- battery data only when `self.create_battery_devices`
- statistics only when `self._next_stat_update < time()`

Exceptions propagate to `DataUpdateCoordinator`, surface as `UpdateFailed`, and entities go unavailable
with automatic backoff.

**For detailed coordinator instructions, see:** [coordinator.py instructions](/.github/instructions/coordinator.instructions.md)

### E3DC Proxy Pattern (Critical)

**MANDATORY: All E3DC communication MUST go through `e3dc_proxy.py`**

```python
# e3dc_proxy.py - the ONLY place E3DC imports/calls happen
from e3dc import E3DC
from e3dc._rscpTags import RscpTag, RscpType

class E3DCProxy:
    @e3dc_call
    def get_batteries(self) -> list[dict[str, Any]]:
        """Return structured battery data (never raw RSCP tuples)."""
        return self.e3dc.get_batteries(keepAlive=True)
```

**Known violation to fix, not to copy:** [sensor.py](custom_components/e3dc_rscp/sensor.py#L6) imports
`PowermeterType` straight from `e3dc._rscpTags`. Do not use it as precedent for new code.

**Exception handling via `@e3dc_call` decorator:**
- Catches pye3dc exceptions and converts to HA domain exceptions
- `AuthenticationError`, `RSCPKeyError` → `ConfigEntryAuthFailed`
- `NotAvailableError`, `SendError` → `HomeAssistantError`

**Coordinator calls proxy via executor:**
```python
# In coordinator.py - DO NOT call proxy methods directly
status = await self.hass.async_add_executor_job(self.proxy.poll)
```

**For detailed proxy instructions, see:** [e3dc_proxy.py instructions](/.github/instructions/e3dc-proxy.instructions.md)

### Service Implementation Pattern

Schemas, handlers and registration all live in `services.py` (**not** `const.py`). Every schema takes the
device via `ATTR_DEVICEID` (no underscore):

```python
SCHEMA_MANUAL_CHARGE = vol.Schema(
    {
        vol.Required(ATTR_DEVICEID): str,
        vol.Optional(ATTR_CHARGE_AMOUNT): vol.All(int, vol.Range(min=0)),
    }
)

hass.services.async_register(
    domain=DOMAIN,
    service=SERVICE_MANUAL_CHARGE,
    service_func=async_call_manual_charge,   # thin wrapper -> _async_manual_charge(hass, call)
    schema=SCHEMA_MANUAL_CHARGE,
)
```

The handler resolves the device id to a coordinator through the device registry (following `via_device_id`
for wallbox/battery child devices), then delegates to a coordinator method.

**For detailed service instructions, see:** [services.py instructions](/.github/instructions/services.instructions.md)

### Error Handling Pattern

**Proxy layer** (`e3dc_proxy.py`):
- Catches pye3dc exceptions via `@e3dc_call`
- Converts to HA domain exceptions

**Coordinator layer** (`coordinator.py`):
- `try/except HomeAssistantError` in `_async_update_data()`
- Logs at appropriate level, lets DataUpdateCoordinator surface as `UpdateFailed`
- Retries automatically per HA's exponential backoff

**Service layer** (`services.py`):
- Validate input schema before calling coordinator
- Catch exceptions and raise `ServiceValidationError` for user-facing messages

## Common Gotchas & Mistakes

### Critical Rules (Breaking Changes)

1. **Never rename entity `unique_id`** after creation
   - Format: `{coordinator_uid}_{entity_key}` (immutable)
   - Breaking change affects existing HA installations and hacs-e3dc-maestro

2. **Always wrap blocking proxy calls in executor**
   ```python
   # ✓ CORRECT
   await self.hass.async_add_executor_job(self.proxy.poll)

   # ✗ WRONG - blocks event loop
   self.proxy.poll()
   ```

3. **Always use `keepAlive=True` in proxy methods**
   ```python
   # ✓ CORRECT
   data = self.e3dc.poll(keepAlive=True)

   # ✗ WRONG - loses connection reuse
   data = self.e3dc.poll()
   ```

4. **Proxy must return structured dicts, never raw RSCP tuples**
   ```python
   # ✓ CORRECT
   return {"power": 1234, "soc": 45.2}

   # ✗ WRONG - confuses downstream code
   return self.e3dc.poll()  # Raw pye3dc tuple
   ```

### Common Mistakes

- **Importing `E3DC` or `RscpTag` outside `e3dc_proxy.py`**: Breaks proxy isolation, causes merge/refactor pain
- **Storing state in entities**: Entities must get state from `coordinator.data` only
- **Timezone offset bugs**: E3DC timestamps are local device time (not UTC) – must handle offset in coordinator/entity, not proxy
- **Not updating diagnostics** when adding new features → users can't troubleshoot
- **Config flow schema changes without version bump**: Breaks migration path for existing installs
- **Missing translation keys**: Must exist in `strings.json` BEFORE referenced in code

### Testing Gaps (Known Limitations)

- No unit tests yet (integration-level only via HA dev container)
- Internet unavailable scenarios need pye3dc library improvements
- Device unavailable state tracking (available property not yet set appropriately)

## When Adding New Sensors/Features

### Checklist: Adding a New Sensor

**Step 1: Data Availability**
1. Check if `python-e3dc` already exposes the data via a high-level method or RSCP tag constant
2. Use `rscp-lib` `RscpTags.py` only as secondary comparison source (don't implement from it)
3. If tag missing in `python-e3dc`, open PR to `python-e3dc` (no local tag workarounds)

**Step 2: Proxy Method** (if new E3DC data needed)
1. Add `@e3dc_call` decorated method to `E3DCProxy` in [e3dc_proxy.py](/.github/instructions/e3dc-proxy.instructions.md)
2. Return structured dict (not raw RSCP tuples)
3. Use `keepAlive=True` on all device calls
4. Document exceptions it can raise

**Step 3: Coordinator**
1. In [coordinator.py](/.github/instructions/coordinator.instructions.md), call new proxy method via `async_add_executor_job()`
2. Add result to `self._mydata` dict in `_load_and_process_*()` method
3. Handle exceptions (let DataUpdateCoordinator convert to UpdateFailed)

**Step 4: Entity**
1. Add an entity description to the platform file ([entity platforms](/.github/instructions/entity-platforms.instructions.md))
2. Set `translation_key`, `device_class`, `state_class`, `native_unit_of_measurement`
3. Set `key` to match the coordinator data dict key \u2014 the same `key` also forms the unique_id

**Step 5: Translations**
1. Add translation key to [strings.json](strings.json) BEFORE referencing in code
2. Create entry under `entity -> {platform} -> {translation_key}`
   ```json
   "entity": {
     "sensor": {
       "new_sensor": {
         "name": "New Sensor",
         "state_attributes": {...}
       }
     }
   }
   ```

**Step 6: Diagnostics** (MANDATORY)
1. Update [diagnostics.py](/.github/instructions/diagnostics.instructions.md)
2. Add data collection to `_collect_data()` method
3. Add redaction pattern if sensitive (MAC, serial, credentials)
4. Use `_query_data_for_dump()` wrapper for error resilience

**Step 7: Testing & Code Quality**
```bash
scripts/ruff         # Must pass with no fixes
scripts/typecheck    # All type hints must pass
```

**Step 8: Documentation** (if service added)
1. Update [README.md](README.md) with service details

### Module-Specific Instructions

For detailed rules on each module, refer to:
- [entity platforms](/.github/instructions/entity-platforms.instructions.md) - sensor, binary_sensor, switch, button, number
- [coordinator.py](/.github/instructions/coordinator.instructions.md) - Data polling, lifecycle
- [e3dc_proxy.py](/.github/instructions/e3dc-proxy.instructions.md) - E3DC communication
- [services.py](/.github/instructions/services.instructions.md) - Service registration & delegation
- [battery_manager.py](/.github/instructions/battery-manager.instructions.md) - Battery device lifecycle
- [diagnostics.py](/.github/instructions/diagnostics.instructions.md) - Diagnostic data collection
- [config_flow.py](/.github/instructions/config-flow.instructions.md) - Config setup flow
- [__init__.py](/.github/instructions/integration-setup.instructions.md) - Integration lifecycle
- [const.py](/.github/instructions/const-schema.instructions.md) - Entity descriptions, constants
- [utils.py](/.github/instructions/utils.instructions.md) - Utility functions, discovery

### Diagnostics Sync – Global Rule

**MANDATORY**: Every time new data, feature, or capability is added to the integration, the diagnostics dump (`diagnostics.py`) must be updated in the same commit.

When adding:
- **New sensor entity** → Add corresponding diagnostics data point to `_collect_data()`
- **New service capability** → Add relevant device state/config to diagnostics
- **New device identification feature** → Add to diagnostics (farm controller, wallboxes, batteries, SGReady, etc.)
- **New coordinator data key** → Add to diagnostics
- **New sensitive data fields** → Add redaction pattern to `_redact_regex`

This ensures:
- Users can always download complete diagnostics for troubleshooting new features
- Sensitive information (MAC, serial, credentials) is consistently redacted
- Integration state is transparent and debuggable
- Downstream components can reference diagnostics in bug reports

**Pattern**: Use `_query_data_for_dump()` wrapper on all data queries to ensure error resilience (diagnostics must never raise exceptions).

## Out of Scope for Copilot
- Do NOT remove or rename existing entity unique IDs (breaks hacs-e3dc-maestro and existing HA installations)