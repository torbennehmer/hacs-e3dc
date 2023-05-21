"""E3DC Binary Sensors."""

from dataclasses import dataclass
import logging
from typing import Final

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class E3DCBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Derived helper for more advanced entity configs."""

    on_icon: str | None = None
    off_icon: str | None = None


SENSOR_DESCRIPTIONS: Final[tuple[E3DCBinarySensorEntityDescription, ...]] = (
    # CONFIG AND DIAGNOSTIC SENSORS
    E3DCBinarySensorEntityDescription(
        key="ext_source_available",
        translation_key="ext_source_available",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        on_icon="mdi:power-plug-outline",
        off_icon="mdi:power-plug-off-outline",
    ),
    E3DCBinarySensorEntityDescription(
        key="pset_limits_enabled",
        translation_key="pset_limits_enabled",
        entity_category=EntityCategory.CONFIG,
        device_class=BinarySensorDeviceClass.RUNNING,
        on_icon="mdi:signal",
        off_icon="mdi:signal-off",
    ),
    # DEVICE SENSORS (none yet)
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Prepare the Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    entities: list[E3DCBinarySensor] = [
        E3DCBinarySensor(coordinator, description, entry.unique_id)
        for description in SENSOR_DESCRIPTIONS
    ]
    async_add_entities(entities)


class E3DCBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Custom E3DC Binary Sensor implementation."""

    coordinator: E3DCCoordinator
    entity_description: E3DCBinarySensorEntityDescription
    _attr_has_entity_name: bool = True
    _custom_icons: bool = False

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCBinarySensorEntityDescription,
        uid: str,
    ) -> None:
        """Initialize the Sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{uid}_{description.key}"
        self._custom_icons = (
            self.entity_description.on_icon is not None
            and self.entity_description.off_icon is not None
        )

    @property
    def is_on(self) -> bool | None:
        """Return the actual sensor state."""
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def icon(self) -> str | None:
        """Return customized icons, if applicable."""
        return (
            self.entity_description.on_icon
            if self.is_on
            else self.entity_description.off_icon
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self.coordinator.device_info()
