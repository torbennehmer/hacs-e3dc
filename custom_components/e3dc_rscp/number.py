"""E3DC Number platform."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.const import EntityCategory, PERCENTAGE

from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class E3DCNumberEntityDescription(NumberEntityDescription):
    """Derived helper for advanced configs."""

    async_set_native_value_action: (
        Callable[[E3DCCoordinator, float, int], Coroutine[Any, Any, bool]] | None
    ) = None
    available_fn: Callable[[E3DCCoordinator], bool] | None = None


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
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement="A",
            async_set_native_value_action=lambda coordinator, value, index=wallbox[
                "index"
            ]: coordinator.async_set_wallbox_max_charge_current(int(value), index),
        )
        entities.append(
            E3DCNumber(
                coordinator,
                wallbox_charge_current_limit_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

    async_add_entities(entities)

    # Portal discharge limit (till_soc) - on main E3DC device, system-level
    if coordinator.portal_client is not None and len(coordinator.wallboxes) > 0:
        portal_till_soc = E3DCNumberEntityDescription(
            key="portal-till-soc",
            translation_key="portal-wb-discharge-limit",
            icon="mdi:battery-lock",
            native_min_value=0,
            native_max_value=100,
            native_step=1,
            mode=NumberMode.SLIDER,
            entity_category=EntityCategory.CONFIG,
            native_unit_of_measurement=PERCENTAGE,
            async_set_native_value_action=lambda coordinator, value: coordinator.async_set_portal_till_soc(
                int(value),
            ),
            available_fn=lambda coordinator: coordinator.data.get(
                "portal-sun-mode", False
            )
            is True,
        )
        async_add_entities(
            [
                E3DCNumber(coordinator, portal_till_soc, entry.unique_id),
            ]
        )


class E3DCNumber(CoordinatorEntity, NumberEntity):
    """Custom E3DC Number Implementation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCNumberEntityDescription,
        uid: str,
        device_info: DeviceInfo | None = None,
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
    def available(self) -> bool:
        """Return True if entity is available."""
        if self.entity_description.available_fn is not None:
            return self.entity_description.available_fn(self.coordinator)
        return super().available

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
            await self.entity_description.async_set_native_value_action(
                self.coordinator, value
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._deviceInfo
