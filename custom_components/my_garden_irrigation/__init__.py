"""Intégration My Garden Irrigation pour Home Assistant."""
from __future__ import annotations

import logging
import re

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import entity_registry as er

from .const import CONF_CROP_ID, CONF_CROPS, DOMAIN, PLATFORMS, SERVICE_RECALCULATE
from .coordinator import IrrigationCoordinator

_LOGGER = logging.getLogger(__name__)

_CROP_ENTITY_SUFFIXES = ("_nb_plants", "_density", "_stage", "_cumulative", "_kc")


def _cleanup_removed_crop_entities(
    hass: HomeAssistant, entry: ConfigEntry, current_crop_ids: set[str]
) -> None:
    """Supprime du registre les entités dont la culture a été retirée.

    Au rechargement, HA ne supprime pas automatiquement les entités qui ne sont
    plus retournées par async_setup_entry — elles restent en statut 'unavailable'.
    Cette fonction les nettoie avant que les plateformes soient réinitialisées.
    """
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"

    for entity_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        uid = entity_entry.unique_id
        if not uid.startswith(prefix):
            continue
        remainder = uid[len(prefix):]

        crop_id: str | None = None
        for suffix in _CROP_ENTITY_SUFFIXES:
            if remainder.endswith(suffix):
                crop_id = remainder[: -len(suffix)]
                break

        # IrrigationDataSensor : unique_id = {entry_id}_{crop_id} (UUID — 36 chars, 4 tirets)
        if crop_id is None and len(remainder) == 36 and remainder.count("-") == 4:
            crop_id = remainder

        if crop_id is not None and _UUID_RE.match(crop_id) and crop_id not in current_crop_ids:
            _LOGGER.debug(
                "Suppression entité orpheline %s (culture %s retirée des options)",
                entity_entry.entity_id,
                crop_id,
            )
            registry.async_remove(entity_entry.entity_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Initialise l'intégration pour une entrée de configuration."""
    current_crop_ids = {c[CONF_CROP_ID] for c in entry.options.get(CONF_CROPS, [])}
    _cleanup_removed_crop_entities(hass, entry, current_crop_ids)

    coordinator = IrrigationCoordinator(hass, entry)
    await coordinator.async_setup()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    coordinator.logger.info(
        "Intégration initialisée — %d culture(s) configurée(s).", len(current_crop_ids)
    )

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
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        coordinator.logger.info("Intégration déchargée.")

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
