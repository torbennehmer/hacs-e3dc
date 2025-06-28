"""Constants for the E3DC Remote Storage Control Protocol integration."""
from enum import Enum

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
SERVICE_SET_POWER_MODE = "set_power_mode"
MAX_WALLBOXES_POSSIBLE = 8  # 8 is the maximum according to RSCP Specification

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.NUMBER
]


class PowerMode(Enum):
    IDLE = 0
    DISCHARGE = 1
    CHARGE = 2

    @classmethod
    def has_value(self, value):
        return value in self._value2member_map_ 


class SetPowerMode(Enum):
    NORMAL = 0
    IDLE = 1
    DISCHARGE = 2
    CHARGE = 3
    CHARGE_GRID = 4

    @classmethod
    def has_value(self, value):
        return value in self._value2member_map_ 