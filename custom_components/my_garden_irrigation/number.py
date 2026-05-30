"""Plateforme number — My Garden Irrigation."""
from __future__ import annotations

import copy

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CROP_ID,
    CONF_CROPS,
    CONF_DENSITY,
    CONF_NB_PLANTS,
    DOMAIN,
    OPTIONS_FIELD_UPDATE_FLAG,
)
from .coordinator import IrrigationCoordinator
from .sensor import _plant_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les contrôles numériques par culture."""
    entities = []
    for crop in entry.options.get(CONF_CROPS, []):
        entities.append(NbPlantsNumber(hass, entry, crop))
        entities.append(DensityNumber(hass, entry, crop))
    async_add_entities(entities)


def _update_crop_field(
    hass: HomeAssistant,
    entry: ConfigEntry,
    crop_id: str,
    field: str,
    value: object,
) -> None:
    """Met à jour un champ d'une culture dans les options sans rechargement complet."""
    crops = copy.deepcopy(entry.options.get(CONF_CROPS, []))
    for crop in crops:
        if crop[CONF_CROP_ID] == crop_id:
            crop[field] = value
            break
    hass.data[DOMAIN].setdefault(OPTIONS_FIELD_UPDATE_FLAG, set()).add(entry.entry_id)
    hass.config_entries.async_update_entry(entry, options={**entry.options, CONF_CROPS: crops})


async def _refresh(hass: HomeAssistant, entry_id: str) -> None:
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry_id]
    await coordinator.async_request_refresh()


class NbPlantsNumber(NumberEntity):
    """Contrôle le nombre de plants d'une culture."""

    _attr_has_entity_name = True
    _attr_translation_key = "nb_plants"
    _attr_icon = "mdi:sprout"
    _attr_native_min_value = 1
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.BOX

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, crop: dict) -> None:
        self._hass = hass
        self._entry = entry
        self._crop_id: str = crop[CONF_CROP_ID]
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_nb_plants"
        self._attr_device_info = _plant_device_info(entry, crop)

    @property
    def native_value(self) -> float:
        for crop in self._entry.options.get(CONF_CROPS, []):
            if crop[CONF_CROP_ID] == self._crop_id:
                return float(crop[CONF_NB_PLANTS])
        return 1.0

    async def async_set_native_value(self, value: float) -> None:
        _update_crop_field(self._hass, self._entry, self._crop_id, CONF_NB_PLANTS, int(value))
        await _refresh(self._hass, self._entry.entry_id)


class DensityNumber(NumberEntity):
    """Contrôle la densité de plantation d'une culture (plants/m²)."""

    _attr_has_entity_name = True
    _attr_translation_key = "density"
    _attr_icon = "mdi:grid"
    _attr_native_min_value = 0.1
    _attr_native_max_value = 100.0
    _attr_native_step = 0.1
    _attr_mode = NumberMode.BOX

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, crop: dict) -> None:
        self._hass = hass
        self._entry = entry
        self._crop_id: str = crop[CONF_CROP_ID]
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_density"
        self._attr_device_info = _plant_device_info(entry, crop)

    @property
    def native_value(self) -> float:
        for crop in self._entry.options.get(CONF_CROPS, []):
            if crop[CONF_CROP_ID] == self._crop_id:
                return float(crop[CONF_DENSITY])
        return 1.0

    async def async_set_native_value(self, value: float) -> None:
        _update_crop_field(self._hass, self._entry, self._crop_id, CONF_DENSITY, round(value, 1))
        await _refresh(self._hass, self._entry.entry_id)
