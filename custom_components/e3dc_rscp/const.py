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

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]
