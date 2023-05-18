"""Constants for the E3DC Remote Storage Control Protocol integration."""

from homeassistant.const import Platform

CONF_RSCPKEY = "rscpkey"
CONF_VERSION = 1
DOMAIN = "e3dc"
ERROR_AUTH_INVALID = "invalid_auth"
ERROR_CANNOT_CONNECT = "cannot_connect"
SERVICE_SET_POWER_LIMITS = "set_power_limits"

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
]
