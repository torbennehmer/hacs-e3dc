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
    # DIAGNOSTIC SENSORS
    E3DCBinarySensorEntityDescription(
        key="system-additional-source-available",
        translation_key="system-additional-source-available",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        on_icon="mdi:power-plug-outline",
        off_icon="mdi:power-plug-off-outline",
    ),
    # DEVICE SENSORS
    E3DCBinarySensorEntityDescription(
        key="pset-limit-enabled",
        translation_key="pset-limit-enabled",
        device_class=BinarySensorDeviceClass.RUNNING,
        on_icon="mdi:signal",
        off_icon="mdi:signal-off",
    ),
    E3DCBinarySensorEntityDescription(
        key="manual-charge-active",
        translation_key="manual-charge-active",
        device_class=BinarySensorDeviceClass.RUNNING,
        on_icon="mdi:electric-switch-closed",
        off_icon="mdi:electric-switch",
    ),
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

    for wallbox in coordinator.wallboxes:

        wallbox_sun_mode_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-sun-mode",
            translation_key="wallbox-sun-mode",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:weather-sunny",
            off_icon="mdi:weather-sunny-off",
            device_class=None,
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_sun_mode_description, entry.unique_id))

        wallbox_plug_lock_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-plug-lock",
            translation_key="wallbox-plug-lock",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:lock-open",
            off_icon="mdi:lock",
            device_class=BinarySensorDeviceClass.LOCK,
            entity_registry_enabled_default=False,  # Disabled per default as only Wallbox easy connect provides this state
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_plug_lock_description, entry.unique_id))

        wallbox_plug_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-plug",
            translation_key="wallbox-plug",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:power-plug",
            off_icon="mdi:power-plug-off",
            device_class=BinarySensorDeviceClass.PLUG,
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_plug_description, entry.unique_id))

        wallbox_schuko_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-schuko",
            translation_key="wallbox-schuko",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:power-plug-outline",
            off_icon="mdi:power-plug-off-outline",
            device_class=BinarySensorDeviceClass.POWER,
            entity_registry_enabled_default=False,   # Disabled per default as only Wallbox multi connect I provides this feature
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_schuko_description, entry.unique_id))

        wallbox_charging_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-charging",
            translation_key="wallbox-charging",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:car-electric",
            off_icon="mdi:car-electric-outline",
            device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_charging_description, entry.unique_id))

        wallbox_charging_canceled_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-charging-canceled",
            translation_key="wallbox-charging-canceled",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:cancel",
            off_icon="mdi:check-circle-outline",
            device_class=None,
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_charging_canceled_description, entry.unique_id))

        wallbox_battery_to_car_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-battery-to-car",
            translation_key="wallbox-battery-to-car",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:battery-charging",
            off_icon="mdi:battery-off",
            device_class=None,
            entity_registry_enabled_default=False,
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_battery_to_car_description, entry.unique_id))

        wallbox_key_state_description = E3DCBinarySensorEntityDescription(
            key=wallbox["key"] + "-key-state",
            translation_key="wallbox-key-state",
            translation_placeholders = {"wallbox_name": wallbox["name"]},
            on_icon="mdi:key-variant",
            off_icon="mdi:key-remove",
            device_class=BinarySensorDeviceClass.LOCK,
            entity_registry_enabled_default=False,
        )
        entities.append(E3DCBinarySensor(coordinator, wallbox_key_state_description, entry.unique_id))

    async_add_entities(entities)


class E3DCBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Custom E3DC Binary Sensor implementation."""

    _attr_has_entity_name: bool = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCBinarySensorEntityDescription,
        uid: str,
    ) -> None:
        """Initialize the Sensor."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCBinarySensorEntityDescription = description
        self._attr_unique_id = f"{uid}_{description.key}"
        self._custom_icons: bool = (
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
