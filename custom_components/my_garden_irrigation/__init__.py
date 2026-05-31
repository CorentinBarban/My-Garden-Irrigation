"""Intégration My Garden Irrigation pour Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import CONF_CROPS, DOMAIN, PLATFORMS, SERVICE_RECALCULATE
from .coordinator import IrrigationCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise l'intégration pour une entrée de configuration."""
    coordinator = IrrigationCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if not hass.services.has_service(DOMAIN, SERVICE_RECALCULATE):
        async def _handle_recalculate(_call: ServiceCall) -> None:
            for coord in hass.data.get(DOMAIN, {}).values():
                if isinstance(coord, IrrigationCoordinator):
                    await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, SERVICE_RECALCULATE, _handle_recalculate)
        _LOGGER.debug("Service %s.%s enregistré", DOMAIN, SERVICE_RECALCULATE)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge une entrée de configuration."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)

    return unloaded


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migration des entrées v1 → v2 : suppression de eto_entity_id des options."""
    if entry.version == 1:
        new_options = {k: v for k, v in entry.options.items() if k != "eto_entity_id"}
        new_options.setdefault(CONF_CROPS, [])
        hass.config_entries.async_update_entry(entry, options=new_options, version=2)
        _LOGGER.info("Migration v1→v2 : eto_entity_id retiré des options.")
    return True
