"""Plateforme sensor — My Garden Irrigation."""
from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfVolume
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_CROP_TYPE,
    ATTR_DENSITY,
    ATTR_ETO_MM,
    ATTR_KC,
    ATTR_LITERS_PER_PLANT,
    ATTR_NB_PLANTS,
    ATTR_STAGE,
    ATTR_SURFACE_M2,
    ATTR_WEEKLY_PROJECTION_L,
    ATTRIBUTION,
    CONF_CROP_ID,
    CONF_CROP_TYPE,
    CONF_CROPS,
    CONF_NAME,
    DOMAIN,
)
from .coordinator import IrrigationCoordinator
from .core.models import CropResult, IrrigationData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée un sensor par culture + un sensor total."""
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        CropIrrigationSensor(coordinator, entry, crop)
        for crop in entry.options.get(CONF_CROPS, [])
    ]
    entities.append(TotalIrrigationSensor(coordinator, entry))

    async_add_entities(entities)


def _device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, "Potager"),
        manufacturer="FAO Paper 56",
        model="Garden Irrigation Calculator",
        sw_version="1.0.0",
    )


class CropIrrigationSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Besoin en eau journalier d'une culture (litres/jour)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:sprout"

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        super().__init__(coordinator)
        self._crop_id: str = crop[CONF_CROP_ID]
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}"
        self._attr_name = crop[CONF_CROP_TYPE].capitalize()
        self._attr_device_info = _device_info(entry)

    def _crop_result(self) -> CropResult | None:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return None
        return data.crops.get(self._crop_id)

    @property
    def native_value(self) -> float | None:
        result = self._crop_result()
        return result.liters if result else None

    @property
    def extra_state_attributes(self) -> dict:
        result = self._crop_result()
        if result is None:
            return {}
        return {
            ATTR_CROP_TYPE: result.crop_type,
            ATTR_STAGE: result.stage,
            ATTR_NB_PLANTS: result.nb_plants,
            ATTR_DENSITY: result.density,
            ATTR_SURFACE_M2: result.surface_m2,
            ATTR_KC: result.kc,
            ATTR_ETO_MM: result.eto_mm,
            ATTR_LITERS_PER_PLANT: result.liters_per_plant,
            ATTR_WEEKLY_PROJECTION_L: result.weekly_projection_l,
        }


class TotalIrrigationSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Besoin en eau total du potager (somme de toutes les cultures)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:watering-can"

    def __init__(
        self, coordinator: IrrigationCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_total"
        self._attr_name = "Total"
        self._attr_device_info = _device_info(entry)

    @property
    def native_value(self) -> float | None:
        data: IrrigationData | None = self.coordinator.data
        return data.total_liters if data else None
