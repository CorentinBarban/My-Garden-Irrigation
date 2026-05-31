"""Plateforme switch — My Garden Irrigation."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
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
    async_add_entities([AutoIrrigationSwitch(coordinator, entry)])


class AutoIrrigationSwitch(SwitchEntity):
    """Active ou désactive l'arrosage automatique planifié par la centrale."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:calendar-clock"
    _attr_translation_key = "auto_irrigation"

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_auto_irrigation_switch"
        self._attr_device_info = _centrale_device_info(entry)

    @property
    def is_on(self) -> bool:
        return self._coordinator.config.auto_irrigation_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._coordinator.async_set_auto_irrigation(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._coordinator.async_set_auto_irrigation(False)
        self.async_write_ha_state()
