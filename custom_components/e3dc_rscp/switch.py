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
    async_turn_on_action: (
        Callable[[E3DCCoordinator], Coroutine[Any, Any, bool]] | None
    ) = None
    async_turn_off_action: (
        Callable[[E3DCCoordinator], Coroutine[Any, Any, bool]] | None
    ) = None


SWITCHES: Final[tuple[E3DCSwitchEntityDescription, ...]] = (
    # CONFIG AND DIAGNOSTIC SWITCHES
    E3DCSwitchEntityDescription(
        key="pset-powersaving-enabled",
        translation_key="pset-powersaving-enabled",
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
        key="pset-weatherregulationenabled",
        translation_key="pset-weatherregulationenabled",
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
    E3DCSwitchEntityDescription(
        # TODO: Figure out how the icons match the on/off state
        key="wallbox_sunmode",
        translation_key="wallbox-sunmode",
        name="Wallbox Sun Mode",
        on_icon="mdi:weather-sunny",
        off_icon="mdi:weather-sunny-off",
        device_class=SwitchDeviceClass.SWITCH,
        async_turn_on_action=lambda coordinator: coordinator.async_set_wallbox_sunmode(
            True
        ),
        async_turn_off_action=lambda coordinator: coordinator.async_set_wallbox_sunmode(
            False
        ),
    ),
    E3DCSwitchEntityDescription(
        key="wallbox_schuko",
        translation_key="wallbox-schuko",
        name="Wallbox Schuko",
        on_icon="mdi:power-plug",
        off_icon="mdi:power-plug-off",
        device_class=SwitchDeviceClass.SWITCH,
        async_turn_on_action=lambda coordinator: coordinator.async_set_wallbox_schuko(
            True
        ),
        async_turn_off_action=lambda coordinator: coordinator.async_set_wallbox_schuko(
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

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCSwitchEntityDescription,
        uid: str,
    ) -> None:
        """Initialize the Sensor."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCSwitchEntityDescription = description
        self._attr_is_on = self.coordinator.data.get(self.entity_description.key)
        self._attr_unique_id = f"{uid}_{description.key}"
        self._has_custom_icons: bool = (
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
