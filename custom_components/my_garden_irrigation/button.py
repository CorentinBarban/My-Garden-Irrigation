"""Plateforme button — My Garden Irrigation."""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities([
        ResetIrrigationButton(coordinator, entry),
        StartIrrigationNowButton(coordinator, entry),
    ])


class ResetIrrigationButton(ButtonEntity):
    """Remet à zéro le bilan hydrique cumulé de toutes les cultures."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:restart"
    _attr_translation_key = "reset_irrigation"

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_reset_irrigation"
        self._attr_device_info = _centrale_device_info(entry)

    async def async_press(self) -> None:
        await self._coordinator.async_reset_irrigation()


class StartIrrigationNowButton(ButtonEntity):
    """Lance immédiatement la séquence d'arrosage basée sur le besoin cumulé."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION
    _attr_icon = "mdi:play-circle-outline"
    _attr_translation_key = "start_irrigation_now"

    def __init__(self, coordinator: IrrigationCoordinator, entry: ConfigEntry) -> None:
        self._coordinator = coordinator
        self._attr_unique_id = f"{entry.entry_id}_start_irrigation_now"
        self._attr_device_info = _centrale_device_info(entry)

    async def async_press(self) -> None:
        await self._coordinator.async_run_irrigation_sequence()
