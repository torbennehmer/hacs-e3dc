"""Main Service interfaces, acts as proxy for actual execution."""

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import (
    DeviceEntry,
    DeviceRegistry,
    async_get,
)
from .const import DOMAIN, SERVICE_SET_POWER_LIMITS, SERVICE_CLEAR_POWER_LIMITS
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)
_device_map: dict[str, E3DCCoordinator] = {}

ATTR_DEVICEID = "device_id"
ATTR_MAX_CHARGE = "max_charge"
ATTR_MAX_DISCHARGE = "max_discharge"

SCHEMA_CLEAR_POWER_LIMITS = vol.Schema(
    {
        vol.Required(ATTR_DEVICEID): str,
    }
)

SCHEMA_SET_POWER_LIMITS = vol.Schema(
    {
        vol.Required(ATTR_DEVICEID): str,
        vol.Optional(ATTR_MAX_CHARGE): vol.All(int, vol.Range(min=0)),
        vol.Optional(ATTR_MAX_DISCHARGE): vol.All(int, vol.Range(min=0)),
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Central hook to register all services, called by component setup."""

    # hass.services.register(DOMAIN, "servicename", lambda, schema)
    async def async_call_set_power_limits(call: ServiceCall) -> None:
        await _async_set_power_limits(hass, call)

    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_SET_POWER_LIMITS,
        service_func=async_call_set_power_limits,
        schema=SCHEMA_SET_POWER_LIMITS,
    )

    async def async_call_clear_power_limits(call: ServiceCall) -> None:
        await _async_clear_power_limits(hass, call)

    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_CLEAR_POWER_LIMITS,
        service_func=async_call_clear_power_limits,
        schema=SCHEMA_CLEAR_POWER_LIMITS,
    )


def _resolve_device_id(hass: HomeAssistant, devid: str) -> E3DCCoordinator:
    """Resolve a device ID to its coordinator with caching."""
    if devid in _device_map:
        return _device_map[devid]
    dev_reg: DeviceRegistry = async_get(hass)
    dev: DeviceEntry = dev_reg.async_get(devid)
    if dev is None:
        raise HomeAssistantError(
            f"{SERVICE_SET_POWER_LIMITS}: Unkown device ID {devid}."
        )

    identifier: tuple(str, str) = next(iter(dev.identifiers))
    if identifier[0] != DOMAIN:
        raise HomeAssistantError(
            f"{SERVICE_SET_POWER_LIMITS}: Device {devid} is no E3DC."
        )

    uid: str = identifier[1]
    coordinator: E3DCCoordinator = hass.data[DOMAIN][uid]
    _device_map[devid] = coordinator
    return coordinator


async def _async_set_power_limits(hass: HomeAssistant, call: ServiceCall) -> None:
    """Extract service information and relay to coordinator."""
    coordinator: E3DCCoordinator = _resolve_device_id(
        hass, call.data.get(ATTR_DEVICEID)
    )
    max_charge: int | None = call.data.get(ATTR_MAX_CHARGE)
    max_discharge: int | None = call.data.get(ATTR_MAX_DISCHARGE)
    if max_charge is None and max_discharge is None:
        raise HomeAssistantError(
            f"{SERVICE_SET_POWER_LIMITS}: Need to set at least one of {ATTR_MAX_CHARGE} or {ATTR_MAX_DISCHARGE}"
        )
    await coordinator.async_set_power_limits(
        max_charge=max_charge, max_discharge=max_discharge
    )


async def _async_clear_power_limits(hass: HomeAssistant, call: ServiceCall) -> None:
    """Extract service information and relay to coordinator."""
    coordinator: E3DCCoordinator = _resolve_device_id(
        hass, call.data.get(ATTR_DEVICEID)
    )
    await coordinator.async_clear_power_limits()
