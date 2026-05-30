"""Plateforme select — My Garden Irrigation."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_CROP_ID,
    CONF_CROPS,
    CONF_STAGE,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_MODE,
    DOMAIN,
    OPTIONS_FIELD_UPDATE_FLAG,
    STAGES,
    WATERING_FREQUENCIES,
    WATERING_FREQUENCY_DAILY,
    WATERING_MODE_CONTINUOUS,
    WATERING_MODES,
)
from .coordinator import IrrigationCoordinator
from .number import _update_crop_field, _update_global_option
from .sensor import _centrale_device_info, _plant_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les sélecteurs globaux (centrale) et par culture."""
    entities: list = [
        WateringFrequencySelect(hass, entry),
        WateringModeSelect(hass, entry),
    ]
    entities += [StageSelect(hass, entry, crop) for crop in entry.options.get(CONF_CROPS, [])]
    async_add_entities(entities)


class StageSelect(SelectEntity):
    """Contrôle le stade de croissance d'une culture."""

    _attr_has_entity_name = True
    _attr_translation_key = "stage"
    _attr_icon = "mdi:sprout-outline"
    _attr_options = STAGES

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, crop: dict) -> None:
        self._hass = hass
        self._entry = entry
        self._crop_id: str = crop[CONF_CROP_ID]
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_stage"
        self._attr_device_info = _plant_device_info(entry, crop)

    @property
    def current_option(self) -> str:
        for crop in self._entry.options.get(CONF_CROPS, []):
            if crop[CONF_CROP_ID] == self._crop_id:
                return crop[CONF_STAGE]
        return STAGES[0]

    async def async_select_option(self, option: str) -> None:
        _update_crop_field(self._hass, self._entry, self._crop_id, CONF_STAGE, option)
        coordinator: IrrigationCoordinator = self._hass.data[DOMAIN][self._entry.entry_id]
        await coordinator.async_request_refresh()


class WateringFrequencySelect(SelectEntity):
    """Contrôle la fréquence d'arrosage du potager (centrale)."""

    _attr_has_entity_name = True
    _attr_translation_key = "watering_frequency"
    _attr_icon = "mdi:calendar-clock"
    _attr_options = WATERING_FREQUENCIES

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_watering_frequency"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def current_option(self) -> str:
        return self._entry.options.get(CONF_WATERING_FREQUENCY, WATERING_FREQUENCY_DAILY)

    async def async_select_option(self, option: str) -> None:
        _update_global_option(self._hass, self._entry, CONF_WATERING_FREQUENCY, option)
        coordinator: IrrigationCoordinator = self._hass.data[DOMAIN][self._entry.entry_id]
        await coordinator.async_request_refresh()


class WateringModeSelect(SelectEntity):
    """Contrôle le mode d'arrosage du potager (centrale) : continu ou fractionné."""

    _attr_has_entity_name = True
    _attr_translation_key = "watering_mode"
    _attr_icon = "mdi:water-sync"
    _attr_options = WATERING_MODES

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_watering_mode"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def current_option(self) -> str:
        return self._entry.options.get(CONF_WATERING_MODE, WATERING_MODE_CONTINUOUS)

    async def async_select_option(self, option: str) -> None:
        _update_global_option(self._hass, self._entry, CONF_WATERING_MODE, option)
        coordinator: IrrigationCoordinator = self._hass.data[DOMAIN][self._entry.entry_id]
        await coordinator.async_request_refresh()
