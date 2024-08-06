"""Constants for the E3DC Remote Storage Control Protocol integration."""

from homeassistant.const import Platform

CONF_RSCPKEY = "rscpkey"
CONF_VERSION = 1
DOMAIN = "e3dc_rscp"
ERROR_AUTH_INVALID = "invalid_auth"
ERROR_CANNOT_CONNECT = "cannot_connect"
SERVICE_CLEAR_POWER_LIMITS = "clear_power_limits"
SERVICE_SET_POWER_LIMITS = "set_power_limits"
SERVICE_MANUAL_CHARGE = "manual_charge"
SERVICE_SET_WALLBOX_MAX_CHARGE_CURRENT = "set_wallbox_max_charge_current"
MAX_WALLBOXES_POSSIBLE = 8 # 8 is the maximum according to RSCP Specification

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER
]
