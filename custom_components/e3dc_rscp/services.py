"""Main Service interfaces, acts as proxy for actual execution."""

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, SERVICE_SET_POWER_LIMITS
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)

ATTR_DEVICEID = "device_id"
ATTR_MAX_CHARGE = "max_charge"
ATTR_MAX_DISCHARGE = "max_discharge"

SCHEMA_SET_POWER_KUNUTS = vol.Schema(
    {
        vol.Required(ATTR_DEVICEID): str,
        vol.Optional(ATTR_MAX_CHARGE): vol.All(int, vol.Range(min=0)),
        vol.Optional(ATTR_MAX_DISCHARGE): vol.All(int, vol.Range(min=0)),
    }
)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Central hook to register all services, called by component setup."""

    async def async_call_set_power_limits(call: ServiceCall) -> None:
        await _async_set_power_limits(hass, call)

    # hass.services.register(DOMAIN, "servicename", lambda, schema)
    hass.services.async_register(
        domain=DOMAIN,
        service=SERVICE_SET_POWER_LIMITS,
        service_func=async_call_set_power_limits,
        schema=SCHEMA_SET_POWER_KUNUTS,
    )


async def _async_set_power_limits(hass: HomeAssistant, call: ServiceCall) -> None:
    """Extract service information and relay to coordinator."""
    uid = call.data.get(ATTR_DEVICEID)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][uid]
    max_charge: int | None = call.data.get(ATTR_MAX_CHARGE)
    max_discharge: int | None = call.data.get(ATTR_MAX_DISCHARGE)
    if max_charge is None and max_discharge is None:
        raise ValueError(
            f"SERVICE_SET_POWER_LIMITS: Need to set at least one of {ATTR_MAX_CHARGE} or {ATTR_MAX_DISCHARGE}"
        )
    await coordinator.async_set_power_limits(
        max_charge=max_charge, max_discharge=max_discharge
    )
