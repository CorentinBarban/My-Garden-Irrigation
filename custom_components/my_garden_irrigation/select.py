"""Plateforme select — My Garden Irrigation.

Toutes les entités lisent depuis le coordinateur, source unique de vérité.
Le stade par culture (StageSelect) est persisté dans le Store HA via
PersistenceManager et restauré au boot — plus de RestoreEntity. Après un
rechargement via le formulaire, c'est entry.options qui fait autorité.
"""
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


class StageSelect(SelectEntity):
    """Contrôle le stade de croissance d'une culture — vue sur le coordinateur."""

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
        self._attr_unique_id = f"{entry.entry_id}_{self._crop_id}_stage"
        self._attr_device_info = _plant_device_info(entry, crop)

    @property
    def current_option(self) -> str:
        return self._coordinator.config.get_crop_field(self._crop_id, CONF_STAGE)

    async def async_select_option(self, option: str) -> None:
        await self._coordinator.async_update_crop_field(self._crop_id, CONF_STAGE, option)
        self.async_write_ha_state()


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
        return self._coordinator.config.watering_frequency

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
        return self._coordinator.config.watering_mode

    async def async_select_option(self, option: str) -> None:
        self._coordinator.set_watering_mode(option)
        self.async_write_ha_state()
