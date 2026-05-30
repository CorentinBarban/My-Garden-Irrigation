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
    DOMAIN,
    OPTIONS_FIELD_UPDATE_FLAG,
    STAGES,
)
from .coordinator import IrrigationCoordinator
from .number import _update_crop_field
from .sensor import _plant_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée un sélecteur de stade par culture."""
    entities = [
        StageSelect(hass, entry, crop)
        for crop in entry.options.get(CONF_CROPS, [])
    ]
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
