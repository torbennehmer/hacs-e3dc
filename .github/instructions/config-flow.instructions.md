---
description: "Use when building config flow steps, user/step forms, authentication, reauth flows, discovery handling, SSDP integration, or configuration validation in the E3DC integration setup."
applyTo: "custom_components/e3dc_rscp/config_flow.py"
---

# Config Flow (config_flow.py)

## Flow Architecture

- Inherit from `ConfigFlow` for new entry flows, `OptionsFlow` for reconfiguration
- Use `@staticmethod` decorators on step methods for side-effect-free validation
- Step naming: `async_step_<name>()` (e.g., `async_step_user`, `async_step_ssdp_confirm`)
- Always return `FlowResult` (use `self.async_create_entry()` for completion, `self.async_show_form()` for input)

## Discovery, Reauth & Reconfigure

- **Discovery**: `async_step_ssdp()` handles auto-discovered devices (extract hostname from SSDP data)
- **Reauth**: `async_step_reauth()` → `async_step_reauth_confirm()` when an existing entry's auth fails;
  re-request credentials and update the entry in place
- **Reconfigure**: `async_step_reconfigure()` → `async_step_reconfigure_credentials()` lets a user change
  connection settings on an already-configured entry
- **Confirmation**: Show a summary of the discovered device; user confirms setup intent

All four of these flows exist in the file — when you touch validation logic, update every path, not just
`async_step_user`.

## Form Validation & Error Handling

- Use `voluptuous.Schema` with selectors (`TextSelector`, `NumberSelector`, etc.)
- **Validation**: build an `E3DCProxy` and call `self._proxy.connect()` inside an executor job. There is no
  `E3DCProxy.try_connect()` helper — `connect()` is the entry point and it raises on failure.
  - `ConfigEntryAuthFailed` or auth error → set error key `ERROR_AUTH_INVALID`, re-show form
  - Connection/network error → set error key `ERROR_CANNOT_CONNECT`, re-show form
- Always show translated error messages via `errors[key]`

## Data Storage & Versioning

- **Configuration data** must include:
  - `CONF_USERNAME`, `CONF_PASSWORD` (authentication credentials)
  - `CONF_HOST`, `CONF_PORT` (device location)
  - `CONF_RSCPKEY` (RSCP encryption key)
  - `CONF_API_VERSION`, `CONF_FARMCONTROLLER` (feature flags)
  - `CONF_CREATE_BATTERY_DEVICES` (optional, defaults to `DEFAULT_CREATE_BATTERY_DEVICES`)
- Bump `CONF_VERSION` in `const.py` if schema changes; handle migration in `__init__.async_migrate_entry()`
- Set `unique_id` early (e.g., device serial number or hostname) to enable reauth/reconfiguration

## SSDP Discovery

- `async_step_ssdp()` reads `discovery_info` for manufacturer, model, hostname, serial and friendly name
- Values may live under either `upnp` or `ssdp_headers`; check both
- Use `urlparse()` to extract the hostname from SSDP URLs, with a fallback when parsing fails
- Abort discovery if the entry already exists: `self.async_abort_if_unique_id_configured()`

## Translation & Placeholders

- Refer to `translations/en.json` keys in form schema via `"data_schema"` and `"description_placeholders"`
- Use `"base"` key for generic error messages (shown in red banner)
- Use `"invalid_auth"`, `"cannot_connect"` as specific error keys

## Backwards Compatibility

- Do **not** remove or rename existing configuration keys without migration logic
- If adding new optional keys, provide sensible defaults in `const.py`
- Test that old config entries (before schema change) migrate cleanly

## Example Pattern

```python
async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
    """Handle user-initiated flow."""
    errors = {}
    if user_input is not None:
        try:
            await self.hass.async_add_executor_job(self._proxy.connect)
        except ConfigEntryAuthFailed:
            errors["base"] = ERROR_AUTH_INVALID
        except HomeAssistantError:
            errors["base"] = ERROR_CANNOT_CONNECT

        if not errors:
            return self.async_create_entry(title=user_input[CONF_HOST], data=user_input)

    return self.async_show_form(step_id="user", data_schema=..., errors=errors)
```
