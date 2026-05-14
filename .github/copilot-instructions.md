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
- Coding best practices must follow established Homeassistant integration rules. Fall back to Python best practices when HA conventions are not specific.

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
- /usr/local/bin is priorized in the path env
- no venv is in use

## When Adding New Sensors/Features
1. Check if `python-e3dc` already exposes the required data via a high-level method or RSCP tag constant
2. Use `rscp-lib` `RscpTags.py` only as a secondary comparison source to confirm naming or identify potential missing tags
3. If the required tag is not available in `python-e3dc`, stop and open a PR against `python-e3dc` (no local tag injection workaround)
4. **NEW E3DC DATA**: Add a new `@e3dc_call` decorated method to `E3DCProxy` that:
   - Fetches or controls the data via pye3dc or direct RSCP calls
   - Returns structured dict (not raw RSCP tuples)
   - Uses `keepAlive=True` on all device calls
   - Documents which exceptions it can raise
5. In coordinator or entity, call the new proxy method via `hass.async_add_executor_job(proxy_method, ...)`
6. Add the entity to `sensor.py` / appropriate platform file
7. Add translation keys to all `translations/*.json` files
8. Update `README.md` in case you add services

**Never**: Add E3DC data fetching directly in coordinator or entity methods. Always add a proxy method first.

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