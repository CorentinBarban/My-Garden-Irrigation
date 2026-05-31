"""Plateforme select — My Garden Irrigation.

StageSelect hérite de RestoreEntity (valeur modifiable sans formulaire).
WateringFrequencySelect et WateringModeSelect lisent depuis le coordinateur
(initialisé depuis entry.options) — après un rechargement via le formulaire,
c'est entry.options qui fait autorité, pas le dernier état HA.
"""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    CONF_CROP_ID,
    CONF_CROPS,
    CONF_STAGE,
    CONF_WATERING_FREQUENCY,
    CONF_WATERING_MODE,
    DOMAIN,
    STAGES,
    WATERING_FREQUENCIES,
    WATERING_MODES,
)
from .coordinator import IrrigationCoordinator
from .sensor import _centrale_device_info, _plant_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Crée les sélecteurs globaux (centrale) et par culture."""
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    entities: list = [
        WateringFrequencySelect(coordinator, entry),
        WateringModeSelect(coordinator, entry),
    ]
    entities += [
        StageSelect(coordinator, entry, crop)
        for crop in entry.options.get(CONF_CROPS, [])
    ]
    async_add_entities(entities)


class StageSelect(SelectEntity, RestoreEntity):
    """Contrôle le stade de croissance d'une culture (RestoreEntity)."""

    _attr_has_entity_name = True
    _attr_translation_key = "stage"
    _attr_icon = "mdi:sprout-outline"
    _attr_options = STAGES

    def __init__(
        self,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
        crop: dict,
    ) -> None:
        self._coordinator = coordinator
        self._crop_id: str = crop[CONF_CROP_ID]
        self._current: str = crop[CONF_STAGE]
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_stage"
        self._attr_device_info = _plant_device_info(entry, crop)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in STAGES:
            self._current = last.state
        self._coordinator.update_crop_field(self._crop_id, CONF_STAGE, self._current)
        await self._coordinator.async_request_refresh()

    @property
    def current_option(self) -> str:
        return self._current

    async def async_select_option(self, option: str) -> None:
        self._current = option
        self._coordinator.update_crop_field(self._crop_id, CONF_STAGE, option)
        self.async_write_ha_state()
        await self._coordinator.async_request_refresh()


class WateringFrequencySelect(SelectEntity):
    """Contrôle la fréquence d'arrosage — lit depuis le coordinateur."""

    _attr_has_entity_name = True
    _attr_translation_key = "watering_frequency"
    _attr_icon = "mdi:calendar-clock"
    _attr_options = WATERING_FREQUENCIES

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_watering_frequency"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def current_option(self) -> str:
        return self._coordinator.watering_frequency

    async def async_select_option(self, option: str) -> None:
        self._coordinator.set_watering_frequency(option)
        self.async_write_ha_state()


class WateringModeSelect(SelectEntity):
    """Contrôle le mode d'arrosage — lit depuis le coordinateur."""

    _attr_has_entity_name = True
    _attr_translation_key = "watering_mode"
    _attr_icon = "mdi:water-sync"
    _attr_options = WATERING_MODES

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_watering_mode"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def current_option(self) -> str:
        return self._coordinator.watering_mode

    async def async_select_option(self, option: str) -> None:
        self._coordinator.set_watering_mode(option)
        self.async_write_ha_state()
