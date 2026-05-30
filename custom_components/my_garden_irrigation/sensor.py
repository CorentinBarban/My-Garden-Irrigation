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
    ATTR_CUMULATIVE_NEED_LITERS,
    ATTR_CYCLES_COUNT,
    ATTR_DENSITY,
    ATTR_DURATION_PER_CYCLE_MINUTES,
    ATTR_EFFECTIVE_RAINFALL_MM,
    ATTR_ETC_LITERS,
    ATTR_ETO_MM,
    ATTR_IS_FRACTIONED,
    ATTR_KC,
    ATTR_LITERS_PER_PLANT,
    ATTR_NB_PLANTS,
    ATTR_NET_LITERS,
    ATTR_PRECIPITATION_MM,
    ATTR_RECOMMENDED_DURATION_MINUTES,
    ATTR_SOAK_DURATION_MINUTES,
    ATTR_STAGE,
    ATTR_SURFACE_M2,
    ATTR_VIA_DEVICE,
    ATTR_WATERING_APPLIED_TODAY_LITERS,
    ATTR_WEEKLY_PROJECTION_L,
    ATTRIBUTION,
    CONF_CROP_ID,
    CONF_CROP_NAME,
    CONF_CROP_TYPE,
    CONF_CROPS,
    CONF_GLOBAL_FLOW_RATE,
    CONF_NAME,
    CONF_WATERING_MODE,
    DEFAULT_CYCLES_COUNT,
    DEFAULT_SOAK_DURATION_MINUTES,
    DOMAIN,
    WATERING_MODE_FRACTIONED,
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
        TotalCumulativeNeedSensor(coordinator, entry),
        EToSensor(coordinator, entry),
        PrecipitationSensor(coordinator, entry),
    ]
    for crop in entry.options.get(CONF_CROPS, []):
        entities.append(CropIrrigationSensor(coordinator, entry, crop))
        entities.append(CropCumulativeNeedSensor(coordinator, entry, crop))
        entities.append(KcSensor(coordinator, entry, crop))

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
        return result.daily_need_liters if result else None

    @property
    def extra_state_attributes(self) -> dict:
        result = self._crop_result()
        if result is None:
            return {}
        data: IrrigationData | None = self.coordinator.data
        attrs: dict = {
            ATTR_CROP_TYPE: result.crop_type,
            ATTR_STAGE: result.stage,
            ATTR_NB_PLANTS: result.nb_plants,
            ATTR_DENSITY: result.density,
            ATTR_SURFACE_M2: result.surface_m2,
            ATTR_KC: result.kc,
            ATTR_ETO_MM: result.eto_mm,
            ATTR_ETC_LITERS: result.etc_liters,
            ATTR_NET_LITERS: result.liters,
            ATTR_EFFECTIVE_RAINFALL_MM: result.effective_rainfall_mm,
            ATTR_WATERING_APPLIED_TODAY_LITERS: result.watering_applied_today_liters,
            ATTR_LITERS_PER_PLANT: result.liters_per_plant,
            ATTR_WEEKLY_PROJECTION_L: result.weekly_projection_l,
            ATTR_VIA_DEVICE: self._entry_id,
        }
        if data is not None:
            attrs[ATTR_CUMULATIVE_NEED_LITERS] = round(
                data.cumulative_need.get(self._crop_id, 0.0), 1
            )
        return attrs


class CropCumulativeNeedSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Besoin hydrique cumulé d'une culture depuis le dernier arrosage (litres)."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:water-plus"

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        super().__init__(coordinator)
        self._crop_id: str = crop[CONF_CROP_ID]
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_cumulative"
        self._attr_name = "Besoin cumulé"
        self._attr_device_info = _plant_device_info(entry, crop)

    @property
    def native_value(self) -> float | None:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return None
        return round(data.cumulative_need.get(self._crop_id, 0.0), 1)


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


class EToSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Évapotranspiration de référence du jour (mm/j) — source Open-Meteo."""

    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_suggested_display_precision = 2
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
        return data.total_daily_need_liters if data else None


class TotalCumulativeNeedSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Besoin hydrique cumulé total du potager depuis le dernier arrosage (litres)."""

    _attr_state_class = SensorStateClass.TOTAL
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:water-plus-outline"

    def __init__(
        self, coordinator: IrrigationCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_total_cumulative"
        self._attr_name = "Total cumulé"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float | None:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return None
        return round(sum(data.cumulative_need.values()), 1)

    @property
    def extra_state_attributes(self) -> dict:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return {}
        total_cumulative = sum(data.cumulative_need.values())
        flow_rate: float = self._entry.options.get(CONF_GLOBAL_FLOW_RATE, 0.0)
        if flow_rate <= 0 or total_cumulative <= 0:
            return {}
        duration_minutes = round((total_cumulative / flow_rate) * 60, 1)
        attrs: dict = {ATTR_RECOMMENDED_DURATION_MINUTES: duration_minutes}
        watering_mode: str = self._entry.options.get(CONF_WATERING_MODE, "")
        if watering_mode == WATERING_MODE_FRACTIONED:
            attrs[ATTR_IS_FRACTIONED] = True
            attrs[ATTR_CYCLES_COUNT] = DEFAULT_CYCLES_COUNT
            attrs[ATTR_DURATION_PER_CYCLE_MINUTES] = round(
                duration_minutes / DEFAULT_CYCLES_COUNT, 1
            )
            attrs[ATTR_SOAK_DURATION_MINUTES] = DEFAULT_SOAK_DURATION_MINUTES
        return attrs


class PrecipitationSensor(CoordinatorEntity[IrrigationCoordinator], SensorEntity):
    """Précipitations brutes du jour (mm) — source Open-Meteo."""

    _attr_device_class = SensorDeviceClass.PRECIPITATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPrecipitationDepth.MILLIMETERS
    _attr_suggested_display_precision = 1
    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:weather-rainy"

    def __init__(
        self, coordinator: IrrigationCoordinator, entry: ConfigEntry
    ) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{entry.entry_id}_precipitation"
        self._attr_name = "Précipitations"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float | None:
        data: IrrigationData | None = self.coordinator.data
        return data.precipitation_mm if data else None

    @property
    def extra_state_attributes(self) -> dict:
        data: IrrigationData | None = self.coordinator.data
        if data is None:
            return {}
        from .core.calculations import compute_effective_rainfall_mm
        return {
            ATTR_EFFECTIVE_RAINFALL_MM: round(compute_effective_rainfall_mm(data.precipitation_mm), 2),
        }
