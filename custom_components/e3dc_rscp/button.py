"""E3DC Button platform."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any, Final

from homeassistant.components.button import (
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class E3DCButtonEntityDescription(ButtonEntityDescription):
    """Derived helper for advanced configs."""

    icon: str | None = None
    async_press_action: (
        Callable[[E3DCCoordinator], Coroutine[Any, Any, bool]] | None
    ) = None


BUTTONS: Final[tuple[E3DCButtonEntityDescription, ...]] = () # None yet


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Button Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]

    entities: list[E3DCButton] = [
        E3DCButton(coordinator, description, entry.unique_id)
        for description in BUTTONS
    ]

    for wallbox in coordinator.wallboxes:

        wallbox_toggle_wallbox_phases_description = E3DCButtonEntityDescription(
            key=wallbox["key"] + "-toggle-wallbox-phases",
            translation_key="wallbox-toggle-wallbox-phases",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            icon="mdi:sine-wave",
            async_press_action=lambda coordinator: coordinator.async_toggle_wallbox_phases(),
        )
        entities.append(E3DCButton(coordinator, wallbox_toggle_wallbox_phases_description, entry.unique_id))

        wallbox_toggle_wallbox_charging_description = E3DCButtonEntityDescription(
            key=wallbox["key"] + "-toggle-wallbox-charging",
            translation_key="wallbox-toggle-wallbox-charging",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            icon="mdi:car-electric",
            async_press_action=lambda coordinator: coordinator.async_toggle_wallbox_charging(),
        )
        entities.append(E3DCButton(coordinator, wallbox_toggle_wallbox_charging_description, entry.unique_id))


    async_add_entities(entities)


class E3DCButton(CoordinatorEntity, ButtonEntity):
    """Custom E3DC Button Implementation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCButtonEntityDescription,
        uid: str,
    ) -> None:
        """Initialize the Button."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCButtonEntityDescription = description
        self._attr_unique_id = f"{uid}_{description.key}"
        self._has_custom_icons: bool = self.entity_description.icon is not None

    @property
    def icon(self) -> str | None:
        """Return icon reference."""
        if self._has_custom_icons:
            return self.entity_description.icon

        return self._attr_icon

    async def async_press(self, **kwargs: Any) -> None:
        """Press the button asynchronnously."""
        if self.entity_description.async_press_action is not None:
            await self.entity_description.async_press_action(self.coordinator)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self.coordinator.device_info()
