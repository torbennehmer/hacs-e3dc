---
description: "Use when adding diagnostics data collection, redacting sensitive information, handling errors in diagnostic queries, or ensuring diagnostic data stays synchronized with new features."
applyTo: "custom_components/e3dc_rscp/diagnostics.py"
---

# Diagnostics (diagnostics.py)

## Purpose

Diagnostics provide a safe, redacted dump of device state and configuration for troubleshooting. When users report issues, they can share diagnostics without exposing personal data (MAC address, serial number, IP).

## Entry Point

```python
async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for our config entry."""
    dumper = _DiagnosticsDumper(hass, entry)
    dumper.create_dump()
    return dumper.get_dump()
```

- Called by HA diagnostics system when user requests diagnostics
- Returns complete device state snapshot
- Must never raise exceptions; all errors are caught internally

## _DiagnosticsDumper Class Pattern

```python
class _DiagnosticsDumper:
    """Helper class to collect diagnostic dump in failsafe way."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry):
        """Set up references to coordinator, proxy, and E3DC."""
        self.hass = hass
        self.entry = entry
        self.coordinator = self.hass.data[DOMAIN][self.entry.unique_id]
        self.proxy = self.coordinator.proxy
        self.e3dc = self.proxy.e3dc
        self.result: dict[str, Any] = {}

    def create_dump(self):
        """Collect data and redact private information."""
        self._collect_data()  # Gather all information
        self._redact_private_information(self.result)  # Remove sensitive data

    def get_dump(self) -> dict[str, Any]:
        """Return the collected dump."""
        return self.result
```

- Single entry point: `create_dump()` (coordinates collection and redaction)
- All data collection deferred to `_collect_data()` (isolates where new data goes)
- All redaction in `_redact_private_information()` (centralized sensitive data handling)

## Data Collection Pattern

```python
def _collect_data(self):
    """Collect diagnostic data from all sources."""
    self.result: dict[str, Any] = {
        # Coordinator data (current state)
        "current_data": self.coordinator.data,

        # High-level pye3dc methods (safe, structured)
        "get_system_info": self._query_data_for_dump(self.e3dc.get_system_info),
        "get_system_status": self._query_data_for_dump(self.e3dc.get_system_status),

        # Wallbox and battery data
        "get_wallbox_data": self._query_data_for_dump(self.e3dc.get_wallbox_data),
        "get_batteries_data": self._query_data_for_dump(self.e3dc.get_batteries_data),

        # Low-level RSCP queries (for advanced debugging)
        "EMS_REQ_GET_MANUAL_CHARGE": self._query_data_for_dump(
            lambda: self.e3dc.sendRequestTag(
                RscpTag.EMS_REQ_GET_MANUAL_CHARGE, keepAlive=True
            )
        ),

        # Proxy-managed config
        "e3dc_config": self.proxy.e3dc_config,

        # Feature flags
        "is_farm_controller": self.coordinator.is_farm_controller(),
    }
```

- **Coordinator data**: Current entity state
- **High-level methods**: Stable, structured data (use instead of raw RSCP when possible)
- **Low-level RSCP**: Only when high-level method unavailable
- **Config data**: Device setup and powermeter configuration
- **Feature flags**: Whether farm controller, SGReady, etc.

## Error Handling Pattern

```python
def _query_data_for_dump(self, call: Callable[[], Any]) -> Any:
    """Query data point with exception handling."""
    try:
        return call()
    except Exception as ex:
        # Capture exception without raising; diagnostic dump must complete
        return {"exception": format_exception(ex)}
```

- **Resilient**: Never raises exceptions
- **Informative**: Returns formatted exception traceback for debugging
- All data points wrapped with this pattern (no naked calls)
- Device connectivity issues don't break entire diagnostics dump

## When Adding New Data to Integration

**Golden Rule**: Whenever new sensor, property, or feature is added, also add its diagnostics entry:

```python
# NEW SENSOR ADDED: battery-remaining-energy
# In sensor.py: Add E3DCBinarySensorEntityDescription
# IN DIAGNOSTICS: Add corresponding data point

# In _collect_data():
"get_battery_data": self._query_data_for_dump(
    self.proxy.get_battery_data  # Or self.e3dc.get_battery_data
),
```

- Add to `_collect_data()` immediately after adding new feature
- Use proxy method if data fetching involves RSCP
- Use pye3dc high-level method if available
- Wrap with `_query_data_for_dump()` for error handling

Pattern for new wallbox feature:

```python
# NEW: Wallbox phase information
"wallbox_phases": self._query_data_for_dump(
    lambda: self.e3dc.get_wallbox_data(wbIndex=0)  # Gets all phases per wallbox
),
```

## Redaction Pattern

```python
_redact_regex = re.compile("(system-mac|macAddress|serial)", re.IGNORECASE)

def _redact_private_information(self, data: Any):
    """Redact sensitive information recursively."""
    if isinstance(data, dict | list):
        for key, value in (
            data.items() if isinstance(data, dict) else enumerate(data)
        ):
            # Redact string values with sensitive key names
            if (
                isinstance(value, str)
                and isinstance(key, str)
                and _redact_regex.search(key) is not None
            ):
                data[key] = f"{value[:3]}<redacted>"

            # Recurse into nested structures
            self._redact_private_information(value)
```

- **Regex patterns**: Match key names (case-insensitive)
- **Redaction strategy**: Keep first 3 chars for context, mask rest (e.g., "AA:BB:CC:...<redacted>")
- **Recursive**: Handles dicts, lists, nested structures
- **Safe**: Non-matching keys are preserved as-is

## Sensitive Data to Redact

The regex actually in force today is narrow — it covers **three** key patterns only:

```python
_redact_regex = re.compile("(system-mac|macAddress|serial)", re.IGNORECASE)
```

That means MAC addresses and serial numbers are masked, and **nothing else is**. Do not assume
usernames, IP addresses, tokens or passwords are filtered out — they are not. If you add a data source
that can surface any of those, you must extend the regex in the same change, or keep the value out of
the dump entirely.

Categories that warrant redaction when introduced:
- MAC addresses (network identity) — covered
- Serial numbers (device identification) — covered
- Credentials, API keys, tokens — **not covered**; never put them in the dump
- Usernames and IP addresses — **not covered**; add a pattern before dumping them

## When to Add Redaction Rules

If new data contains PII or credentials:
1. Add the key pattern to `_redact_regex`
2. Keep `re.IGNORECASE`; the match is against the **key name**, not the value
3. Download a diagnostics dump and confirm the value is masked

```python
_redact_regex = re.compile(
    "(system-mac|macAddress|serial|userName)",  # userName added
    re.IGNORECASE,
)
```

## Accessing Diagnostics Data

Users access via HA UI:
- Settings → Devices & Services → E3DC integration → Options → Download diagnostics
- File contains JSON dump of all queried data
- Redacted data shows: `"macAddress": "AA:BB:C<redacted>"`

Developers can view raw dump:

```python
# In HA UI, open developer tools → Services
# Call homeassistant.get_diagnostics with entry_id
```

## Testing Diagnostics

After adding new data points:

```bash
# Trigger diagnostics collection manually
# Check that:
# 1. No exceptions are raised
# 2. All expected keys are present
# 3. Sensitive data is redacted
# 4. Nested structures are preserved
```

## Error Logging

Errors in diagnostic queries are logged but never fatal:

```python
def _query_data_for_dump(self, call: Callable[[], Any]) -> Any:
    """Query data point with logging."""
    try:
        return call()
    except Exception as ex:
        _LOGGER.debug("Diagnostics query failed: %s", ex)  # Or WARNING if critical
        return {"exception": format_exception(ex)}
```

- Debug-level logging for expected failures (e.g., unsupported feature)
- Warning-level logging for unexpected errors (e.g., device offline)
- Full traceback included in returned data for HA logs

## Backwards Compatibility

- Never remove diagnostic data points (users may reference them)
- Renaming keys is acceptable (update redaction patterns)
- Adding new points is always safe
- If data structure changes, document in CHANGELOG

## Performance Considerations

- Diagnostics collection is **synchronous** (blocks briefly)
- Minimize expensive queries (use cached data where possible)
- Use `keepAlive=True` on RSCP calls to reuse connection
- Don't call high-volume polling methods (e.g., `poll()` might be called frequently; snapshot is fine)

## Global Rule: Diagnostics Sync

**Every time you add:**
- New sensor entity → add diagnostics data point
- New service capability → add relevant state/config to diagnostics
- New device identification feature → add to diagnostics
- New coordinator data key → add to diagnostics

**Check:**
1. Is the data needed for troubleshooting? (If yes, add to diagnostics)
2. Does it contain PII? (If yes, add to redaction patterns)
3. Is error handling in place? (Always use `_query_data_for_dump()`)

## Example: Adding New Feature

```python
# Step 1: Add new sensor in sensor.py
# Step 2: Add coordinator method to fetch data
# Step 3: ADD TO DIAGNOSTICS:

def _collect_data(self):
    self.result: dict[str, Any] = {
        # ... existing entries ...

        # NEW: SGReady state info (for troubleshooting SGReady sensors)
        "get_sgready_state": self._query_data_for_dump(
            self.proxy.get_sgready_state  # Proxy method returns structured dict
        ),
    }

# Step 4: If needed, add redaction patterns
```

This ensures complete integration between feature development and diagnostics.
