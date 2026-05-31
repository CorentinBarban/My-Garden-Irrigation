"""Plateforme time — My Garden Irrigation.

Utilise RestoreEntity pour persister l'heure d'arrosage sans écrire
dans ConfigEntry.options (Module 1 du CDC de refactoring).
"""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import (
    ATTRIBUTION,
    CONF_IRRIGATION_TIME,
    DEFAULT_IRRIGATION_TIME,
    DOMAIN,
)
from .coordinator import IrrigationCoordinator
from .sensor import _centrale_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrrigationTimeEntity(coordinator, entry)])


class IrrigationTimeEntity(TimeEntity, RestoreEntity):
    """Heure de déclenchement de l'arrosage automatique."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "irrigation_time"

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        time_str: str = entry.options.get(CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME)
        self._time_value: dt_time = self._parse_time(time_str)
        self._attr_unique_id = f"{entry.entry_id}_irrigation_time"
        self._attr_device_info = _centrale_device_info(entry)

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state not in ("unknown", "unavailable"):
            parsed = self._parse_time(last.state)
            if parsed is not None:
                self._time_value = parsed
        time_str = (
            f"{self._time_value.hour:02d}:{self._time_value.minute:02d}:00"
        )
        self._coordinator.set_irrigation_time(time_str)

    @property
    def native_value(self) -> dt_time:
        return self._time_value

    async def async_set_value(self, value: dt_time) -> None:
        self._time_value = value
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
