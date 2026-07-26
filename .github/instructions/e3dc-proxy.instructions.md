---
description: "Use when working with E3DC device communication, RSCP protocol requests, pye3dc library integration, exception handling for device operations, or any low-level E3DC data fetching and control."
applyTo: "custom_components/e3dc_rscp/e3dc_proxy.py"
---

# E3DC Proxy Layer (e3dc_proxy.py)

## Mandatory Proxy Pattern

**CRITICAL**: `e3dc_proxy.py` is the ONLY place in the codebase where:
- `E3DC` class is instantiated or imported
- RSCP tag constants (`RscpTag`, `RscpType`, `PowermeterType`) are used
- `rscpFindTag()`, `rscpFindTagIndex()` helper functions are called
- Direct `sendRequest()` or `sendRequestTag()` calls are made
- Exception handling for pye3dc errors occurs

**Rule**: Do not import `E3DC`, `RscpTag`, or any pye3dc exception classes anywhere outside this file. All E3DC access must go through `E3DCProxy` methods.

## ThreadSafeE3DC Wrapper

```python
class ThreadSafeE3DC(E3DC):
    """Thread-safe wrapper with lock on sendRequest."""
    def sendRequest(self, *args, **kwargs):
        with self._lock:
            return super().sendRequest(*args, **kwargs)
```

- Ensures blocking `sendRequest` calls are serialized across threads
- Prevents race conditions in RSCP frame transmission
- Initialize in `E3DCProxy.__init__()`, never instantiate directly elsewhere

## @e3dc_call Decorator Pattern

All `E3DCProxy` methods must be decorated with `@e3dc_call`. The decorator:
1. Catches pye3dc exceptions and maps them to HA exceptions:
   - `NotAvailableError` → `HomeAssistantError("Communication Failure: E3DC not available")`
   - `SendError` → `HomeAssistantError("Communication Failure: Failed to send data")`
   - `AuthenticationError` → `ConfigEntryAuthFailed("Failed to authenticate with E3DC")`
   - `RSCPKeyError` → `ConfigEntryAuthFailed("Encryption Error with E3DC, key invalid")`
   - Other exceptions → `HomeAssistantError("Fatal error when talking to E3DC")`
2. Re-raises `HomeAssistantError` and `ConfigEntryAuthFailed` as-is
3. Logs all errors at `DEBUG` level with exception info
4. Converts low-level RSCP errors into HA domain exceptions

## Method Structure

All proxy methods follow this pattern:

```python
@e3dc_call
def method_name(self, param1: Type1, param2: Type2) -> dict[str, Any] | Type:
    """Fetch or control E3DC resource.

    Args:
        param1: Description
        param2: Description

    Returns:
        Structured dict or primitive type (never raw RSCP tuple)
    """
    # For high-level pye3dc methods:
    return self.e3dc.high_level_method(param1, keepAlive=True)

    # For direct RSCP requests:
    result_tuple = self.e3dc.sendRequest(
        (RscpTag.TAG_NAME, RscpType.TypeName, value),
        keepAlive=True,
    )

    # Convert raw tuple to structured dict:
    return {
        "key1": rscpFindTag(result_tuple, RscpTag.RESULT_TAG)[2],
        "key2": rscpFindTagIndex(result_tuple, RscpTag.RESULT_TAG),
    }
```

## keepAlive=True Requirement

Always pass `keepAlive=True` to:
- `self.e3dc.poll(keepAlive=True)`
- `self.e3dc.sendRequest(..., keepAlive=True)`
- `self.e3dc.sendRequestTag(..., keepAlive=True)`
- Any high-level method with this parameter

This enables connection reuse and reduces latency across polling cycles.

## Return Value Pattern

- **Never return raw RSCP tuples** (e.g., `(RscpTag, RscpType, value)`)
- **Always return structured data**:
  - Simple values: `str`, `int`, `bool`, `dict[str, Any]`, `list[dict[str, Any]]`
  - Complex results: Always `dict[str, Any]` with descriptive keys
- Example:
  ```python
  # ❌ Bad: return rscpFindTag(data, RscpTag.SOME_TAG)[2]
  # ✅ Good: return {"temperature": rscpFindTag(data, RscpTag.TEMP_TAG)[2], ...}
  ```

## Exception Handling

Coordinator and other callers catch `HomeAssistantError` and `ConfigEntryAuthFailed`:
- Don't catch exceptions in proxy methods unless wrapping in a higher-level exception
- Let `@e3dc_call` decorator handle all pye3dc exceptions
- Document which exceptions each method can raise (via docstring)

Example:
```python
@e3dc_call
def connect(self, config: dict[str, Any] | None = None):
    """Connect to E3DC.

    Raises:
        ConfigEntryAuthFailed: If credentials or RSCP key invalid
        HomeAssistantError: If connection fails for other reasons
    """
    self.e3dc = ThreadSafeE3DC(...)  # May raise auth errors
```

## Configuration & Connection

- **Constructor**: Accept `ConfigEntry` or `dict[str, str | int]` with keys `CONF_HOST`, `CONF_USERNAME`, `CONF_PASSWORD`, `CONF_RSCPKEY`, `CONF_PORT`
- **`connect()` method**: Instantiate `ThreadSafeE3DC`, store optional config dict for powermeter lookups
- **`disconnect()` method**: Check `isConnected()` before closing, set `self.e3dc = None`

## Future Refactoring Goal

Methods in this file are candidates for upstreaming to `python-e3dc`:
1. High-level helper methods (e.g., `get_sgready_state()`, `set_power_limits()`)
2. Exception handling via decorator pattern
3. Structured return value normalization

If a method becomes stable and widely used, propose PR to `python-e3dc` to reduce maintenance burden here.

## Coordinator Integration Pattern

Coordinator calls proxy methods inside `async_add_executor_job()`:
```python
# In coordinator._async_update_data():
self.e3dc_proxy.connect()  # Blocking, wrapped in executor
data = self.e3dc_proxy.poll(keepAlive=True)  # Blocking, wrapped in executor
```

Proxy methods are **always blocking** (synchronous); wrapping in executor is coordinator's responsibility.
