"""E3DC sensor platform."""

import logging
from dataclasses import dataclass
from typing import Final

from e3dc._rscpTags import PowermeterType

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfEnergy, UnitOfPower
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import E3DCCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class E3DCSensorEntityDescription(SensorEntityDescription):
    """Class describing E3DC Sensor entities."""

    icons: dict[str, str] = None


SENSOR_DESCRIPTIONS: Final[tuple[E3DCSensorEntityDescription, ...]] = (
    # DIAGNOSTIC SENSORS
    E3DCSensorEntityDescription(
        key="system-derate-percent",
        translation_key="system-derate-percent",
        icon="mdi:transmission-tower-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="system-derate-power",
        translation_key="system-derate-power",
        icon="mdi:transmission-tower-off",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="system-battery-installed-capacity",
        translation_key="system-battery-installed-capacity",
        icon="mdi:battery-high",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="system-battery-installed-peak",
        translation_key="system-battery-installed-peak",
        icon="mdi:solar-power-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="system-ac-maxpower",
        translation_key="system-ac-maxpower",
        icon="mdi:solar-power-variant",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="system-battery-charge-max",
        translation_key="system-battery-charge-max",
        icon="mdi:battery-arrow-up-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="system-battery-discharge-max",
        translation_key="system-battery-discharge-max",
        icon="mdi:battery-arrow-down-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="system-mac",
        translation_key="system-mac",
        icon="mdi:ethernet",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="pset-limit-discharge-minimum",
        translation_key="pset-limit-discharge-minimum",
        icon="mdi:battery-arrow-down-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="system-battery-discharge-minimum-default",
        translation_key="system-battery-discharge-minimum-default",
        icon="mdi:battery-arrow-down-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.WATT,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    # DEVICE SENSORS
    E3DCSensorEntityDescription(
        key="autarky",
        translation_key="autarky",
        icon="mdi:home-percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="battery-charge",
        translation_key="battery-charge",
        icon="mdi:battery-charging-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="battery-netchange",
        translation_key="battery-netchange",
        icon="mdi:battery-charging",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="grid-consumption",
        translation_key="grid-consumption",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="house-consumption",
        translation_key="house-consumption",
        icon="mdi:home-import-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="grid-netchange",
        translation_key="grid-netchange",
        icon="mdi:battery-charging",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="battery-discharge",
        translation_key="battery-discharge",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="additional-production",
        translation_key="additional-production",
        icon="mdi:power-plug",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
    ),
    E3DCSensorEntityDescription(
        key="grid-production",
        translation_key="grid-production",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="solar-production",
        translation_key="solar-production",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="selfconsumption",
        translation_key="selfconsumption",
        icon="mdi:cloud-percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="soc",
        translation_key="soc",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="manual-charge-energy",
        translation_key="manual-charge-energy",
        icon="mdi:transmission-tower",
        native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="pset-limit-charge",
        translation_key="pset-limit-charge",
        icon="mdi:battery-arrow-up-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="pset-limit-discharge",
        translation_key="pset-limit-discharge",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement=UnitOfPower.WATT,
        suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # LONGTERM STATISTIC SENSORS
    E3DCSensorEntityDescription(
        key="db-day-autarky",
        translation_key="db-day-autarky",
        icon="mdi:cloud-percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="db-day-battery-charge",
        translation_key="db-day-battery-charge",
        icon="mdi:battery-charging-outline",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="db-day-battery-discharge",
        translation_key="db-day-battery-discharge",
        icon="mdi:battery-arrow-down-outline",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="db-day-grid-consumption",
        translation_key="db-day-grid-consumption",
        icon="mdi:transmission-tower-export",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="db-day-house-consumption",
        translation_key="db-day-house-consumption",
        icon="mdi:home-import-outline",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="db-day-grid-production",
        translation_key="db-day-grid-production",
        icon="mdi:transmission-tower-import",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="db-day-solar-production",
        translation_key="db-day-solar-production",
        icon="mdi:solar-power",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
    ),
    E3DCSensorEntityDescription(
        key="db-day-selfconsumption",
        translation_key="db-day-selfconsumption",
        icon="mdi:cloud-percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        device_class=SensorDeviceClass.POWER_FACTOR,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    E3DCSensorEntityDescription(
        key="power-mode",
        translation_key="power-mode",
        icons={
            "IDLE": "mdi:battery-off-outline",
            "DISCHARGE": "mdi:battery-arrow-down-outline",
            "CHARGE": "mdi:battery-arrow-up-outline",
        },
        icon="mdi:battery-unknown",
    ),
    E3DCSensorEntityDescription(
        key="set-power-mode",
        translation_key="pset-powermode",
        icon="mdi:flash",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=True,
    ),
    E3DCSensorEntityDescription(
        key="set-power-value",
        translation_key="pset-powervalue",
        icon="mdi:meter-electric",
        name="Max Charge Power",
        entity_category=EntityCategory.DIAGNOSTIC,
        native_unit_of_measurement="W",
        entity_registry_enabled_default=True,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Initialize Sensor Platform."""
    assert isinstance(entry.unique_id, str)
    coordinator: E3DCCoordinator = hass.data[DOMAIN][entry.unique_id]
    entities: list[E3DCSensor] = [
        E3DCSensor(coordinator, description, entry.unique_id)
        for description in SENSOR_DESCRIPTIONS
    ]

    # Add SG Ready state if SG Ready is enabled
    if coordinator.sgready_available:
        sgready_state_description = E3DCSensorEntityDescription(
            key="sgready-state",
            translation_key="sgready-state",
            icon="mdi:heat-pump",
        )
        entities.append(
            E3DCSensor(coordinator, sgready_state_description, entry.unique_id)
        )

    # Add Sensor descriptions for additional powermeters, skip root PM
    for powermeter_config in coordinator.proxy.e3dc_config["powermeters"]:
        if powermeter_config["type"] == PowermeterType.PM_TYPE_ROOT.value:
            continue

        energy_description = E3DCSensorEntityDescription(
            has_entity_name=True,
            name=powermeter_config["name"] + " - total",
            key=powermeter_config["key"] + "-total",
            translation_key=powermeter_config["key"] + "-total",
            icon="mdi:meter-electric",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=2,
            device_class=SensorDeviceClass.ENERGY,
            state_class=powermeter_config["total-state-class"],
        )
        entities.append(E3DCSensor(coordinator, energy_description, entry.unique_id))

        power_description = E3DCSensorEntityDescription(
            has_entity_name=True,
            name=powermeter_config["name"],
            key=powermeter_config["key"],
            translation_key=powermeter_config["key"],
            icon="mdi:meter-electric",
            native_unit_of_measurement=UnitOfPower.WATT,
            suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
            suggested_display_precision=1,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        )
        entities.append(E3DCSensor(coordinator, power_description, entry.unique_id))

    for wallbox in coordinator.wallboxes:
        # Get the UID & Key for the given wallbox
        unique_id = list(wallbox["deviceInfo"]["identifiers"])[0][1]
        wallbox_key = wallbox["key"]

        wallbox_app_software_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-app-software",
            translation_key="wallbox-app-software",
            icon="mdi:information-outline",
            device_class=None,
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_app_software_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_consumption_net_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-consumption-net",
            translation_key="wallbox-consumption-net",
            icon="mdi:transmission-tower-import",
            native_unit_of_measurement=UnitOfPower.WATT,
            suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_consumption_net_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_consumption_sun_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-consumption-sun",
            translation_key="wallbox-consumption-sun",
            icon="mdi:solar-power",
            native_unit_of_measurement=UnitOfPower.WATT,
            suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_consumption_sun_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_energy_all_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-energy-all",
            translation_key="wallbox-energy-all",
            icon="mdi:counter",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=2,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_energy_all_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_energy_net_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-energy-net",
            translation_key="wallbox-energy-net",
            icon="mdi:counter",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=2,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_energy_net_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_energy_sun_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-energy-sun",
            translation_key="wallbox-energy-sun",
            icon="mdi:counter",
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            suggested_display_precision=2,
            device_class=SensorDeviceClass.ENERGY,
            state_class=SensorStateClass.TOTAL_INCREASING,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_energy_sun_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_index_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-index",
            translation_key="wallbox-index",
            icon="mdi:numeric",
            device_class=None,
            entity_registry_enabled_default=False,
            entity_category=EntityCategory.DIAGNOSTIC,
        )
        entities.append(
            E3DCSensor(
                coordinator, wallbox_index_description, unique_id, wallbox["deviceInfo"]
            )
        )

        wallbox_max_charge_current_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-max-charge-current",
            translation_key="wallbox-max-charge-current",
            icon="mdi:current-ac",
            native_unit_of_measurement="A",
            device_class=SensorDeviceClass.CURRENT,
            state_class=SensorStateClass.MEASUREMENT,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_max_charge_current_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_phases_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-phases",
            translation_key="wallbox-phases",
            icon="mdi:sine-wave",
            device_class=None,
        )
        entities.append(
            E3DCSensor(
                coordinator,
                wallbox_phases_description,
                unique_id,
                wallbox["deviceInfo"],
            )
        )

        wallbox_soc_description = E3DCSensorEntityDescription(
            key=f"{wallbox_key}-soc",
            translation_key="wallbox-soc",
            icon="mdi:battery-charging",
            native_unit_of_measurement=PERCENTAGE,
            suggested_display_precision=0,
            device_class=SensorDeviceClass.BATTERY,
            state_class=SensorStateClass.MEASUREMENT,
            entity_registry_enabled_default=False,
        )
        entities.append(
            E3DCSensor(
                coordinator, wallbox_soc_description, unique_id, wallbox["deviceInfo"]
            )
        )

    if len(coordinator.wallboxes) > 0:
        wallbox_consumption_description = E3DCSensorEntityDescription(
            key="wallbox-consumption",
            translation_key="wallbox-consumption",
            icon="mdi:ev-station",
            native_unit_of_measurement=UnitOfPower.WATT,
            suggested_unit_of_measurement=UnitOfPower.KILO_WATT,
            suggested_display_precision=2,
            device_class=SensorDeviceClass.POWER,
            state_class=SensorStateClass.MEASUREMENT,
        )
        entities.append(
            E3DCSensor(coordinator, wallbox_consumption_description, entry.unique_id)
        )

    async_add_entities(entities)


class E3DCSensor(CoordinatorEntity, SensorEntity):
    """Custom E3DC Sensor implementation."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: E3DCCoordinator,
        description: E3DCSensorEntityDescription,
        uid: str,
        device_info: DeviceInfo | None = None,
    ) -> None:
        """Initialize the Sensor."""
        super().__init__(coordinator)
        self.coordinator: E3DCCoordinator = coordinator
        self.entity_description: E3DCSensorEntityDescription = description
        self._attr_unique_id = f"{uid}_{description.key}"
        self._has_custom_icons: bool = self.entity_description.icons is not None
        if device_info is not None:
            self._deviceInfo = device_info
        else:
            self._deviceInfo = self.coordinator.device_info()

    @property
    def native_value(self) -> StateType:
        """Return the reported sensor value."""
        return self.coordinator.data.get(self.entity_description.key)

    @property
    def icon(self) -> str | None:
        """Return the icon for the sensor."""
        return (
            self.get_icon() if self._has_custom_icons else self.entity_description.icon
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device information."""
        return self._deviceInfo

    def get_icon(self) -> str | None:
        """Return the icon for the sensor."""
        value: str = self.coordinator.data.get(self.entity_description.key)
        if self.entity_description.icons.get(value) is not None:
            return self.entity_description.icons.get(value)

        return None
