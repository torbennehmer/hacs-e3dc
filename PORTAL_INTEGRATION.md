# Portal Integration — Implementation Status

Branch: `portal-integration` (based on `main`)

## What Was Done

### New File: `custom_components/e3dc_rscp/e3dc_portal_client.py`

Self-contained Portal REST client ported from `e3dc-web/python-e3dc/e3dc/_e3dc_portal.py`. No dependency on the python-e3dc library for portal features.

**Contains:**
- `E3DCPortalClient` class — synchronous `requests.Session` based HTTP client
- Full SAML/Keycloak login chain (4-step: entry → Keycloak form → SAML assertion → token redirect)
- Token lifecycle: `_ensure_token()` auto-refreshes via `_re_auth()` before every request
- `get_charging_priorisation(wallbox_serial)` — reads current state
- `set_charging_priorisation(wallbox_serial, *, is_battery, in_sun_mode, in_mix_mode, till_soc)` — full-state-write with double-encoding quirk
- `get_token_state()` / `set_token_state()` — for persisting reAuthToken across HA restarts
- `@e3dc_portal_call` decorator — maps `PortalAuthenticationError` → `ConfigEntryAuthFailed`, `PortalRequestError` → `HomeAssistantError`
- Helper functions: `_merge_charging_prio()`, `_encode_charging_prio_body()`, `_extract_kccontext_login_action()`, `_extract_saml_response()`

### Modified Files (10 files, 733 lines added)

#### `const.py`
- Added: `CONF_PORTAL_ENABLED`, `DEFAULT_PORTAL_ENABLED`, `CONF_PORTAL_RE_AUTH_TOKEN`, `PORTAL_POLL_INTERVAL` (120s), `ERROR_PORTAL_AUTH_FAILED`
- Bumped `CONF_VERSION` from 2 → 3

#### `config_flow.py`
- **User step**: Added `portal_enabled` checkbox to `STEP_USER_DATA_SCHEMA`
- **SSDP confirm step**: Added `portal_enabled` checkbox
- **Portal validation**: `_validate_portal_login()` method — validates portal credentials during setup, shows error but allows continuing without portal
- **Options flow**: Added `portal_enabled` toggle to `E3DCOptionsFlowHandler`. Stores in `config_entry.data` (not options). Clears reAuthToken when disabled. Integration reloads on change (uses `OptionsFlowWithReload`).
- Both user step and SSDP confirm step store `CONF_PORTAL_ENABLED` and `CONF_PORTAL_RE_AUTH_TOKEN` in final entry data

#### `__init__.py`
- Added v2 → v3 migration: defaults `portal_enabled=False`, `portal_re_auth_token=None`
- Added imports for portal constants

#### `coordinator.py`
- Added `serial` field to `E3DCWallbox` TypedDict (stores wallbox serial from RSCP identification)
- Added `portal_client: E3DCPortalClient | None` attribute
- Added `_update_guard_portal` and `_next_portal_update` for polling control
- **`_async_connect_portal()`**: Creates portal client, restores persisted reAuthToken, attempts login. On failure: logs warning, sets `portal_client = None`, entities won't be created
- **`_async_persist_portal_token()`**: Saves reAuthToken to config entry data after each token refresh
- **`_load_and_process_portal_data()`**: For each wallbox, fetches charging priorisation and stores in `_mydata` with keys `portal-{wb_key}-battery-first`, `portal-{wb_key}-sun-mode`, `portal-{wb_key}-mix-mode`, `portal-{wb_key}-till-soc`
- **Portal polling**: Separate 120s interval in `_async_update_data()`, after wallbox data, before battery data. Skipped when update guard active.
- **Service methods** (4): `async_set_portal_battery_first()`, `async_set_portal_sun_mode()`, `async_set_portal_mix_mode()`, `async_set_portal_till_soc()` — each sets update guard, calls API via executor, triggers immediate portal re-poll, persists token

#### `switch.py`
- Added **Portal Battery First**, **Portal Sun Mode**, **Portal Mix Mode** switches per wallbox
- On main E3DC device (not wallbox device), `EntityCategory.CONFIG`
- Only created when `coordinator.portal_client is not None` AND wallboxes present
- Follow existing pattern: pessimistic update + coordinator call

#### `number.py`
- Added **Portal Discharge Limit** (till_soc) number entity per wallbox
- 0–100% slider, step 1, `EntityCategory.CONFIG`, on main E3DC device
- Only created when portal enabled + wallbox present

#### `binary_sensor.py`
- Added **Portal Connection Status** binary sensor
- Device class CONNECTIVITY, `EntityCategory.DIAGNOSTIC`, on main E3DC device
- Only created when `coordinator.portal_client is not None`

#### `diagnostics.py`
- Added portal status to diagnostic dump (enabled, connected, authenticated)
- Extended redaction regex to cover `reAuthToken`, `re_auth_token`, `access_token`, `token`

#### `strings.json` + `translations/en.json`
- Added `portal_enabled` label in config flow user step and options flow
- Added `portal_auth_failed` error message
- Added entity translations: `portal-battery-first`, `portal-sun-mode`, `portal-mix-mode`, `portal-discharge-limit`, `portal-connection-status`

### Devcontainer

Created `.devcontainer/devcontainer.json` using `mcr.microsoft.com/devcontainers/python:1-3.13` base image with port 8124 forwarded for HA dev instance.

## Design Decisions

- **Credentials**: Reuses existing RSCP username/password (same E3DC portal account)
- **Portal-only mode**: Not supported — portal is always add-on to local RSCP
- **Token persistence**: reAuthToken stored in config entry data (encrypted by HA), survives restarts
- **Wallbox serial**: Auto-discovered from RSCP wallbox identification (`wallboxSerial` field)
- **Polling**: Separate slow interval (120s), plus on-demand refresh before/after writes
- **RSCP vs Portal overlap**: RSCP entities have priority; portal entities are distinct (e.g., `portal-sun-mode` is separate from RSCP `sun-mode`)
- **Auth failure**: Triggers reauth flow; RSCP entities stay unaffected
- **Portal entities**: On main E3DC device, only when wallbox is connected
- **HTTP client**: Synchronous `requests` + `hass.async_add_executor_job()` to match existing `e3dc_proxy.py` pattern

## Next Steps

### 1. Test in Devcontainer
- Reopen VS Code, let devcontainer build
- Run task "Run Home Assistant on port 8124"
- Open `http://localhost:8124`, set up E3DC integration with portal enabled
- Verify:
  - Portal entities appear when portal enabled + wallbox present
  - Switches toggle correctly (check portal state via GET after PUT)
  - Number entity updates till_soc correctly
  - Portal connection status reflects auth state

### 2. Handle Edge Cases
- **No wallbox**: Verify portal entities don't appear when no wallbox is connected
- **Portal disabled**: Verify no portal entities created, no portal API calls
- **Token expiry**: Verify automatic re-auth when access token expires (10 min)
- **reAuthToken expiry**: Verify reauth flow triggers after 30 days (simulate by clearing stored token)
- **HA restart**: Verify reAuthToken restored from config entry, no full SAML login needed

### 3. Refinements to Consider
- **SSDP discovery flow**: Portal validation is not yet wired in SSDP confirm (only stores the toggle, doesn't validate). Could add portal validation there too.
- **Farm controller**: Portal features are skipped for farm controllers (no wallbox support). Verify this works.
- **Multiple wallboxes**: If user has >1 wallbox, verify each gets its own set of portal entities with correct serial routing.
- **Error recovery**: When portal auth fails at runtime, currently sets `portal-connection-status` to False. Could add periodic retry logic.
- **Rate limiting**: Portal API may have rate limits. Consider adding backoff on repeated failures.

### 4. Future Portal Features
- Smart-charge context: `GET /storages/{serial}/smart-functions/smart-charge`
- Idle periods: `GET /storages/{serial}/smart-functions/smart-charge/idle-periods`
- Broader `/storages/` endpoint coverage

### 5. Code Quality
- Add unit tests for `_merge_charging_prio()`, `_encode_charging_prio_body()`, token lifecycle
- Add config flow tests for portal toggle in setup + options
- Run full lint: `uvx ruff check custom_components/e3dc_rscp/` (already passes)

## File Map

```
custom_components/e3dc_rscp/
├── e3dc_portal_client.py   ← NEW: Portal REST client
├── __init__.py              ← v3 migration
├── config_flow.py           ← portal toggle in setup + options
├── const.py                 ← portal constants
├── coordinator.py           ← portal lifecycle, polling, services
├── switch.py                ← portal switches (battery-first, sun-mode, mix-mode)
├── number.py                ← portal discharge limit (till_soc)
├── binary_sensor.py         ← portal connection status
├── diagnostics.py           ← portal diagnostics + token redaction
├── strings.json             ← portal translations
├── translations/en.json     ← portal English translations
├── e3dc_proxy.py            ← UNCHANGED (RSCP only)
├── battery_manager.py       ← UNCHANGED
├── sensor.py                ← UNCHANGED
├── button.py                ← UNCHANGED
├── services.py              ← UNCHANGED
└── utils.py                 ← UNCHANGED
.devcontainer/
└── devcontainer.json        ← NEW: devcontainer config
```
