"""Plateforme sensor — My Garden Irrigation."""
from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfVolume
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
    ATTR_VIA_DEVICE,
    ATTR_WEEKLY_PROJECTION_L,
    ATTRIBUTION,
    CONF_CROP_ID,
    CONF_CROP_NAME,
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
    """Crée un sensor par culture + sensors globaux."""
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]

    entities: list[SensorEntity] = [
        TotalIrrigationSensor(coordinator, entry),
        EToSensor(coordinator, entry),
    ]
    for crop in entry.options.get(CONF_CROPS, []):
        entities.append(CropIrrigationSensor(coordinator, entry, crop))
        entities.append(KcSensor(coordinator, entry, crop))
        entities.append(ETcSensor(coordinator, entry, crop))

    async_add_entities(entities)


def _centrale_device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        entry_type=DeviceEntryType.SERVICE,
        identifiers={(DOMAIN, entry.entry_id)},
        name=entry.data.get(CONF_NAME, "Potager"),
        manufacturer="FAO Paper 56",
        model="Garden Irrigation Hub",
        sw_version="1.0.0",
    )


def _plant_device_info(entry: ConfigEntry, crop: dict) -> DeviceInfo:
    crop_id = crop[CONF_CROP_ID]
    name = crop.get(CONF_CROP_NAME) or crop[CONF_CROP_TYPE].capitalize()
    return DeviceInfo(
        identifiers={(DOMAIN, f"{entry.entry_id}_{crop_id}")},
        name=name,
        manufacturer="FAO Paper 56",
        model=crop[CONF_CROP_TYPE].capitalize(),
        via_device=(DOMAIN, entry.entry_id),
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
        self._entry_id: str = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}"
        self._attr_name = "Irrigation"
        self._attr_device_info = _plant_device_info(entry, crop)

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
            ATTR_VIA_DEVICE: self._entry_id,
        }


class KcSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Coefficient cultural Kc d'une culture (sans dimension)."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:leaf-circle-outline"

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        super().__init__(coordinator)
        self._crop_id: str = crop[CONF_CROP_ID]
        self._entry_id: str = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_kc"
        self._attr_name = "Kc"
        self._attr_device_info = _plant_device_info(entry, crop)

    def _crop_result(self) -> CropResult | None:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return None
        return data.crops.get(self._crop_id)

    @property
    def native_value(self) -> float | None:
        result = self._crop_result()
        return result.kc if result else None

    @property
    def extra_state_attributes(self) -> dict:
        result = self._crop_result()
        if result is None:
            return {}
        return {
            ATTR_CROP_TYPE: result.crop_type,
            ATTR_STAGE: result.stage,
            ATTR_VIA_DEVICE: self._entry_id,
        }


class ETcSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Évapotranspiration culturale ETc (mm/j) = Kc × ETo."""

    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:water-sync"

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        super().__init__(coordinator)
        self._crop_id: str = crop[CONF_CROP_ID]
        self._entry_id: str = entry.entry_id
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_etc"
        self._attr_name = "ETc"
        self._attr_device_info = _plant_device_info(entry, crop)

    def _crop_result(self) -> CropResult | None:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return None
        return data.crops.get(self._crop_id)

    @property
    def native_value(self) -> float | None:
        result = self._crop_result()
        if result is None:
            return None
        return round(result.kc * result.eto_mm, 2)

    @property
    def extra_state_attributes(self) -> dict:
        result = self._crop_result()
        if result is None:
            return {}
        return {
            ATTR_CROP_TYPE: result.crop_type,
            ATTR_STAGE: result.stage,
            ATTR_KC: result.kc,
            ATTR_ETO_MM: result.eto_mm,
            ATTR_VIA_DEVICE: self._entry_id,
        }


class EToSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Évapotranspiration de référence du jour (mm/j) — source Open-Meteo."""

    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:sun-thermometer-outline"

    def __init__(
        self, coordinator: IrrigationCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_eto"
        self._attr_name = "ETo"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float | None:
        data: IrrigationData | None = self.coordinator.data
        return data.eto_mm if data else None


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
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float | None:
        data: IrrigationData | None = self.coordinator.data
        return data.total_liters if data else None
