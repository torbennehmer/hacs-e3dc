"""E3DC Number platform."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)

@dataclass
class E3DCNumberEntityDescription(NumberEntityDescription):
    """Derived helper for advanced configs."""

    async_set_native_value_action: Callable[
        [E3DCCoordinator, float, int], Coroutine[Any, Any, bool]
    ] | None = None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Number Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    entities: list[E3DCNumber] = []

    # Add Number descriptions for wallboxes
    for wallbox in coordinator.wallboxes:
        unique_id = list(wallbox["deviceInfo"]["identifiers"])[0][1]
        wallbox_key = wallbox["key"]

        wallbox_charge_current_limit_description = E3DCNumberEntityDescription(
            key=f"{wallbox_key}-max-charge-current",
            translation_key="wallbox-max-charge-current",
            name="Wallbox Max Charge Current",
            icon="mdi:current-ac",
            native_min_value=wallbox["lowerCurrentLimit"],
            native_max_value=wallbox["upperCurrentLimit"],
            native_step=1,
            device_class=NumberDeviceClass.CURRENT,
            native_unit_of_measurement="A",
            async_set_native_value_action=lambda coordinator, value, index=wallbox["index"]: coordinator.async_set_wallbox_max_charge_current(int(value), index),
        )
        entities.append(E3DCNumber(coordinator, wallbox_charge_current_limit_description, unique_id, wallbox["deviceInfo"]))

    async_add_entities(entities)


class E3DCNumber(CoordinatorEntity, NumberEntity):
    """Custom E3DC Number Implementation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCNumberEntityDescription,
        uid: str,
        device_info: DeviceInfo | None = None
    ) -> None:
        """Initialize the Number."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCNumberEntityDescription = description
        self._attr_value = self.coordinator.data.get(self.entity_description.key)
        self._attr_unique_id = f"{uid}_{description.key}"
        if device_info is not None:
            self._deviceInfo = device_info
        else:
            self._deviceInfo = self.coordinator.device_info()

    @property
    def native_value(self):
        """Return the current value."""
        return self._attr_value

    @callback
    def _handle_coordinator_update(self) -> None:
        """Process coordinator updates."""
        self._attr_value = self.coordinator.data.get(self.entity_description.key)
        self.async_write_ha_state()

    async def async_set_native_value(self, value: float) -> None:
        """Set the number value asynchronously."""
        if self.entity_description.async_set_native_value_action is not None:
            self._attr_value = value
            self.async_write_ha_state()
            await self.entity_description.async_set_native_value_action(self.coordinator, value)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._deviceInfo
