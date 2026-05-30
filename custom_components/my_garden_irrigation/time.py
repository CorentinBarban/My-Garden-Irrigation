"""Plateforme time — My Garden Irrigation."""
from __future__ import annotations

from datetime import time as dt_time

from homeassistant.components.time import TimeEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTRIBUTION,
    CONF_IRRIGATION_TIME,
    DEFAULT_IRRIGATION_TIME,
    DOMAIN,
    OPTIONS_FIELD_UPDATE_FLAG,
)
from .coordinator import IrrigationCoordinator
from .sensor import _centrale_device_info


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([IrrigationTimeEntity(hass, coordinator, entry)])


class IrrigationTimeEntity(TimeEntity):
    """Heure de déclenchement de l'arrosage automatique."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:clock-outline"
    _attr_translation_key = "irrigation_time"

    def __init__(
        self,
        hass: HomeAssistant,
        coordinator: IrrigationCoordinator,
        entry: ConfigEntry,
    ) -> None:
        self._hass = hass
        self._coordinator = coordinator
        self._entry = entry
        self._attr_unique_id = f"{entry.entry_id}_irrigation_time"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def native_value(self) -> dt_time | None:
        time_str: str = self._entry.options.get(CONF_IRRIGATION_TIME, DEFAULT_IRRIGATION_TIME)
        try:
            parts = time_str.split(":")
            return dt_time(int(parts[0]), int(parts[1]))
        except (ValueError, AttributeError, IndexError):
            return dt_time(6, 0)

    async def async_set_value(self, value: dt_time) -> None:
        time_str = f"{value.hour:02d}:{value.minute:02d}:00"
        self._hass.data[DOMAIN].setdefault(OPTIONS_FIELD_UPDATE_FLAG, set()).add(
            self._entry.entry_id
        )
        self._hass.config_entries.async_update_entry(
            self._entry, options={**self._entry.options, CONF_IRRIGATION_TIME: time_str}
        )
        self._coordinator._setup_auto_irrigation()
        await self._coordinator.async_request_refresh()
