"""Intégration My Garden Irrigation pour Home Assistant."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN, PLATFORMS, SERVICE_RECALCULATE
from .coordinator import IrrigationCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise l'intégration pour une entrée de configuration."""
    coordinator = IrrigationCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Rechargement automatique si les options changent (ajout/suppression de culture)
    entry.async_on_unload(entry.add_update_listener(_async_reload_entry))

    # Service recalculate (enregistré une seule fois pour le domaine)
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
    coordinator: IrrigationCoordinator = hass.data[DOMAIN][entry.entry_id]
    coordinator.async_unsubscribe()

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id)

    # Désenregistre le service quand la dernière entrée est retirée
    if not hass.data[DOMAIN]:
        hass.services.async_remove(DOMAIN, SERVICE_RECALCULATE)

    return unloaded


async def _async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Rechargement déclenché par un changement d'options."""
    await hass.config_entries.async_reload(entry.entry_id)
