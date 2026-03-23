"""E3DC Select platform."""

from collections.abc import Callable, Coroutine
from dataclasses import dataclass
import logging
from typing import Any

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class E3DCSelectEntityDescription(SelectEntityDescription):
    """Derived helper for advanced configs."""

    async_select_option_action: (
        Callable[[E3DCCoordinator, str], Coroutine[Any, Any, bool]] | None
    ) = None


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Select Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    entities: list[E3DCSelect] = []

    # Portal charging priority (system-level, not per-wallbox)
    if coordinator.portal_client is not None and len(coordinator.wallboxes) > 0:
        charging_priority = E3DCSelectEntityDescription(
            key="portal-charging-priority",
            translation_key="portal-charging-priority",
            icon="mdi:battery-sync",
            options=["battery", "wallbox"],
            entity_category=EntityCategory.CONFIG,
            async_select_option_action=lambda coordinator, option: coordinator.async_set_portal_charging_priority(
                option
            ),
        )
        entities.append(E3DCSelect(coordinator, charging_priority, entry.unique_id))

    async_add_entities(entities)


class E3DCSelect(CoordinatorEntity, SelectEntity):
    """Custom E3DC Select Implementation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCSelectEntityDescription,
        uid: str,
        device_info: DeviceInfo | None = None,
    ) -> None:
        """Initialize the Select."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCSelectEntityDescription = description
        self._attr_current_option = self.coordinator.data.get(
            self.entity_description.key
        )
        self._attr_unique_id = f"{uid}_{description.key}"
        if device_info is not None:
            self._deviceInfo = device_info
        else:
            self._deviceInfo = self.coordinator.device_info()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Process coordinator updates."""
        self._attr_current_option = self.coordinator.data.get(
            self.entity_description.key
        )
        self.async_write_ha_state()

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        if self.entity_description.async_select_option_action is not None:
            self._attr_current_option = option
            self.async_write_ha_state()
            await self.entity_description.async_select_option_action(
                self.coordinator, option
            )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._deviceInfo
