"""Plateforme number — My Garden Irrigation.

Seules les entités pilotées UNIQUEMENT par l'utilisateur via l'interface
(NbPlantsNumber, DensityNumber) héritent de RestoreEntity — conformément
au CDC (Module 1). Les entités de configuration globale lisent leur valeur
depuis le coordinateur, lui-même initialisé depuis entry.options au démarrage.
"""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CROP_ID,
    CONF_CROPS,
    CONF_CYCLES_COUNT,
    CONF_DENSITY,
    CONF_GLOBAL_FLOW_RATE,
    CONF_NB_PLANTS,
    CONF_SOAK_DURATION,
    CONF_WATERING_INTERVAL_DAYS,
    DEFAULT_CYCLES_COUNT,
    DEFAULT_SOAK_DURATION_MINUTES,
    DOMAIN,
)
from .coordinator import IrrigationCoordinator
from .sensor import _centrale_device_info, _plant_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les contrôles numériques par culture et les contrôles globaux."""
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [
        GlobalFlowRateNumber(coordinator, entry),
        WateringIntervalDaysNumber(coordinator, entry),
        CyclesCountNumber(coordinator, entry),
        SoakDurationNumber(coordinator, entry),
    ]
    for crop in entry.options.get(CONF_CROPS, []):
        entities.append(NbPlantsNumber(coordinator, entry, crop))
        entities.append(DensityNumber(coordinator, entry, crop))
    async_add_entities(entities)


# ---------------------------------------------------------------------------
# Entités par culture — RestoreEntity (valeurs modifiables sans passer par
# le formulaire de config, donc non présentes dans entry.options)
# ---------------------------------------------------------------------------

class NbPlantsNumber(NumberEntity, RestoreEntity):
    """Contrôle le nombre de plants d'une culture."""

    _attr_has_entity_name = True
    _attr_translation_key = "nb_plants"
    _attr_icon = "mdi:sprout"
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        self._coordinator = coordinator
        self._crop_id: str = crop[CONF_CROP_ID]
        self._value: float = float(crop[CONF_NB_PLANTS])
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_nb_plants"
        self._attr_device_info = _plant_device_info(entry, crop)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            try:
                self._value = float(last.state)
            except ValueError:
                pass
        self._coordinator.update_crop_field(self._crop_id, CONF_NB_PLANTS, int(self._value))
        await self._coordinator.async_request_refresh()

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = value
        self.async_write_ha_state()
        await self._coordinator.async_update_crop_field(self._crop_id, CONF_NB_PLANTS, int(value))


class DensityNumber(NumberEntity, RestoreEntity):
    """Contrôle la densité de plantation d'une culture (plants/m²)."""

    _attr_has_entity_name = True
    _attr_translation_key = "density"
    _attr_icon = "mdi:grid"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 100.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        self._coordinator = coordinator
        self._crop_id: str = crop[CONF_CROP_ID]
        self._value: float = float(crop[CONF_DENSITY])
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_density"
        self._attr_device_info = _plant_device_info(entry, crop)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            try:
                self._value = float(last.state)
            except ValueError:
                pass
        self._coordinator.update_crop_field(self._crop_id, CONF_DENSITY, round(self._value, 1))
        await self._coordinator.async_request_refresh()

    @property
    def native_value(self) -> float:
        return self._value

    async def async_set_native_value(self, value: float) -> None:
        self._value = round(value, 1)
        self.async_write_ha_state()
        await self._coordinator.async_update_crop_field(self._crop_id, CONF_DENSITY, self._value)


# ---------------------------------------------------------------------------
# Entités de configuration globale — lisent depuis le coordinateur
# (lui-même initialisé depuis entry.options). Pas de RestoreEntity :
# après un rechargement via le formulaire, entry.options fait autorité.
# ---------------------------------------------------------------------------

class GlobalFlowRateNumber(NumberEntity):
    """Contrôle le débit total de l'installation d'arrosage (L/h) — centrale."""

    _attr_has_entity_name = True
    _attr_translation_key = "global_flow_rate"
    _attr_icon = "mdi:water-pump"
    _attr_native_min_value = 0
    _attr_native_max_value = 10_000
    _attr_native_step = 0.1
    _attr_native_unit_of_measurement = "L/h"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_global_flow_rate"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float:
        return self._coordinator.config.flow_rate

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.set_flow_rate(round(value, 1))
        self.async_write_ha_state()


class WateringIntervalDaysNumber(NumberEntity):
    """Intervalle en jours entre deux arrosages (fréquence = intervalle fixe)."""

    _attr_has_entity_name = True
    _attr_translation_key = "watering_interval_days"
    _attr_icon = "mdi:calendar-range"
    _attr_native_min_value = 1
    _attr_native_max_value = 30
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_watering_interval_days"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float:
        return float(self._coordinator.config.watering_interval_days)

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.set_watering_interval_days(int(value))
        self.async_write_ha_state()


class CyclesCountNumber(NumberEntity):
    """Nombre de cycles pour le mode d'arrosage fractionné (Cycle & Soak)."""

    _attr_has_entity_name = True
    _attr_translation_key = "cycles_count"
    _attr_icon = "mdi:repeat"
    _attr_native_min_value = 1
    _attr_native_max_value = 10
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_cycles_count"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float:
        return float(self._coordinator.config.cycles_count)

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.set_cycles_count(int(value))
        self.async_write_ha_state()


class SoakDurationNumber(NumberEntity):
    """Durée de repos (minutes) entre chaque cycle du mode fractionné."""

    _attr_has_entity_name = True
    _attr_translation_key = "soak_duration"
    _attr_icon = "mdi:timer-sand"
    _attr_native_min_value = 1
    _attr_native_max_value = 120
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "min"
    _attr_mode = NumberMode.BOX

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_soak_duration"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> float:
        return float(self._coordinator.config.soak_duration_minutes)

    async def async_set_native_value(self, value: float) -> None:
        self._coordinator.set_soak_duration_minutes(int(value))
        self.async_write_ha_state()
