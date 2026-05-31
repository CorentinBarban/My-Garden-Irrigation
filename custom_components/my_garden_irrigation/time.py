"""Plateforme time — My Garden Irrigation.

IrrigationTimeEntity lit depuis le coordinateur (initialisé depuis entry.options).
Pas de RestoreEntity : après un rechargement via le formulaire, entry.options
fait autorité sur le dernier état HA.
"""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import ATTRIBUTION, DOMAIN
from .coordinator import IrrigationCoordinator
from .sensor import _centrale_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrrigationTimeEntity(coordinator, entry)])


class IrrigationTimeEntity(TimeEntity):
    """Heure de déclenchement de l'arrosage automatique."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "irrigation_time"

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_irrigation_time"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> dt_time:
        return self._parse_time(self._coordinator.config.irrigation_time)

    async def async_set_value(self, value: dt_time) -> None:
        time_str = f"{value.hour:02d}:{value.minute:02d}:00"
        self._coordinator.set_irrigation_time(time_str)
        self.async_write_ha_state()

    @staticmethod
    def _parse_time(time_str: str) -> dt_time:
        try:
            parts = time_str.split(":")
            return dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, AttributeError, IndexError):
            return dt_time(6, 0)
