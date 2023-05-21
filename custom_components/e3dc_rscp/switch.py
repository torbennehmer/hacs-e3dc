"""E3DC Switch platform."""
from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
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
class E3DCSwitchEntityDescription(SwitchEntityDescription):
    """Derived helper for advanced configs."""

    on_icon: str | None = None
    off_icon: str | None = None
    async_turn_on_action: Callable[
        [E3DCCoordinator], Coroutine[Any, Any, bool]
    ] | None = None
    async_turn_off_action: Callable[
        [E3DCCoordinator], Coroutine[Any, Any, bool]
    ] | None = None


SWITCHES: Final[tuple[E3DCSwitchEntityDescription, ...]] = (
    # CONFIG AND DIAGNOSTIC SWITCHES
    E3DCSwitchEntityDescription(
        key="pset_powersave_enabled",
        translation_key="pset_powersave_enabled",
        on_icon="mdi:leaf",
        off_icon="mdi:leaf-off",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        async_turn_on_action=lambda coordinator: coordinator.async_set_powersave(True),
        async_turn_off_action=lambda coordinator: coordinator.async_set_powersave(
            False
        ),
        entity_registry_enabled_default=False,
    ),
    E3DCSwitchEntityDescription(
        key="pset_weatherregulation_enabled",
        translation_key="pset_weatherregulation_enabled",
        on_icon="mdi:weather-sunny",
        off_icon="mdi:weather-sunny-off",
        device_class=SwitchDeviceClass.SWITCH,
        entity_category=EntityCategory.CONFIG,
        async_turn_on_action=lambda coordinator: coordinator.async_set_weather_regulated_charge(
            True
        ),
        async_turn_off_action=lambda coordinator: coordinator.async_set_weather_regulated_charge(
            False
        ),
    ),
    # REGULAR SWITCHES (None Yet)
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Binary Sensor Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    entities: list[E3DCSwitch] = [
        E3DCSwitch(coordinator, description, entry.unique_id)
        for description in SWITCHES
    ]
    async_add_entities(entities)


class E3DCSwitch(CoordinatorEntity, SwitchEntity):
    """Custom E3DC Switch Implementation."""

    coordinator: E3DCCoordinator
    entity_description: E3DCSwitchEntityDescription
    _attr_has_entity_name = True
    _has_custom_icons: bool = False

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCSwitchEntityDescription,
        uid: str,
    ) -> None:
        """Initialize the Sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_is_on = self.coordinator.data.get(self.entity_description.key)
        self._attr_unique_id = f"{uid}_{description.key}"
        self._has_custom_icons = (
            self.entity_description.on_icon is not None
            and self.entity_description.off_icon is not None
        )

    @property
    def icon(self) -> str | None:
        """Return dynamic icon reference."""
        if self._has_custom_icons:
            return (
                self.entity_description.on_icon
                if (self.is_on)
                else self.entity_description.off_icon
            )

        return self._attr_icon

    @callback
    def _handle_coordinator_update(self) -> None:
        """Process coordinator updates."""
        self._attr_is_on = self.coordinator.data.get(self.entity_description.key)
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn off the switch asynchronnously."""
        if self.entity_description.async_turn_on_action is not None:
            self._attr_is_on = True
            self.async_write_ha_state()
            await self.entity_description.async_turn_on_action(self.coordinator)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn on the switch asynchronnously."""
        if self.entity_description.async_turn_off_action is not None:
            self._attr_is_on = False
            self.async_write_ha_state()
            await self.entity_description.async_turn_off_action(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self.coordinator.device_info()
