from dataclasses import dataclass
from typing import Final, Awaitable, Callable

from homeassistant.components.select import (
    SelectEntity,
    SelectEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from custom_components.e3dc_rscp import const, E3DCCoordinator

from .const import DOMAIN

OPTIONS: Final[dict[str, dict[str, int]]] = {
    "powermode": {
        "NORMAL": 0,
        "IDLE": 1,
        "DISCHARGE": 2,
        "CHARGE": 3,
        "CHARGE_GRID": 4,
    },
    "mode": {
        "0": "IDLE",
        "1": "DISCHARGE",
        "2": "CHARGE"
    }
}


@dataclass(frozen=True, kw_only=True)
class E3DCSelectEntityDescription(SelectEntityDescription):
    command: Callable[[E3DCCoordinator, str], Awaitable[None]]


async def async_setup_entry(
        hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Select Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]


class E3DCSelectEntity(CoordinatorEntity, SelectEntity):
    """Representation of an E3DC select entity."""
    entity_description: E3DCSelectEntityDescription

    _attr_has_entity_name = True

    def __init__(
            self,
            coordinator: E3DCCoordinator,
            description: E3DCSelectEntityDescription,
            uid: str,
            device_info: DeviceInfo | None = None,
    ) -> None:
        """Initialize the Number."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCSelectEntityDescription = description
        self._attr_value = self.coordinator.data.get(self.entity_description.key)
        self._attr_unique_id = f"{uid}_{description.key}"
        if device_info is not None:
            self._deviceInfo = device_info
        else:
            self._deviceInfo = self.coordinator.device_info()

    @property
    def current_option(self) -> str | None:
        """Return the selected entity option to represent the entity state."""
        return self.coordinator.data.get(self.entity_description.key)

    async def async_select_option(self, option: str) -> None:
        """Change the selected option."""
        await self.entity_description.command(self.coordinator, option)

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._deviceInfo