"""Constants for the E3DC Remote Storage Control Protocol integration."""
from enum import Enum

from homeassistant.const import Platform

CONF_RSCPKEY = "rscpkey"
CONF_FARMCONTROLLER = "farmcontroller"
CONF_VERSION = 2
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
    """Enum for power modes in E3DC RSCP."""

    IDLE = '0'
    DISCHARGE = '1'
    CHARGE = '2'

    @classmethod
    def has_value(self, value):
        """Check if a value is a valid PowerMode."""
        return value in self._value2member_map_

    @classmethod
    def get_enum(self, value):
        """Get the PowerMode member by value."""
        return self._value2member_map_.get(value, None)

class SetPowerMode(Enum):
    """Enum for set power modes in E3DC RSCP."""

    NORMAL = '0'
    IDLE = '1'
    DISCHARGE = '2'
    CHARGE = '3'
    CHARGE_GRID = '4'

    @classmethod
    def has_value(self, value):
        """Check if a value is a valid SetPowerMode."""
        return value in self._value2member_map_

    @classmethod
    def get_enum(self, value):
        """Get the SetPowerMode member by value."""
        return self._value2member_map_.get(value, None)

class EntryType(Enum):
    """Entry types for E3DC sensors to distinguish between farm controller, members or both (ununsed atm)."""

    FARM = "farm"
    MEMBER = "member"
    BOTH = "both"
